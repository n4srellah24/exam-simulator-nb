"""End to end in a real Qt WebEngine window: exam paper, tools, submit, results."""

import json

from PyQt6.QtCore import Qt

from conftest import drag, js, key, rect, wait_until


def results_loaded(view):
    return wait_until(lambda: js(view, "document.title").startswith("Results"))


# ── Paper layout ─────────────────────────────────────────────────────────────

def test_booklet_and_answer_sheet_layout(open_exam, questions):
    win, view = open_exam(questions)
    assert js(view, "document.querySelectorAll('#sheet .block').length") == 4
    cols = js(view, """[...document.querySelectorAll('.sheet-col')].map(c =>
        [...c.querySelectorAll('.qlabel')].map(l => l.textContent.trim()))""")
    assert cols[0][:1] == ["Q1"] and cols[0][-1] == "Q20"
    assert cols[1][:1] == ["Q21"] and cols[1][-1] == "Q40"
    assert js(view, "document.querySelector('#sheet .comb-label').textContent") == "Module"
    assert js(view, "document.querySelectorAll('#sheet .comb').length") == 1
    # wording per language is covered in test_i18n.py
    assert "Date" in js(view, "document.querySelector('#booklet .paper-head').textContent")
    # 4-option questions show a disabled E box
    assert js(view, "!!document.querySelector('#grow-39 .box-na')")


def test_booklet_and_sheet_are_separate_panes(open_exam, questions):
    win, view = open_exam(questions)
    js(view, "document.getElementById('left-panel').scrollTop = 1e6")
    assert js(view, "document.getElementById('left-panel').scrollTop") > 1000
    assert js(view, "document.getElementById('right-panel').scrollTop") == 0
    booklet = rect(view, "#left-panel")
    sheet = rect(view, "#right-panel")
    assert booklet[0] + booklet[2] <= sheet[0]


def test_html_in_explanation_cannot_break_the_page(open_exam, questions):
    qs = [dict(q) for q in questions[:3]]
    qs[0]["explanation"] = "voir </script><script>window.HACKED = 1</script>"
    win, view = open_exam(qs)
    assert js(view, "typeof window.HACKED") == "undefined"


# ── Answer sheet ─────────────────────────────────────────────────────────────

def test_marking_and_unmarking_boxes(open_exam, questions):
    win, view = open_exam(questions)
    x, y, w, h = rect(view, "#b-0-A")
    drag(view, [(x + w / 2, y + h / 2)])
    assert js(view, "document.getElementById('b-0-A').getAttribute('aria-checked')") == "true"
    assert js(view, "!!document.querySelector('#b-0-A svg.pen')")
    assert js(view, "document.getElementById('grow-0').classList.contains('row-done')")
    assert js(view, "document.getElementById('ans-count').textContent") == "1"
    drag(view, [(x + w / 2, y + h / 2)])
    assert js(view, "document.getElementById('b-0-A').getAttribute('aria-checked')") == "false"
    assert not js(view, "document.getElementById('grow-0').classList.contains('row-done')")
    assert js(view, "document.getElementById('ans-count').textContent") == "0"


def test_question_label_jumps_to_question(open_exam, questions):
    win, view = open_exam(questions)
    js(view, "document.querySelector('#grow-30 .qlabel').click()")
    assert wait_until(lambda: abs(js(view, "document.getElementById('qblock-30').getBoundingClientRect().top") -
                                  js(view, "document.getElementById('left-panel').getBoundingClientRect().top")) < 120)


# ── Highlighter ──────────────────────────────────────────────────────────────

def test_highlight_by_dragging_then_remove_and_undo(open_exam, questions):
    win, view = open_exam(questions)
    key(view, Qt.Key.Key_H, "h")
    assert js(view, "document.body.dataset.tool") == "hl"
    x, y, w, h = rect(view, '#qblock-0 [data-part="B"]')
    drag(view, [(x + 1, y + h / 2), (x + w / 2, y + h / 2), (x + w - 1, y + h / 2)])
    assert js(view, "highlights.length") == 1
    assert js(view, "document.querySelectorAll('#qblock-0 mark.hl-yellow').length") >= 1

    js(view, "pickColor('hl', 'pink')")
    x, y, w, h = rect(view, '#qblock-1 [data-part="Q"]')
    drag(view, [(x + 1, y + h / 2), (x + w - 1, y + h / 2)])
    assert js(view, "document.querySelectorAll('#qblock-1 mark.hl-pink').length") >= 1

    mx, my, mw_, mh = rect(view, "#qblock-1 mark.hl")
    drag(view, [(mx + mw_ / 2, my + mh / 2)])
    assert js(view, "highlights.length") == 1
    assert js(view, "document.querySelectorAll('#qblock-1 mark.hl').length") == 0
    key(view, Qt.Key.Key_Z, "z", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "highlights.length") == 2


