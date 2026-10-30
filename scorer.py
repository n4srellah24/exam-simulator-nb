"""
Scoring engine + results HTML builder.
"""

import html
from datetime import date

import json

from .paper import NOTES_CSS, NOTES_JS, PAPER_CSS, PEN_SVG, fmt_duration, mark_svg

# ── Flag definitions ──────────────────────────────────────────────────────────
FLAG_COLORS = {
    1: ("#ef4444", "Red"),
    2: ("#f97316", "Orange"),
    3: ("#22c55e", "Green"),
    4: ("#3b82f6", "Blue"),
    5: ("#ec4899", "Pink"),
    6: ("#06b6d4", "Turquoise"),
    7: ("#a855f7", "Purple"),
}

# ── Formatting helpers ────────────────────────────────────────────────────────

def _clean_zero(value: float, places: int = 6) -> float:
    rounded = round(float(value), places)
    return 0.0 if abs(rounded) < 10 ** (-places) else rounded


def _fmt_score(value: float) -> str:
    value = _clean_zero(value)
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ── compute_score ─────────────────────────────────────────────────────────────

def compute_score(questions, answers_dict, scoring):
    mode = scoring["mode"]

    question_results = []
    total_earned = 0.0
    total_possible = 0.0

    for i, q in enumerate(questions):
        correct_set = set(q["correct"])
        chosen_set = set(answers_dict.get(str(i), []))

        correct_chosen = correct_set & chosen_set
        wrong_chosen = chosen_set - correct_set

        possible = 1.0
        earned = 0.0

        if not chosen_set:
            status = "skipped"
            earned = 0.0

        elif mode == "raw":
            if chosen_set == correct_set:
                earned, status = 1.0, "correct"
            else:
                earned, status = 0.0, "wrong"

        elif mode == "partial":
            n = len(correct_set)
            step = 1.0 / n
            raw_earned = len(correct_chosen) * step - len(wrong_chosen) * step
            raw_earned = max(-possible, min(possible, raw_earned))
            earned = max(0.0, raw_earned)
            if earned >= 1.0:
                status = "correct"
            elif earned > 0:
                status = "partial"
            else:
                status = "wrong"

        else:  # negative
            n = len(correct_set)
            step = 1.0 / n
            raw_earned = len(correct_chosen) * step - len(wrong_chosen) * step
            earned = max(-possible, min(possible, raw_earned))
            if earned >= 1.0:
                status = "correct"
            elif earned > 0:
                status = "partial"
            else:
                status = "wrong"

        earned = _clean_zero(earned)
        total_earned += earned
        total_possible += possible

        question_results.append({
            "index": i,
            "question": q["question"],
            "options": q["options"],
            "correct": sorted(correct_set),
            "chosen": sorted(chosen_set),
            "status": status,
            "earned": earned,
            "possible": possible,
            "nid": q.get("nid", ""),
            "source": q.get("source", ""),
            "explanation": q.get("explanation", ""),
        })

    total_earned = _clean_zero(total_earned)
    total_possible = _clean_zero(total_possible)
    if mode == "negative":
        total_earned = max(0.0, total_earned)
    pct = _clean_zero((total_earned / total_possible * 100) if total_possible else 0)
    score_20 = _clean_zero(pct / 5)  # maps 0–100% to 0–20

    return {
        "questions": question_results,
        "total_earned": total_earned,
        "total_possible": total_possible,
        "percentage": pct,
        "score_20": score_20,
        "scoring": scoring,
        "n_correct": sum(1 for r in question_results if r["status"] == "correct"),
        "n_partial": sum(1 for r in question_results if r["status"] == "partial"),
        "n_wrong": sum(1 for r in question_results if r["status"] == "wrong"),
        "n_skipped": sum(1 for r in question_results if r["status"] == "skipped"),
    }


# ── build_results_html ────────────────────────────────────────────────────────

