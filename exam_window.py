"""
ExamWindow — split-panel exam interface.

Left : scrollable printed question booklet on the desk  (+/- zoom widget)
Right: separate answer sheet (blocks of 10 rows × A B C D E, pen ✕ when marked)
Top  : topbar with title, progress, timer, submit button
"""

import html
import json
from datetime import date
from PyQt6.QtCore import QObject, QTimer, pyqtSlot
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWidgets import QMainWindow
from aqt.qt import Qt
from PyQt6.QtWebEngineWidgets import QWebEngineView
from aqt import mw

from .paper import PAPER_CSS, PEN_SVG, comb_date, comb_field, fmt_duration


# ── Bridge ────────────────────────────────────────────────────────────────────

class _Bridge(QObject):
    def __init__(self, window: "ExamWindow"):
        super().__init__()
        self._win = window

    @pyqtSlot(str)
    def submitExam(self, answers_json: str):
        try:
            answers = json.loads(answers_json)
        except Exception:
            answers = {}
        self._win._on_submit(answers)

    @pyqtSlot()
    def timeUp(self):
        pass

    @pyqtSlot()
    def closeExam(self):
        QTimer.singleShot(0, self._win.close)

    @pyqtSlot()
    def takeAnotherExam(self):
        QTimer.singleShot(0, self._win._take_another_exam)

    @pyqtSlot(str, str)
    def tagNotes(self, nids_json: str, tag: str):
        try:
            nids = json.loads(nids_json)
        except Exception:
            nids = []
        self._win._tag_notes(nids, tag)

    @pyqtSlot(str, int)
    def flagNotes(self, nids_json: str, flag_num: int):
        try:
            nids = json.loads(nids_json)
        except Exception:
            nids = []
        self._win._flag_notes(nids, flag_num)


# ── Main window ───────────────────────────────────────────────────────────────

class ExamWindow(QMainWindow):
    def __init__(self, parent, questions: list, timer_seconds: int,
                 scoring: dict, exam_name: str = "Exam", save_history: bool = True):
        super().__init__(parent)
        self.questions     = questions
        self.timer_seconds = timer_seconds
        self.scoring       = scoring
        self.exam_name     = exam_name
        self.save_history  = save_history

        self.setWindowTitle(
            f"Exam Simulator — {len(questions)} Questions  |  {exam_name}")

        self._web = QWebEngineView()
        self._web.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setCentralWidget(self._web)

        self._channel = QWebChannel()
        self._bridge  = _Bridge(self)
        self._channel.registerObject("pybridge", self._bridge)
        self._web.loadFinished.connect(self._rebind_webchannel)
        self._rebind_webchannel()

        self._web.setHtml(self._build_exam_html())

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _rebind_webchannel(self, *_args):
        try:
            self._web.page().setWebChannel(self._channel)
        except Exception:
            pass


    def _take_another_exam(self):
        from .launcher import LauncherDialog

        self.close()
        dlg = LauncherDialog(mw)
        dlg.exec()

    def _tag_notes(self, nids, tag):
        try:
            clean_tag = str(tag).strip().replace(" ", "_")
            ids = [int(nid) for nid in nids if str(nid).strip()]
        except Exception:
            return
        if not clean_tag or not ids:
            return
        changed = False
        for nid in ids:
            try:
                note = mw.col.get_note(int(nid))
                note.add_tag(clean_tag)
                note.flush()
                changed = True
            except Exception:
                pass
        if changed:
            try:
                mw.col.setMod()
            except Exception:
                pass
            try:
                mw.reset()
            except Exception:
                pass

    def _flag_notes(self, nids, flag_num):
        try:
            ids = [int(nid) for nid in nids if str(nid).strip()]
            flag_num = int(flag_num)
        except Exception:
            return
        if not ids:
            return
        changed = False
        for nid in ids:
            try:
                note = mw.col.get_note(int(nid))
                for card in note.cards():
                    card.set_user_flag(flag_num)
                    card.flush()
                    changed = True
            except Exception:
                pass
        if changed:
            try:
                mw.col.setMod()
            except Exception:
                pass
            try:
                mw.reset()
            except Exception:
                pass


    def _on_submit(self, answers_dict: dict):
        from .history_store import record_simulation
        from .scorer import compute_score, build_results_html

        if self.save_history:
            note_ids = [int(q["nid"]) for q in self.questions if q.get("nid") is not None]
            record_simulation(self.exam_name, note_ids)

        results = compute_score(self.questions, answers_dict, self.scoring)
        results["exam_name"] = self.exam_name
        results["timer_seconds"] = self.timer_seconds
        self._web.setHtml(build_results_html(results))
        self._rebind_webchannel()

    # ── HTML builders ─────────────────────────────────────────────────────────

    def _build_exam_html(self) -> str:
        q_json  = json.dumps(self.questions, ensure_ascii=False)
        n       = len(self.questions)
        timer_s = self.timer_seconds
        hidden  = "hidden" if not timer_s else ""
        name    = html.escape(self.exam_name)
        today   = date.today().strftime("%d/%m/%Y")
        dur     = fmt_duration(timer_s)
        dur_html = f'<span><b>Durée :</b> {dur}</span>' if dur else ""

        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Exam — {name}</title>
