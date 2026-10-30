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

from . import i18n
from .i18n import t
from .paper import NOTES_CSS, NOTES_JS, PAPER_CSS, PEN_SVG, comb_field, fmt_duration


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

    @pyqtSlot(str)
    def saveNotes(self, notes_json: str):
        try:
            self._win._notes = json.loads(notes_json)
        except Exception:
            self._win._notes = {}

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
        self._notes        = {}

        self.setWindowTitle(t("exam_window_title", n=len(questions), name=exam_name))

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
        results["notes"] = self._notes
        self._web.setHtml(build_results_html(results))
        self._rebind_webchannel()

    # ── HTML builders ─────────────────────────────────────────────────────────

    def _build_exam_html(self) -> str:
        # "</" would end the <script> early if a field contains "</script>"
        q_json  = json.dumps(self.questions, ensure_ascii=False).replace("</", "<\\/")
        n       = len(self.questions)
        timer_s = self.timer_seconds
        hidden  = "hidden" if not timer_s else ""
        name    = html.escape(self.exam_name)
        today   = i18n.fmt_date(date.today())
        dur     = fmt_duration(timer_s)
        dur_html = f'<span><b>{i18n.label("duration")}</b> {dur}</span>' if dur else ""
        js_strings = json.dumps(i18n.strings(
            "source", "label_colon", "go_to_question", "submit_title", "submit_msg",
            "submit_ok", "submit_cancel", "grading", "clear_title", "clear_msg",
            "clear_ok", "cancel"), ensure_ascii=False).replace("</", "<\\/")

        def swatch(kind, color, label):
            return (f'<button class="sw sw-{color}" data-kind="{kind}" data-color="{color}" '
                    f'onclick="pickColor(\'{kind}\',\'{color}\')" title="{label}" aria-label="{label}"></button>')

        return f"""<!DOCTYPE html>
<html lang="{i18n.lang()}">
<head>
<meta charset="utf-8">
<title>{t("exam_page_title", name=name)}</title>
<style>{PAPER_CSS}{NOTES_CSS}{_EXAM_CSS}</style>
</head>
<body data-tool="pointer">

<!-- TOPBAR -->
<div id="topbar">
  <div id="exam-meta">
    <span id="exam-title">{name}</span>
    <span id="progress"><b id="ans-count">0</b> / {n} {t("answered")}</span>
  </div>
  <div id="timer-wrap" class="{hidden}"><span id="timer-text">--:--</span></div>
  <button id="submit-btn" onclick="askSubmit()">{t("submit")}</button>
</div>

<!-- MAIN -->
<div id="main">
  <div id="left-panel" class="desk">
    <div id="tools" role="toolbar" aria-label="{t("tools_label")}">
      <div class="tgroup">
        <button class="tool" data-tool="pointer" onclick="setTool('pointer', true)" title="{t("tip_pointer")}">{_ICONS["pointer"]}<span>{t("tool_pointer")}</span></button>
        <button class="tool" data-tool="hl" onclick="setTool('hl')" title="{t("tip_highlight")}">{_ICONS["hl"]}<span>{t("tool_highlight")}</span></button>
        <span class="swatches">{swatch("hl", "yellow", t("hl_yellow"))}{swatch("hl", "green", t("hl_green"))}{swatch("hl", "pink", t("hl_pink"))}</span>
        <button class="tool" data-tool="pen" onclick="setTool('pen')" title="{t("tip_pen")}">{_ICONS["pen"]}<span>{t("tool_pen")}</span></button>
        <span class="swatches">{swatch("pen", "blue", t("pen_blue"))}{swatch("pen", "red", t("pen_red"))}</span>
        <button class="tool" data-tool="eraser" onclick="setTool('eraser')" title="{t("tip_eraser")}">{_ICONS["eraser"]}<span>{t("tool_eraser")}</span></button>
      </div>
      <div class="tgroup">
        <button class="tool" onclick="undo()" title="{t("tip_undo")}">{_ICONS["undo"]}<span>{t("tool_undo")}</span></button>
        <button class="tool" onclick="clearDrawings()" title="{t("tip_clear")}">{_ICONS["clear"]}<span>{t("tool_clear")}</span></button>
      </div>
      <div class="tgroup zoom">
        <button class="tool tool-sq" onclick="zoomOut()" title="{t("zoom_out")}" aria-label="{t("zoom_out")}">{_ICONS["minus"]}</button>
        <button class="tool" id="zoom-pct" onclick="resetZoom()" title="{t("zoom_reset")}">100%</button>
        <button class="tool tool-sq" onclick="zoomIn()" title="{t("zoom_in")}" aria-label="{t("zoom_in")}">{_ICONS["plus"]}</button>
      </div>
    </div>
    <div id="booklet-sizer">
      <article id="booklet" class="paper">
        <header class="paper-head">
          <div class="ph-row">
            <span><b>{i18n.label("module")}</b> {name}</span>
            <span><b>{i18n.label("date")}</b> {today}</span>
          </div>
          <div class="ph-row">
            <span>{t("n_mcq", n=n)}</span>
            {dur_html}
          </div>
        </header>
        <div id="questions-container"></div>
        <svg id="ink-layer" class="ink-layer" style="width:100%;height:100%"></svg>
      </article>
    </div>
  </div>
  <div id="right-panel" class="desk">
    <section id="sheet" class="paper" aria-label="{t("answer_sheet")}">
      <div class="sheet-head">
        <div class="sheet-fields">
          {comb_field(t("module"), self.exam_name.upper(), 18)}
        </div>
        <div class="sheet-rules">
          <b>{t("instructions")}</b>
          <p>{t("instructions_text")}</p>
          <p class="ex">{i18n.label("example")} <span class="box box-on">{PEN_SVG}</span></p>
        </div>
      </div>
      <div id="sheet-grid"></div>
    </section>
  </div>
</div>

<!-- Custom confirm modal -->
<div id="modal-overlay" style="display:none;">
  <div id="modal-box" role="dialog" aria-modal="true" aria-labelledby="modal-title">
    <div id="modal-title"></div>
    <div id="modal-msg"></div>
    <div id="modal-btns">
      <button id="modal-cancel" onclick="modalCancel()"></button>
      <button id="modal-ok"     onclick="modalOk()"></button>
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
const T             = {js_strings};

// "Durée :" / "Duration:" and "{{n}}"-style placeholders
function label(key) {{ return T.label_colon.replace("{{label}}", T[key]); }}
function fill(text, vals) {{ return text.replace(/\\{{(\\w+)\\}}/g, (m, k) => (k in vals ? vals[k] : m)); }}

let pybridge      = null;
let answers       = {{}};
let timerLeft     = TIMER_SECONDS;
let timerInterval = null;
let _modalResolve = null;

new QWebChannel(qt.webChannelTransport, ch => {{
  pybridge = ch.objects.pybridge || null;
}});

/* ── Booklet ────────────────────────────────────────────────────────────── */
function renderQuestions() {{
  const c = document.getElementById("questions-container");
  QUESTIONS.forEach((q, i) => {{
    const block = document.createElement("div");
    block.className  = "q-block";
    block.id         = "qblock-" + i;
    block.dataset.qi = i;
    let opts = "";
    for (const [l, t] of Object.entries(q.options))
      opts += `<div class="q-opt"><span class="opt-letter">${{l}}:</span><span class="opt-text" data-part="${{l}}">${{t}}</span></div>`;
    const src = q.source ? `<div class="q-source">${{label("source")}} ${{q.source}}</div>` : "";
    block.innerHTML = `
      <div class="q-header">
        <span class="q-num">${{i+1}}</span>
        <span class="q-text" data-part="Q">${{q.question}}</span>
      </div>
      <div class="q-opts">${{opts}}</div>${{src}}`;
    c.appendChild(block);
  }});
}}

/* ── Answer sheet: blocks of 10, first half down the left column ────────── */
const TICK = '<svg class="tick" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.6l2.6 2.6L10 3.2"/></svg>';

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
      let cells = `<th class="qlabel" scope="row" onclick="scrollToQ(${{i}})" title="${{fill(T.go_to_question, {{n: i+1}})}}">${{TICK}}Q${{i+1}}</th>`;
      cols.forEach(l => {{
        cells += q.options[l] !== undefined
          ? `<td><span class="box" id="b-${{i}}-${{l}}" role="checkbox" aria-checked="false" aria-label="Q${{i+1}} ${{l}}" tabindex="0" onclick="toggle(${{i}},'${{l}}')" onkeydown="boxKey(event,${{i}},'${{l}}')"></span></td>`
          : `<td><span class="box box-na" aria-hidden="true"></span></td>`;
      }});
      rows += `<tr id="grow-${{i}}">${{cells}}</tr>`;
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
  document.getElementById("grow-" + qi).classList.toggle("row-done", s.size > 0);
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
function showModal(title, msg, okLabel, cancelLabel) {{
  return new Promise(resolve => {{
    _modalResolve = resolve;
    document.getElementById("modal-title").textContent  = title;
    document.getElementById("modal-msg").textContent    = msg;
    document.getElementById("modal-ok").textContent     = okLabel;
    document.getElementById("modal-cancel").textContent = cancelLabel;
    document.getElementById("modal-overlay").style.display = "flex";
    document.getElementById("modal-cancel").focus();
  }});
}}
function modalOpen()   {{ return document.getElementById("modal-overlay").style.display !== "none"; }}
function modalOk()     {{ document.getElementById("modal-overlay").style.display="none"; if(_modalResolve) _modalResolve(true);  }}
function modalCancel() {{ document.getElementById("modal-overlay").style.display="none"; if(_modalResolve) _modalResolve(false); }}

async function askSubmit() {{
  const done      = Object.values(answers).filter(s=>s&&s.size>0).length;
  const remaining = N - done;
  if (remaining > 0) {{
    const ok = await showModal(T.submit_title, fill(T.submit_msg, {{n: remaining}}),
      T.submit_ok, T.submit_cancel);
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
  document.getElementById("submit-btn").textContent = T.grading;
  if (pybridge) {{
    pybridge.saveNotes(JSON.stringify(notesPayload()));
    pybridge.submitExam(JSON.stringify(payload));
  }}
}}
</script>
<script>{NOTES_JS}{_TOOLS_JS}</script>
<script>
renderQuestions();
renderGrid();
initTools();
startTimer();
</script>
</body>
</html>"""