STATUS_LABELS = {
    "correct": "Correct",
    "partial": "Partial",
    "wrong": "Wrong",
    "skipped": "Skipped",
}


def _option_html(letter, text, is_correct, is_chosen):
    classes = ["q-opt"]
    if is_correct:
        classes.append("key")
    if is_chosen:
        classes.append("chosen")
    if is_chosen and not is_correct:
        classes.append("bad")
    notes = []
    if is_chosen:
        notes.append("your answer")
    if is_correct:
        notes.append("correct answer")
    sr = f'<span class="sr">({", ".join(notes)})</span>' if notes else ""
    ink = PEN_SVG if is_chosen else ""
    return (
        f'<div class="{" ".join(classes)}">'
        f'<span class="ink">{ink}</span>'
        f'<span class="opt-letter"><span class="lt">{letter}</span>:</span>'
        f'<span class="opt-text" data-part="{letter}">{text}</span>{sr}'
        f'</div>'
    )


def build_results_html(results):
    pct = _clean_zero(results["percentage"])
    score_20 = _clean_zero(results["score_20"])
    exam_name = html.escape(results.get("exam_name", "Exam"))
    today = date.today().strftime("%d/%m/%Y")
    dur = fmt_duration(results.get("timer_seconds"))
    dur_html = f'<span><b>Durée :</b> {dur}</span>' if dur else ""

    if score_20 >= 17:
        grade_label = "Excellent"
    elif score_20 >= 14:
        grade_label = "Good"
    elif score_20 >= 10:
        grade_label = "Pass"
    else:
        grade_label = "Fail"

    score_mode = results["scoring"]["mode"]
    mode_labels = {
        "raw": "All or Nothing",
        "partial": "Partial Positive +",
        "negative": "Partial Negative -",
    }
    mode_label = mode_labels.get(score_mode, "Custom")

    q_blocks = ""
    for r in results["questions"]:
        num = r["index"] + 1
        status = r["status"]
        opts_html = "".join(
            _option_html(letter, text, letter in r["correct"], letter in r["chosen"])
            for letter, text in r["options"].items()
        )

        src_html = f'<div class="q-source">Source : {r["source"]}</div>' if r.get("source") else ""

        expl_html = ""
        if r.get("explanation"):
            expl_html = (
                f'<div class="expl-wrap">'
                f'<button class="expl-toggle" aria-expanded="false" onclick="toggleExpl(this)">'
                f'Show explanation</button>'
                f'<div class="expl-body" hidden>{r["explanation"]}</div>'
                f'</div>'
            )

        label = STATUS_LABELS.get(status, "Skipped")
        q_blocks += (
            f'<div class="r-q" id="qrow-{r["index"]}" data-qi="{r["index"]}" data-status="{status}" '
            f'onclick="toggleRowSelection(event, {r["index"]})">'
            f'<label class="sel" title="Select question {num}">'
            f'<input type="checkbox" class="q-check" data-nid="{r.get("nid", "")}" '
            f'aria-label="Select question {num}" onchange="refreshSelCount()">'
            f'</label>'
            f'<div class="r-body">'
            f'<div class="q-header"><span class="q-num">{num}</span>'
            f'<span class="q-text" data-part="Q">{r["question"]}</span></div>'
            f'<div class="q-opts">{opts_html}</div>{src_html}{expl_html}'
            f'<svg class="ink-layer" width="1" height="1"></svg>'
            f'</div>'
            f'<div class="r-mark" title="{label}">'
            f'{mark_svg(status)}'
            f'<span class="r-score">{_fmt_score(r["earned"])}<small>/{_fmt_score(r["possible"])}</small></span>'
            f'<span class="sr">{label}</span>'
            f'</div>'
            f'</div>'
        )

    flag_opts = ''.join(
        f'<option value="{fnum}">{name}</option>'
        for fnum, (_, name) in FLAG_COLORS.items()
    )

    flag_svg_map = '{' + ','.join(
        f'{fnum}:\'<svg width="14" height="14" viewBox="0 0 24 24" '
        f'xmlns=\\"http://www.w3.org/2000/svg\\" style=\\"vertical-align:middle\\">'
        f'<path fill=\\"{col}\\" d=\\"M5 3v18h2v-7h10l-2-4 2-4H7V3H5z\\"/>'
        f'</svg> {name}\''
        for fnum, (col, name) in FLAG_COLORS.items()
    ) + '}'

    n_q = len(results["questions"])
    notes = results.get("notes") or {}
    has_notes = bool(notes.get("highlights") or notes.get("strokes"))
    notes_json = json.dumps(notes, ensure_ascii=False).replace("</", "<\\/")
    notes_btn = (
        '<button id="notes-toggle" class="notes-btn active" aria-pressed="true" '
        'onclick="toggleNotes()" title="Show or hide your highlights and drawings">'
        '<span>Show my notes</span></button>'
    ) if has_notes else ""

    def filter_btn(status, count, active=False):
        icon = "" if status == "all" else mark_svg(status)
        label = "All" if status == "all" else STATUS_LABELS[status]
        cls = "filt active" if active else "filt"
        return (f'<button class="{cls}" data-filter="{status}" aria-pressed="{str(active).lower()}" '
                f'onclick="filterRows(\'{status}\')">{icon}<span>{label}</span>'
                f'<b>{count}</b></button>')

    filters = filter_btn("all", n_q, True) + filter_btn("correct", results["n_correct"])
    if score_mode != "raw":
        filters += filter_btn("partial", results["n_partial"])
    filters += filter_btn("wrong", results["n_wrong"]) + filter_btn("skipped", results["n_skipped"])

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Results — {exam_name}</title>
<style>
{PAPER_CSS}
{NOTES_CSS}
body.notes-off mark.hl {{ background: transparent; }}
body.notes-off .r-body .ink-layer {{ display: none; }}