<style>{PAPER_CSS}{_EXAM_CSS}</style>
</head>
<body>

<!-- TOPBAR -->
<div id="topbar">
  <div id="exam-meta">
    <span id="exam-title">{name}</span>
    <span id="progress"><b id="ans-count">0</b> / {n} answered</span>
  </div>
  <div id="timer-wrap" class="{hidden}"><span id="timer-text">--:--</span></div>
  <button id="submit-btn" onclick="askSubmit()">Submit Exam</button>
</div>

<!-- MAIN -->
<div id="main">
  <div id="left-panel" class="desk">
    <div id="zoom-ctrl">
      <button class="zoom-btn" onclick="zoomIn()" title="Zoom in" aria-label="Zoom in">+</button>
      <button class="zoom-btn" onclick="zoomOut()" title="Zoom out" aria-label="Zoom out">&minus;</button>
    </div>
    <article id="booklet" class="paper">
      <header class="paper-head">
        <div class="ph-row"><span><b>Module :</b> {name}</span><span><b>Date :</b> {today}</span></div>
        <div class="ph-row"><span>{n} QCM</span>{dur_html}</div>
      </header>
      <div id="questions-container"></div>
    </article>
  </div>
  <div id="right-panel" class="desk">
    <section id="sheet" class="paper" aria-label="Answer sheet">
      <div class="sheet-head">
        <div class="sheet-fields">
          {comb_field("Module", self.exam_name.upper(), 18)}
          {comb_date("Date", today)}
        </div>
        <div class="sheet-rules">
          <b>Consignes</b>
          <p>Cochez d'une croix la ou les réponse(s) juste(s) dans la case correspondante.</p>
          <p class="ex">Exemple : <span class="box box-on">{PEN_SVG}</span></p>
        </div>
      </div>
      <div id="sheet-grid"></div>
    </section>
  </div>
</div>

<!-- Custom confirm modal -->
<div id="modal-overlay" style="display:none;">
  <div id="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <div id="modal-title">Submit your paper?</div>
    <div id="modal-msg"></div>
    <div id="modal-btns">
      <button id="modal-cancel" onclick="modalCancel()">Keep answering</button>
      <button id="modal-ok"     onclick="modalOk()">Submit anyway</button>
    </div>
  </div>
</div>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>
"use strict";

const QUESTIONS     = {q_json};
const TIMER_SECONDS = {timer_s};
const N             = QUESTIONS.length;
const PEN           = '{PEN_SVG}';

let pybridge      = null;
let answers       = {{}};
let timerLeft     = TIMER_SECONDS;
let timerInterval = null;
let fontSize      = 15;
let _modalResolve = null;

new QWebChannel(qt.webChannelTransport, ch => {{
  pybridge = ch.objects.pybridge || null;
}});