# ── Pen, eraser, clear ───────────────────────────────────────────────────────

def test_pen_eraser_undo_and_clear(open_exam, questions):
    win, view = open_exam(questions)
    key(view, Qt.Key.Key_P, "p")
    x, y, w, h = rect(view, "#qblock-2")
    drag(view, [(x + 40 + i * 6, y + 20 + (i % 3) * 4) for i in range(15)])
    drag(view, [(x + 40 + i * 6, y + 90) for i in range(15)])
    assert js(view, "strokes.length") == 2
    assert js(view, "document.querySelectorAll('#ink-layer path').length") == 2
    assert js(view, "strokes[0].q") == 2

    key(view, Qt.Key.Key_E, "e")
    drag(view, [(x + 70, y + 80), (x + 70, y + 100)])
    assert js(view, "strokes.length") == 1
    key(view, Qt.Key.Key_Z, "z", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "strokes.length") == 2

    js(view, "clearDrawings()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "strokes.length") == 0)
    assert js(view, "document.querySelectorAll('#ink-layer path').length") == 0
    key(view, Qt.Key.Key_Z, "z", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "document.querySelectorAll('#ink-layer path').length") == 2


def test_pen_does_not_change_answers_or_select_text(open_exam, questions):
    win, view = open_exam(questions)
    key(view, Qt.Key.Key_P, "p")
    x, y, w, h = rect(view, '#qblock-0 [data-part="A"]')
    drag(view, [(x, y + h / 2), (x + w, y + h / 2)])
    assert js(view, "highlights.length") == 0
    assert js(view, "window.getSelection().isCollapsed")
    assert js(view, "document.getElementById('ans-count').textContent") == "0"


# ── Zoom ─────────────────────────────────────────────────────────────────────

def test_zoom_magnifies_without_rewrapping(open_exam, questions):
    win, view = open_exam(questions)
    before = js(view, "document.querySelector('#qblock-0 .q-header').offsetHeight")
    w0 = rect(view, "#booklet")[2]
    key(view, Qt.Key.Key_Equal, "=", Qt.KeyboardModifier.ControlModifier)
    key(view, Qt.Key.Key_Equal, "=", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "document.getElementById('zoom-pct').textContent") == "125%"
    assert abs(rect(view, "#booklet")[2] - w0 * 1.25) < 2
    assert js(view, "document.querySelector('#qblock-0 .q-header').offsetHeight") == before
    assert float(js(view, "getComputedStyle(document.getElementById('sheet')).zoom")) == 1
    key(view, Qt.Key.Key_Minus, "-", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "document.getElementById('zoom-pct').textContent") == "110%"
    key(view, Qt.Key.Key_0, "0", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "document.getElementById('zoom-pct').textContent") == "100%"
    js(view, "document.getElementById('zoom-pct').click()")
    assert js(view, "document.getElementById('zoom-pct').textContent") == "100%"


def test_drawing_stays_on_its_question_when_zoomed(open_exam, questions):
    win, view = open_exam(questions)
    key(view, Qt.Key.Key_P, "p")
    x, y, w, h = rect(view, '#qblock-0 [data-part="C"]')
    drag(view, [(x + i * 5, y + h / 2) for i in range(20)])
    stroke_before = js(view, "JSON.stringify(strokes)")
    key(view, Qt.Key.Key_Equal, "=", Qt.KeyboardModifier.ControlModifier)
    key(view, Qt.Key.Key_Equal, "=", Qt.KeyboardModifier.ControlModifier)
    p = rect(view, "#ink-layer path")
    t = rect(view, '#qblock-0 [data-part="C"]')
    assert abs((p[1] + p[3] / 2) - (t[1] + t[3] / 2)) < 6
    assert js(view, "JSON.stringify(strokes)") == stroke_before


# ── Submit → results ─────────────────────────────────────────────────────────

def answer(view, qi, letters):
    for l in letters:
        js(view, f"document.getElementById('b-{qi}-{l}').click()")


def submit(view):
    js(view, "document.getElementById('submit-btn').click()")
    if wait_until(lambda: js(view, "modalOpen()"), 2):
        js(view, "document.getElementById('modal-ok').click()")
    assert results_loaded(view), "results page never appeared"


def test_unanswered_warning_can_be_cancelled(open_exam, questions):
    win, view = open_exam(questions)
    js(view, "document.getElementById('submit-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    assert "40 question(s)" in js(view, "document.getElementById('modal-msg').textContent")
    js(view, "document.getElementById('modal-cancel').click()")
    assert not js(view, "modalOpen()")
    assert js(view, "document.title").startswith("Exam")


def test_full_exam_to_results_with_notes(open_exam, questions, clean_history, col):
    qs = questions[:3] + questions[20:22]       # Colon AC ×3, Foie B ×2
    win, view = open_exam(qs, mode="partial", name="Mock_E2E", save_history=True)
    answer(view, 0, "AC")      # correct
    answer(view, 1, "A")       # partial ½
    answer(view, 3, "C")       # wrong
    answer(view, 4, "B")       # correct
    js(view, "pickColor('hl','green')")
    x, y, w, h = rect(view, '#qblock-0 [data-part="Q"]')
    drag(view, [(x + 1, y + h / 2), (x + w - 1, y + h / 2)])
    key(view, Qt.Key.Key_P, "p")
    bx, by, bw, bh = rect(view, "#qblock-1")
    drag(view, [(bx + 300 + i * 4, by + 10) for i in range(10)])
    assert js(view, "highlights.length") == 1 and js(view, "strokes.length") == 1

    submit(view)
    assert js(view, "document.querySelector('.note-val').textContent").startswith("10")
    counts = js(view, """Object.fromEntries([...document.querySelectorAll('.filt')]
        .map(b => [b.dataset.filter, +b.querySelector('b').textContent]))""")
    assert counts == {"all": 5, "correct": 2, "partial": 1, "wrong": 1, "skipped": 1}
    assert js(view, "document.querySelectorAll('#qrow-0 mark.hl-green').length") >= 1
    assert js(view, "document.querySelectorAll('#qrow-1 .ink-layer path').length") == 1
    assert js(view, "document.querySelectorAll('#qrow-0 .q-opt.key').length") == 2
    assert js(view, "document.querySelectorAll('#qrow-3 .q-opt.bad').length") == 1

    js(view, "document.getElementById('notes-toggle').click()")
    assert js(view, "getComputedStyle(document.querySelector('#qrow-1 .ink-layer')).display") == "none"
    assert js(view, "getComputedStyle(document.querySelector('#qrow-0 mark.hl')).backgroundColor") == "rgba(0, 0, 0, 0)"
    js(view, "document.getElementById('notes-toggle').click()")
    assert js(view, "getComputedStyle(document.querySelector('#qrow-1 .ink-layer')).display") != "none"

    js(view, "filterRows('wrong')")
    assert js(view, "document.querySelectorAll('.r-q:not(.row-hidden)').length") == 1

    history = json.loads(clean_history.read_text(encoding="utf-8"))
    assert history["entries"][0]["exam_name"] == "Mock_E2E"
    assert history["entries"][0]["note_ids"] == sorted(q["nid"] for q in qs)


def test_notes_line_up_between_exam_and_results(open_exam, questions):
    qs = questions[:2]
    win, view = open_exam(qs)
    key(view, Qt.Key.Key_P, "p")
    t = rect(view, '#qblock-1 [data-part="D"]')
    drag(view, [(t[0] + i * 5, t[1] + t[3] / 2) for i in range(20)])
    key(view, Qt.Key.Key_Escape, "")
    p, q = rect(view, "#ink-layer path"), rect(view, '#qblock-1 .q-header')
    exam_offset = (p[0] - q[0], p[1] - q[1])
    submit(view)
    p, q = rect(view, "#qrow-1 .ink-layer path"), rect(view, '#qrow-1 .q-header')
    assert abs((p[0] - q[0]) - exam_offset[0]) < 2
    assert abs((p[1] - q[1]) - exam_offset[1]) < 2


def test_no_notes_toggle_without_notes(open_exam, questions):
    win, view = open_exam(questions[:2])
    submit(view)
    assert js(view, "document.getElementById('notes-toggle')") is None


def test_flag_and_tag_from_results_update_real_notes(open_exam, questions, col):
    qs = questions[30:33]
    win, view = open_exam(qs)
    submit(view)
    js(view, "document.querySelectorAll('.q-check')[0].click(); document.querySelectorAll('.q-check')[2].click()")
    assert js(view, "document.getElementById('sel-count').textContent") == "2 selected"
    js(view, "document.getElementById('flag-select').value = '3'; applyFlag()")
    js(view, "document.getElementById('tag-input').value = 'to_review'; applyTag()")
    picked = [qs[0]["nid"], qs[2]["nid"]]
    assert wait_until(lambda: all(col.get_note(n).cards()[0].user_flag() == 3 for n in picked)), "flag not applied"
    assert wait_until(lambda: all("to_review" in col.get_note(n).tags for n in picked)), "tag not applied"
    assert col.get_note(qs[1]["nid"]).cards()[0].user_flag() == 0
    assert "to_review" not in col.get_note(qs[1]["nid"]).tags


def test_timer_runs_out_and_submits(open_exam, questions):
    win, view = open_exam(questions[:3], timer_seconds=2)
    assert js(view, "document.getElementById('timer-text').textContent") in ("00:02", "00:01")
    assert results_loaded(view)