# ── Toolbar icons: one 16px, 1.6 stroke family ───────────────────────────────

def _icon(d: str) -> str:
    return (f'<svg class="ic" viewBox="0 0 16 16" aria-hidden="true"><path d="{d}"/></svg>')


_ICONS = {
    "pointer": _icon("M4 2.5v10l2.8-2.6 1.9 4.1 1.7-.8-1.9-4h3.8z"),
    "hl":      _icon("M9.8 2.6l3.6 3.6-5.6 5.6H4.2V8.2zM2.5 14h7"),
    "pen":     _icon("M11.2 2.6l2.2 2.2-7.6 7.6-3 .8.8-3zM9.6 4.2l2.2 2.2"),
    "eraser":  _icon("M6.2 13.2L2.8 9.8l6.6-6.6 4.4 4.4-6 5.6M6.2 13.2h7.3M5.4 7.2l4.4 4.4"),
    "undo":    _icon("M5.5 6.5h5a3 3 0 010 6H7.5M5.5 6.5L8 4M5.5 6.5L8 9"),
    "clear":   _icon("M3 4.6h10M6.2 4.6V3h3.6v1.6M4.4 4.6l.7 8.6h5.8l.7-8.6"),
    "minus":   _icon("M4 8h8"),
    "plus":    _icon("M4 8h8M8 4v8"),
}