/* ── Booklet ────────────────────────────────────────────────────────────── */
function renderQuestions() {{
  const c = document.getElementById("questions-container");
  QUESTIONS.forEach((q, i) => {{
    const block = document.createElement("div");
    block.className = "q-block";
    block.id        = "qblock-" + i;
    let opts = "";
    for (const [l, t] of Object.entries(q.options))
      opts += `<div class="q-opt"><span class="opt-letter">${{l}}:</span><span class="opt-text">${{t}}</span></div>`;
    const src = q.source ? `<div class="q-source">Source : ${{q.source}}</div>` : "";
    block.innerHTML = `
      <div class="q-header">
        <span class="q-num">${{i+1}}</span>
        <span class="q-text">${{q.question}}</span>
      </div>
      <div class="q-opts">${{opts}}</div>${{src}}`;
    c.appendChild(block);
  }});
}}

/* ── Answer sheet: blocks of 10, first half down the left column ────────── */
function renderGrid() {{
  const ALL  = ["A","B","C","D","E"];
  const used = new Set();
  QUESTIONS.forEach(q => Object.keys(q.options).forEach(l => used.add(l)));
  const cols = ALL.filter(l => used.has(l));

  const nBlocks = Math.ceil(N / 10);
  const nLeft   = Math.ceil(nBlocks / 2);
  const grid    = document.getElementById("sheet-grid");
  const colEls  = [document.createElement("div"), document.createElement("div")];
  colEls.forEach(el => {{ el.className = "sheet-col"; grid.appendChild(el); }});

  for (let b = 0; b < nBlocks; b++) {{
    let rows = "";
    for (let i = b * 10; i < Math.min(N, b * 10 + 10); i++) {{
      const q = QUESTIONS[i];
      let cells = `<th class="qlabel" scope="row" onclick="scrollToQ(${{i}})" title="Go to question ${{i+1}}">Q${{i+1}}</th>`;
      cols.forEach(l => {{
        cells += q.options[l] !== undefined
          ? `<td><span class="box" id="b-${{i}}-${{l}}" role="checkbox" aria-checked="false" aria-label="Q${{i+1}} ${{l}}" tabindex="0" onclick="toggle(${{i}},'${{l}}')" onkeydown="boxKey(event,${{i}},'${{l}}')"></span></td>`
          : `<td><span class="box box-na" aria-hidden="true"></span></td>`;
      }});
      rows += `<tr>${{cells}}</tr>`;
    }}
    const head = "<tr><th></th>" + cols.map(l => `<th scope="col">${{l}}</th>`).join("") + "</tr>";
    const table = document.createElement("table");
    table.className = "block";
    table.innerHTML = `<thead>${{head}}</thead><tbody>${{rows}}</tbody>`;
    colEls[b < nLeft ? 0 : 1].appendChild(table);
  }}
}}

function toggle(qi, l) {{
  if (!answers[qi]) answers[qi] = new Set();
  const s  = answers[qi];
  const el = document.getElementById(`b-${{qi}}-${{l}}`);
  if (s.has(l)) {{
    s.delete(l); el.classList.remove("box-on"); el.innerHTML = "";
  }} else {{
    s.add(l); el.classList.add("box-on");
    el.innerHTML = PEN;
    // a hand never draws the same cross twice
    el.firstChild.style.transform = `rotate(${{((qi * 7 + l.charCodeAt(0) * 3) % 11) - 5}}deg) scale(1.12)`;
  }}
  el.setAttribute("aria-checked", s.has(l) ? "true" : "false");
  document.getElementById("ans-count").textContent =
    Object.values(answers).filter(s=>s&&s.size>0).length;
}}

function boxKey(e, qi, l) {{
  if (e.key === " " || e.key === "Enter") {{ e.preventDefault(); toggle(qi, l); }}
}}

function scrollToQ(i) {{
  const el = document.getElementById("qblock-"+i);
  if (!el) return;
  el.scrollIntoView({{behavior:"smooth",block:"start"}});
  el.classList.remove("q-target");
  void el.offsetWidth;
  el.classList.add("q-target");
}}

/* ── Zoom ───────────────────────────────────────────────────────────────── */
function zoomIn()  {{ fontSize = Math.min(fontSize + 2, 27); applyZoom(); }}
function zoomOut() {{ fontSize = Math.max(fontSize - 2, 11); applyZoom(); }}
function applyZoom() {{
  document.getElementById("booklet").style.fontSize = fontSize + "px";
}}