#topbar {{
  display: flex; justify-content: space-between; align-items: center; gap: 20px;
  background: var(--bar); color: var(--bar-ink); padding: 10px 24px; flex-shrink: 0;
}}
#topbar h1 {{ font-size: 14px; font-weight: bold; }}
#topbar .sub {{ font-size: 12px; color: var(--bar-soft); margin-left: 12px; font-weight: normal; }}
#top-actions {{ display: flex; gap: 8px; }}
.hdr-btn {{
  padding: 8px 16px; font: bold 13px Arial, sans-serif; border-radius: 4px; cursor: pointer;
}}
.btn-close {{ background: transparent; color: var(--bar-ink); border: 1px solid #475569; }}
.btn-close:hover {{ background: #334155; }}
.btn-another {{ background: var(--accent); color: #fff; border: 1px solid var(--accent); }}
.btn-another:hover {{ background: var(--accent-hover); }}

#toolbar {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px;
  padding: 10px 24px; background: #ecebe7; border-bottom: 1px solid #bdbab2;
  font-size: 13px; flex-shrink: 0;
}}
.tool-group {{ display: flex; align-items: center; gap: 6px; }}
.tool-label {{ font-size: 12px; color: #5a5852; margin-right: 2px; }}
.filt, .notes-btn {{
  display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 11px;
  border: 1px solid #b9b6ae; background: #fff; border-radius: 4px; cursor: pointer;
  font: 13px Arial, sans-serif; color: var(--print);
}}
.filt .mark {{ width: 15px; height: 15px; }}
.filt b {{ font-variant-numeric: tabular-nums; }}
.filt:hover, .notes-btn:hover {{ border-color: #6b6962; }}
.filt.active, .notes-btn.active {{ background: var(--print); border-color: var(--print); color: #fff; }}
.filt.active .mark path {{ stroke: #fff; }}
.act-btn, #flag-select, #tag-input {{
  height: 32px; padding: 0 10px; font: 13px Arial, sans-serif;
  border: 1px solid #b9b6ae; border-radius: 4px; background: #fff; color: var(--print);
}}
.act-btn {{ cursor: pointer; }}
.act-btn:hover {{ border-color: #6b6962; }}
.act-btn-primary {{ background: var(--accent); border-color: var(--accent); color: #fff; font-weight: bold; }}
.act-btn-primary:hover {{ background: var(--accent-hover); border-color: var(--accent-hover); }}
#tag-input {{ width: 170px; }}
#tag-input::placeholder {{ color: #77756e; }}
#sel-count {{ font-weight: bold; font-variant-numeric: tabular-nums; min-width: 82px; }}
#action-feedback {{ font-size: 12px; color: #1f6b33; font-weight: bold; }}

#results-scroll {{ flex: 1; overflow-y: auto; padding: 28px 32px 56px; }}
#corrected {{ width: 890px; margin: 0 auto; padding: 48px 32px 64px; font-size: 15px; }}
#corrected .paper-head, #corrected .legend {{ margin-left: 60px; margin-right: 74px; }}
.head-grid {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; }}
.head-info {{ flex: 1; }}
.note-box {{
  border: 2px solid var(--red-pen); color: var(--red-pen);
  padding: 6px 14px 8px; text-align: center; transform: rotate(-1.5deg); flex-shrink: 0;
}}
.note-label {{ font-size: 12px; font-weight: bold; }}
.note-val {{ font-size: 30px; font-weight: bold; line-height: 1.1; font-variant-numeric: tabular-nums; }}
.note-val small {{ font-size: 15px; }}
.note-sub {{ font-size: 12px; font-variant-numeric: tabular-nums; }}
.legend {{
  display: flex; flex-wrap: wrap; gap: 6px 22px; margin-top: -12px; margin-bottom: 26px;
  font-size: 12px; color: var(--print-soft);
}}
.legend span {{ display: inline-flex; align-items: center; gap: 6px; }}
.legend .ink {{ display: inline-block; width: 14px; height: 14px; }}
.legend .lg-key {{ display: inline-flex; width: 18px; height: 18px; align-items: center; justify-content: center;
  border: 1.6px solid var(--red-pen); border-radius: 50%; color: var(--print); font-size: 11px; }}
.legend .lg-bad {{ text-decoration: line-through; text-decoration-color: var(--red-pen); text-decoration-thickness: 2px; color: var(--print); }}

.r-q {{
  display: grid; grid-template-columns: 60px 692px 74px; align-items: start;
  margin-bottom: 1.35em; border-radius: 3px; cursor: pointer;
}}
.r-q:hover {{ background: #fafaf7; }}
.r-q.row-selected {{ background: #eef2fc; }}
.r-q.row-hidden {{ display: none; }}
.sel {{ display: flex; padding: .2em 0 0 6px; cursor: pointer; }}
.q-check {{ width: 16px; height: 16px; accent-color: var(--accent); cursor: pointer; }}
.r-body {{ position: relative; }}
.r-body .ink-layer {{ z-index: 2; }}
.q-opt {{ position: relative; }}
.q-opt .ink {{ position: absolute; left: -1.5em; top: .25em; width: 1em; height: 1em; }}
.q-opt .lt {{ position: relative; }}
.q-opt.key .lt::before {{
  content: ""; position: absolute; left: 50%; top: 52%; width: 1.5em; height: 1.4em;
  border: 1.6px solid var(--red-pen); border-radius: 50%;
  transform: translate(-50%, -50%) rotate(-8deg);
}}
.q-opt.bad .opt-text {{
  text-decoration: line-through; text-decoration-color: var(--red-pen); text-decoration-thickness: 2px;
}}
.r-mark {{ display: flex; flex-direction: column; align-items: center; gap: 2px; padding-top: .1em; }}
.r-score {{ color: var(--red-pen); font-weight: bold; font-size: 13px; font-variant-numeric: tabular-nums; }}
.r-score small {{ font-size: 11px; }}
.r-q[data-status="skipped"] .r-score {{ color: #6f6f6f; }}

.expl-wrap {{ margin-top: .4em; }}
.expl-toggle {{
  background: none; border: none; padding: 2px 0; cursor: pointer;
  font: bold 13px Arial, sans-serif; color: var(--accent);
  text-decoration: underline; text-underline-offset: 3px;
}}
.expl-toggle:hover {{ color: var(--accent-hover); }}
.expl-body {{
  margin-top: 6px; padding: 10px 14px; font-size: .9em; line-height: 1.6;
  background: #f6f5f1; border: 1px solid #dddbd3; cursor: auto;
}}
.sr {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
</style>
</head>
<body>

<div id="topbar">
  <h1>{exam_name}<span class="sub">Corrected · {mode_label} · {n_q} questions</span></h1>
  <div id="top-actions">
    <button class="hdr-btn btn-close" onclick="finishExam()">Close</button>
    <button class="hdr-btn btn-another" onclick="takeAnotherExam()">Take another exam</button>
  </div>
</div>

<div id="toolbar">
  <div class="tool-group" role="group" aria-label="Show">{filters}</div>
  {notes_btn}
  <div class="tool-group">
    <span id="sel-count">0 selected</span>
    <button class="act-btn" onclick="selectAll()">Select all</button>
    <button class="act-btn" onclick="deselectAll()">Clear</button>
  </div>
  <div class="tool-group">
    <label class="tool-label" for="flag-select">Flag</label>
    <select id="flag-select">{flag_opts}</select>
    <button class="act-btn act-btn-primary" onclick="applyFlag()">Apply flag</button>
  </div>
  <div class="tool-group">
    <label class="tool-label" for="tag-input">Tag</label>
    <input id="tag-input" type="text" placeholder="e.g. needs_review">
    <button class="act-btn act-btn-primary" onclick="applyTag()">Apply tag</button>
  </div>
  <span id="action-feedback" role="status"></span>
</div>

<div id="results-scroll" class="desk">
  <article id="corrected" class="paper">
    <header class="paper-head head-grid">
      <div class="head-info">
        <div class="ph-row"><span><b>Module :</b> {exam_name}</span><span><b>Date :</b> {today}</span></div>
        <div class="ph-row"><span>{n_q} QCM</span>{dur_html}</div>
      </div>
      <div class="note-box">
        <div class="note-label">Note</div>
        <div class="note-val">{_fmt_score(score_20)}<small> / 20</small></div>
        <div class="note-sub">{grade_label} · {_fmt_score(pct)} % · {_fmt_score(results["total_earned"])}/{_fmt_score(results["total_possible"])} pts</div>
      </div>
    </header>
    <div class="legend" aria-hidden="true">
      <span><span class="ink">{PEN_SVG}</span>your answer</span>
      <span><span class="lg-key">A</span>correct answer</span>
      <span><span class="lg-bad">struck</span>wrong choice</span>
    </div>
    {q_blocks}
  </article>
</div>

<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script>{NOTES_JS}</script>
<script>
var NOTES = {notes_json};
var pybridge = null;
var FLAG_SVGS = {flag_svg_map};
var currentFilter = 'all';

new QWebChannel(qt.webChannelTransport, function(ch) {{
  pybridge = ch.objects.pybridge;
}});

function renderNotes() {{
  var hl = NOTES.highlights || [];
  var groups = {{}};
  hl.forEach(function(h) {{ (groups[h.q + ':' + h.part] = groups[h.q + ':' + h.part] || []).push(h); }});
  Object.keys(groups).forEach(function(key) {{
    var h = groups[key][0];
    var el = document.querySelector('#qrow-' + h.q + ' [data-part="' + h.part + '"]');
    if (el) paintHighlights(el, groups[key]);
  }});
  (NOTES.strokes || []).forEach(function(s) {{
    var svg = document.querySelector('#qrow-' + s.q + ' .ink-layer');
    if (!svg) return;
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('class', 'ink-' + s.color);
    path.setAttribute('d', inkPath(s.pts));
    svg.appendChild(path);
  }});
}}

function toggleNotes() {{
  var off = document.body.classList.toggle('notes-off');
  var btn = document.getElementById('notes-toggle');
  btn.classList.toggle('active', !off);
  btn.setAttribute('aria-pressed', String(!off));
}}

function finishExam() {{ if (pybridge) pybridge.closeExam(); }}
function takeAnotherExam() {{ if (pybridge) pybridge.takeAnotherExam(); }}

function toggleExpl(btn) {{
  var body = btn.nextElementSibling;
  var open = !body.hidden;
  body.hidden = open;
  btn.setAttribute('aria-expanded', String(!open));
  btn.textContent = open ? 'Show explanation' : 'Hide explanation';
}}

function toggleRowSelection(event, rowIndex) {{
  if (!event) return;
  if (event.target.closest('button, a, input, label, select, textarea, .expl-body')) return;
  var row = document.getElementById('qrow-' + rowIndex);
  if (!row) return;
  var cb = row.querySelector('.q-check');
  if (!cb) return;
  cb.checked = !cb.checked;
  refreshSelCount();
}}

function filterRows(status) {{
  currentFilter = status;
  document.querySelectorAll('.filt').forEach(function(b) {{
    var on = b.dataset.filter === status;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));
  }});
  document.querySelectorAll('.r-q').forEach(function(q) {{
    q.classList.toggle('row-hidden', !(status === 'all' || q.dataset.status === status));
  }});
  deselectAll();
}}

function refreshSelCount() {{
  var n = document.querySelectorAll('.q-check:checked').length;
  document.getElementById('sel-count').textContent = n + ' selected';
  document.querySelectorAll('.r-q').forEach(function(q) {{
    var cb = q.querySelector('.q-check');
    if (cb) q.classList.toggle('row-selected', cb.checked);
  }});
}}

function selectAll() {{
  document.querySelectorAll('.r-q:not(.row-hidden) .q-check').forEach(function(c) {{
    c.checked = true;
  }});
  refreshSelCount();
}}

function deselectAll() {{
  document.querySelectorAll('.q-check').forEach(function(c) {{ c.checked = false; }});
  refreshSelCount();
}}

function getSelectedNids() {{
  var nids = [];
  document.querySelectorAll('.q-check:checked').forEach(function(cb) {{
    if (cb.dataset.nid) nids.push(cb.dataset.nid);
  }});
  return nids;
}}

function showFeedback(html) {{
  var el = document.getElementById('action-feedback');
  el.innerHTML = html;
  setTimeout(function() {{ el.innerHTML = ''; }}, 3500);
}}

function applyFlag() {{
  var nids = getSelectedNids();
  if (!nids.length) {{ showFeedback('Select at least one question first.'); return; }}
  var flagNum = parseInt(document.getElementById('flag-select').value);
  if (pybridge) {{
    pybridge.flagNotes(JSON.stringify(nids), flagNum);
    var label = FLAG_SVGS[flagNum] || ('Flag ' + flagNum);
    showFeedback(label + ' applied to ' + nids.length + ' card(s).');
  }}
}}

function applyTag() {{
  var nids = getSelectedNids();
  if (!nids.length) {{ showFeedback('Select at least one question first.'); return; }}
  var tag = document.getElementById('tag-input').value.trim();
  if (!tag) {{ showFeedback('Type a tag name first.'); return; }}
  if (pybridge) {{
    pybridge.tagNotes(JSON.stringify(nids), tag);
    showFeedback('Tagged ' + nids.length + ' card(s): ' + tag);
  }}
}}

renderNotes();
</script>
</body>
</html>"""