# ── Booklet tools: highlighter, pen, eraser, undo, zoom (plain string) ───────

_TOOLS_JS = r"""
let tool = "pointer", hlColor = "yellow", penColor = "blue";
let highlights = [], strokes = [], undoStack = [], nextId = 1;
const ZOOMS = [0.7, 0.8, 0.9, 1, 1.1, 1.25, 1.5, 1.75, 2];
let zoomIdx = 3;

const booklet = () => document.getElementById("booklet");
const layer   = () => document.getElementById("ink-layer");

function setTool(t, force) {
  if (!force && t === tool) t = "pointer";   // clicking the active tool puts it down
  tool = t;
  document.body.dataset.tool = t;
  document.body.dataset.hl = hlColor;
  document.querySelectorAll(".tool[data-tool]").forEach(b => {
    const on = b.dataset.tool === t;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", String(on));
  });
  document.querySelectorAll(".sw").forEach(b => {
    const cur = b.dataset.kind === "hl" ? hlColor : penColor;
    b.classList.toggle("picked", b.dataset.color === cur);
  });
  if (t !== "hl") window.getSelection().removeAllRanges();
}

function pickColor(kind, color) {
  if (kind === "hl") hlColor = color; else penColor = color;
  setTool(kind, true);
}

function notesPayload() {
  return {highlights: highlights, strokes: strokes};
}

function undo() {
  const fn = undoStack.pop();
  if (fn) fn();
}

/* Highlighter */
function repaint(list) {
  const seen = new Set();
  list.forEach(h => {
    const key = h.q + ":" + h.part;
    if (seen.has(key)) return;
    seen.add(key);
    const el = document.querySelector(`#qblock-${h.q} [data-part="${h.part}"]`);
    if (el) paintHighlights(el, highlights.filter(x => x.q === h.q && x.part === h.part));
  });
}

function onHighlightUp() {
  if (tool !== "hl") return;
  const sel = window.getSelection();
  if (!sel.rangeCount || sel.isCollapsed) return;
  const range = sel.getRangeAt(0);
  const added = [];
  booklet().querySelectorAll("[data-part]").forEach(el => {
    if (!range.intersectsNode(el)) return;
    const start = el.contains(range.startContainer) ? textOffset(el, range.startContainer, range.startOffset) : 0;
    const end   = el.contains(range.endContainer)   ? textOffset(el, range.endContainer, range.endOffset) : el.textContent.length;
    if (end > start)
      added.push({id: nextId++, q: +el.closest("[data-qi]").dataset.qi, part: el.dataset.part, start, end, color: hlColor});
  });
  sel.removeAllRanges();
  if (!added.length) return;
  highlights.push(...added);
  repaint(added);
  undoStack.push(() => { highlights = highlights.filter(h => !added.includes(h)); repaint(added); });
}

function onHighlightClick(e) {
  if (tool !== "hl" || !window.getSelection().isCollapsed) return;
  const m = e.target.closest("mark.hl");
  if (!m) return;
  const h = highlights.find(x => x.id === +m.dataset.hid);
  if (!h) return;
  highlights = highlights.filter(x => x !== h);
  repaint([h]);
  undoStack.push(() => { highlights.push(h); repaint([h]); });
}

/* Pen + eraser: strokes are stored relative to their question block so the
   results page can redraw them on the same words. */
function toLocal(e) {
  const pt = layer().createSVGPoint();
  pt.x = e.clientX; pt.y = e.clientY;
  const p = pt.matrixTransform(layer().getScreenCTM().inverse());
  return [Math.round(p.x * 10) / 10, Math.round(p.y * 10) / 10];
}

function blockAt(y) {
  const blocks = document.querySelectorAll(".q-block");
  let b = blocks[0];
  blocks.forEach(el => { if (el.offsetTop <= y) b = el; });
  return b;
}

function absPoints(s) {
  const b = document.getElementById("qblock-" + s.q);
  return s.pts.map(([x, y]) => [x + b.offsetLeft, y + b.offsetTop]);
}

function drawStroke(s) {
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("class", "ink-" + s.color);
  path.setAttribute("d", inkPath(absPoints(s)));
  path.dataset.sid = s.id;
  layer().appendChild(path);
}

function removeStroke(s) {
  strokes = strokes.filter(x => x !== s);
  const el = layer().querySelector(`[data-sid="${s.id}"]`);
  if (el) el.remove();
}

let live = null;

// Distance from point p to segment ab.
function segDist(p, a, b) {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const len2 = dx * dx + dy * dy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2)) : 0;
  return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
}

// Erase every stroke within reach of the pointer's path from `from` to `to`.
// A fast swipe moves many pixels between events, so test the whole path.
function eraseAlong(from, to) {
  const steps = Math.max(1, Math.ceil(Math.hypot(to[0] - from[0], to[1] - from[1]) / 3));
  const path = [];
  for (let i = 0; i <= steps; i++)
    path.push([from[0] + (to[0] - from[0]) * i / steps, from[1] + (to[1] - from[1]) * i / steps]);
  strokes.filter(s => {
    const pts = absPoints(s);
    return path.some(p => pts.length === 1
      ? Math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]) < 8
      : pts.slice(1).some((q, i) => segDist(p, pts[i], q) < 8));
  }).forEach(s => {
    removeStroke(s);
    undoStack.push(() => { strokes.push(s); drawStroke(s); });
  });
}

function onInkDown(e) {
  if (tool !== "pen" && tool !== "eraser") return;
  e.preventDefault();
  layer().setPointerCapture(e.pointerId);
  const p = toLocal(e);
  if (tool === "eraser") { live = {erasing: true, last: p}; eraseAlong(p, p); return; }
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("class", "ink-" + penColor);
  layer().appendChild(path);
  live = {pts: [p], path: path, color: penColor};
  path.setAttribute("d", inkPath(live.pts));
}

function onInkMove(e) {
  if (!live) return;
  const p = toLocal(e);
  if (live.erasing) { eraseAlong(live.last, p); live.last = p; return; }
  const last = live.pts[live.pts.length - 1];
  if (Math.hypot(p[0] - last[0], p[1] - last[1]) < 1.2) return;
  live.pts.push(p);
  live.path.setAttribute("d", inkPath(live.pts));
}

function onInkUp() {
  if (!live) return;
  const done = live;
  live = null;
  if (done.erasing) return;
  const b = blockAt(done.pts[0][1]);
  const s = {
    id: nextId++, q: +b.dataset.qi, color: done.color,
    pts: done.pts.map(([x, y]) => [Math.round((x - b.offsetLeft) * 10) / 10, Math.round((y - b.offsetTop) * 10) / 10]),
  };
  done.path.dataset.sid = s.id;
  strokes.push(s);
  undoStack.push(() => removeStroke(s));
}

async function clearDrawings() {
  if (!strokes.length) return;
  const ok = await showModal(T.clear_title, T.clear_msg, T.clear_ok, T.cancel);
  if (!ok) return;
  const removed = strokes.slice();
  removed.forEach(removeStroke);
  undoStack.push(() => removed.forEach(s => { strokes.push(s); drawStroke(s); }));
}

/* Zoom: magnify the whole booklet (no re-wrapping, drawings stay put) */
function applyZoom() {
  const z = ZOOMS[zoomIdx];
  const panel = document.getElementById("left-panel");
  const ratio = panel.scrollTop / Math.max(1, panel.scrollHeight);
  const bk = booklet();
  bk.style.transform = `scale(${z})`;
  const sizer = document.getElementById("booklet-sizer");
  sizer.style.width  = (bk.offsetWidth * z) + "px";
  sizer.style.height = (bk.offsetHeight * z) + "px";
  document.getElementById("sheet").style.zoom = Math.min(z, 1.5);
  document.getElementById("zoom-pct").textContent = Math.round(z * 100) + "%";
  panel.scrollTop = ratio * panel.scrollHeight;
}
function zoomIn()    { zoomIdx = Math.min(zoomIdx + 1, ZOOMS.length - 1); applyZoom(); }
function zoomOut()   { zoomIdx = Math.max(zoomIdx - 1, 0); applyZoom(); }
function resetZoom() { zoomIdx = 3; applyZoom(); }

function onKey(e) {
  if (modalOpen()) { if (e.key === "Escape") modalCancel(); return; }
  if (e.target.closest("input, textarea, select")) return;
  if (e.ctrlKey || e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === "z")                  { e.preventDefault(); undo(); }
    else if (k === "+" || k === "=") { e.preventDefault(); zoomIn(); }
    else if (k === "-")             { e.preventDefault(); zoomOut(); }
    else if (k === "0")             { e.preventDefault(); resetZoom(); }
    return;
  }
  if (e.altKey) return;
  const k = e.key.toLowerCase();
  if (k === "h") setTool("hl");
  else if (k === "p") setTool("pen");
  else if (k === "e") setTool("eraser");
  else if (e.key === "Escape") setTool("pointer", true);
}

function initTools() {
  const bk = booklet();
  bk.addEventListener("mouseup", onHighlightUp);
  bk.addEventListener("click", onHighlightClick);
  const ly = layer();
  ly.addEventListener("pointerdown", onInkDown);
  ly.addEventListener("pointermove", onInkMove);
  ly.addEventListener("pointerup", onInkUp);
  ly.addEventListener("pointercancel", onInkUp);
  document.addEventListener("keydown", onKey);
  setTool("pointer", true);
  applyZoom();
}
"""


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
#left-panel { flex: 1; overflow: auto; position: relative; padding: 0 32px 48px; min-width: 0; }
#booklet-sizer { margin: 0 auto; }
#booklet {
  position: relative; width: 820px; transform-origin: 0 0;
  padding: 52px 64px 64px; font-size: 15px;
}