/* ── Timer ──────────────────────────────────────────────────────────────── */
function startTimer() {{
  if (!TIMER_SECONDS) return;
  renderTimer();
  timerInterval = setInterval(() => {{
    timerLeft--;
    renderTimer();
    if (timerLeft <= 300) document.getElementById("timer-wrap").classList.add("timer-warn");
    if (timerLeft <= 0)   {{ clearInterval(timerInterval); if(pybridge) pybridge.timeUp(); doSubmit(); }}
  }}, 1000);
}}
function renderTimer() {{
  const m = String(Math.floor(timerLeft/60)).padStart(2,"0");
  const s = String(timerLeft%60).padStart(2,"0");
  document.getElementById("timer-text").textContent = m+":"+s;
}}

/* ── Custom confirm modal ───────────────────────────────────────────────── */
function showModal(msg) {{
  return new Promise(resolve => {{
    _modalResolve = resolve;
    document.getElementById("modal-msg").textContent = msg;
    document.getElementById("modal-overlay").style.display = "flex";
    document.getElementById("modal-cancel").focus();
  }});
}}
function modalOk()     {{ document.getElementById("modal-overlay").style.display="none"; if(_modalResolve) _modalResolve(true);  }}
function modalCancel() {{ document.getElementById("modal-overlay").style.display="none"; if(_modalResolve) _modalResolve(false); }}

async function askSubmit() {{
  const done      = Object.values(answers).filter(s=>s&&s.size>0).length;
  const remaining = N - done;
  if (remaining > 0) {{
    const ok = await showModal(`${{remaining}} question(s) still have no answer marked on the sheet.`);
    if (!ok) return;
  }}
  doSubmit();
}}

function doSubmit() {{
  if (timerInterval) clearInterval(timerInterval);
  const payload = {{}};
  Object.keys(answers).forEach(k => {{
    if (answers[k] && answers[k].size > 0)
      payload[k] = Array.from(answers[k]).sort();
  }});
  document.getElementById("submit-btn").disabled    = true;
  document.getElementById("submit-btn").textContent = "Grading…";
  if (pybridge) pybridge.submitExam(JSON.stringify(payload));
}}

renderQuestions();
renderGrid();
startTimer();
</script>
</body>
</html>"""


# ── CSS (plain string — no f-string, single braces are fine) ─────────────────

_EXAM_CSS = """
#main { display: flex; flex: 1; overflow: hidden; }

/* Topbar */
#topbar {
  position: relative;
  display: flex; align-items: center; justify-content: space-between;
  background: var(--bar); color: var(--bar-ink);
  padding: 10px 24px; flex-shrink: 0; gap: 16px;
}
#exam-meta { display: flex; align-items: baseline; gap: 14px; min-width: 0; }
#exam-title { font-size: 14px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#progress { font-size: 12px; color: var(--bar-soft); white-space: nowrap; font-variant-numeric: tabular-nums; }
#progress b { color: var(--bar-ink); }
#timer-wrap {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  font-size: 22px; font-weight: bold; font-variant-numeric: tabular-nums;
  color: #7dd3fc; min-width: 90px; text-align: center;
}
#timer-wrap.hidden { visibility: hidden; }
#timer-wrap.timer-warn { color: #f87171; animation: blink 1s steps(1) infinite; }
@keyframes blink { 50% { opacity: .4; } }
#submit-btn {
  background: var(--accent); color: #fff; border: none; border-radius: 4px;
  padding: 8px 20px; font-size: 13px; font-weight: bold;
  cursor: pointer; font-family: inherit;
}
#submit-btn:hover    { background: var(--accent-hover); }
#submit-btn:disabled { background: #64748b; cursor: default; }

/* Booklet side */
#left-panel { flex: 1; overflow-y: auto; position: relative; padding: 28px 32px 48px; }
#booklet {
  max-width: 820px; margin: 0 auto;
  padding: 52px 64px 64px; font-size: 15px;
}

/* Zoom widget */
#zoom-ctrl {
  position: sticky; top: 0; float: right; height: 0;
  display: flex; flex-direction: column; gap: 4px; z-index: 20;
}
.zoom-btn {
  width: 30px; height: 30px; border-radius: 4px;
  background: #ecebe7; border: 1px solid #a9a69e; color: var(--desk-ink);
  font: bold 17px/1 Arial, sans-serif; cursor: pointer;
}
.zoom-btn:hover { background: #fff; }

/* Answer sheet side */
#right-panel { flex: 0 0 412px; overflow-y: auto; padding: 28px 22px 48px 0; }
#sheet { padding: 22px 20px 36px; min-height: 100%; }
.sheet-head { border-bottom: 1.5px solid var(--rule); padding-bottom: 12px; margin-bottom: 24px; }
.sheet-fields { display: flex; flex-direction: column; gap: 6px; margin-bottom: 12px; }
.comb { display: flex; align-items: center; gap: 8px; }
.comb-label { width: 48px; font-size: 11px; color: var(--print-soft); text-align: right; flex-shrink: 0; }
.cells { display: flex; align-items: center; }
.cell {
  width: 15px; height: 18px; border: 1px solid #6b6b6b; margin-left: -1px;
  display: inline-flex; align-items: center; justify-content: center;
  font: bold 11px/1 Arial, sans-serif; color: var(--pen);
}
.cell-sep { padding: 0 4px; font-size: 12px; color: var(--print-soft); }
.sheet-rules {
  border: 1px solid #6b6b6b; padding: 8px 10px;
  font-size: 12px; line-height: 1.45; color: #333;
}
.sheet-rules b { display: block; margin-bottom: 2px; font-size: 12px; color: var(--print); }
.sheet-rules .ex { display: flex; align-items: center; gap: 8px; margin-top: 4px; }

#sheet-grid { display: flex; justify-content: space-between; gap: 18px; }
.sheet-col { display: flex; flex-direction: column; gap: 26px; }
.block { border: 1.5px solid var(--rule); border-collapse: collapse; font-size: 12px; }
.block thead th {
  background: var(--head-fill); font-size: 12px; font-weight: bold;
  padding: 2px 0; text-align: center; border-bottom: 1px solid var(--rule);
}
.block td { padding: 3px 2px; text-align: center; }
.block tbody tr:first-child td, .block tbody tr:first-child th { padding-top: 6px; }
.block tbody tr:last-child td, .block tbody tr:last-child th { padding-bottom: 6px; }
.qlabel {
  padding: 3px 6px 3px 6px; text-align: left; font-weight: normal;
  white-space: nowrap; cursor: pointer; font-variant-numeric: tabular-nums;
}
.qlabel:hover { text-decoration: underline; text-underline-offset: 2px; }
.box {
  width: 17px; height: 17px; border: 1.4px solid var(--rule); background: var(--paper);
  display: inline-flex; vertical-align: middle; cursor: pointer; padding: 0;
}
.box:hover { background: #eef1fb; }
.box-na { border-color: #c4c4c4; background: #f2f2f2; cursor: default; }
.box-na:hover { background: #f2f2f2; }

/* Custom confirm modal */
#modal-overlay {
  position: fixed; inset: 0; background: rgba(20,20,20,.45);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
#modal-box {
  background: var(--paper); border-radius: 6px;
  padding: 26px 30px; min-width: 320px; max-width: 420px;
  box-shadow: 0 10px 32px rgba(0,0,0,.28);
}
#modal-title { font-size: 16px; font-weight: bold; margin-bottom: 10px; }
#modal-msg { font-size: 14px; color: #333; margin-bottom: 22px; line-height: 1.5; }
#modal-btns { display: flex; justify-content: flex-end; gap: 10px; }
#modal-btns button { padding: 8px 18px; border-radius: 4px; cursor: pointer; font: 13px Arial, sans-serif; }
#modal-cancel { border: 1px solid #b5b5b5; background: #fff; }
#modal-cancel:hover { background: #f1f1f1; }
#modal-ok { border: none; background: var(--accent); color: #fff; font-weight: bold; }
#modal-ok:hover { background: var(--accent-hover); }
"""