/* Booklet tools */
#tools {
  position: sticky; top: 0; left: 0; z-index: 30;
  display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px 18px;
  margin: 0 -32px 20px; padding: 10px 16px;
  background: var(--desk); border-bottom: 1px solid #bdbab2;
}
.tgroup { display: flex; align-items: center; gap: 4px; }
.tool {
  display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 10px;
  background: #ecebe7; border: 1px solid #b9b6ae; border-radius: 4px; color: var(--desk-ink);
  font: 13px Arial, sans-serif; cursor: pointer;
}
.tool:hover { background: #fff; }
.tool.active { background: var(--print); border-color: var(--print); color: #fff; }
.tool-sq { width: 32px; padding: 0; justify-content: center; }
#zoom-pct { min-width: 58px; justify-content: center; font-variant-numeric: tabular-nums; }
.ic { width: 16px; height: 16px; flex-shrink: 0; }
.ic path { fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.swatches { display: inline-flex; gap: 3px; margin: 0 8px 0 2px; }
.sw {
  width: 20px; height: 20px; border-radius: 50%; border: 1px solid rgba(0,0,0,.25);
  cursor: pointer; padding: 0;
}
.sw.picked { box-shadow: 0 0 0 2px var(--desk), 0 0 0 4px var(--desk-ink); }
.sw-yellow { background: #fff27a; }
.sw-green  { background: #b4f0c4; }
.sw-pink   { background: #ffc4e1; }
.sw-blue   { background: #1f3a93; }
.sw-red    { background: #d0302a; }

/* Tool modes */
body[data-tool="hl"] #booklet { cursor: text; }
body[data-tool="hl"][data-hl="yellow"] #booklet ::selection { background: #fff27a; }
body[data-tool="hl"][data-hl="green"]  #booklet ::selection { background: #b4f0c4; }
body[data-tool="hl"][data-hl="pink"]   #booklet ::selection { background: #ffc4e1; }
body[data-tool="hl"] mark.hl { cursor: pointer; }
body[data-tool="pen"] #ink-layer,
body[data-tool="eraser"] #ink-layer { pointer-events: all; cursor: crosshair; touch-action: none; }
body[data-tool="eraser"] #ink-layer { cursor: cell; }
#ink-layer { z-index: 5; }

/* Answer sheet side */
/* A strip of desk and a rule always separate the sheet from the booklet,
   even when the zoomed booklet is wider than its panel. */
#right-panel {
  flex: 0 0 auto; overflow: auto; padding: 72px 22px 48px 24px;
  border-left: 1px solid #a9a69e;
}
#sheet { width: 432px; padding: 22px 20px 36px; }
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
  padding: 3px 6px 3px 4px; text-align: left; font-weight: normal;
  white-space: nowrap; cursor: pointer; font-variant-numeric: tabular-nums;
}
.qlabel:hover { text-decoration: underline; text-underline-offset: 2px; }
.tick { width: 11px; height: 11px; margin-right: 3px; vertical-align: -1px; visibility: hidden; }
.tick path { fill: none; stroke: #6f6f6f; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.row-done .tick { visibility: visible; }
.box {
  width: 22px; height: 22px; border: 1.4px solid var(--rule); background: var(--paper);
  display: inline-flex; vertical-align: middle; cursor: pointer; padding: 0;
}
.box:hover { background: #eef1fb; }
.box-na { border-color: #c4c4c4; background: #f2f2f2; cursor: default; }
.box-na:hover { background: #f2f2f2; }
.sheet-rules .box { width: 18px; height: 18px; cursor: default; }

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
