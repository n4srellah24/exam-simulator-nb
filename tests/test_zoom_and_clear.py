"""Separate booklet / answer-sheet zoom, and clearing highlights."""

from PyQt6.QtCore import QEvent, Qt

from conftest import drag, js, key, mouse, rect, wait_until


def pct(view, sel):
    return js(view, f"document.querySelector({sel!r}).textContent.trim()")


def sheet_zoom(view):
    return float(js(view, "getComputedStyle(document.getElementById('sheet')).zoom"))


def booklet_scale(view):
    return rect(view, "#booklet")[2] / js(view, "document.getElementById('booklet').offsetWidth")


def hover(view, selector):
    x, y, w, h = rect(view, selector)
    mouse(view, QEvent.Type.MouseMove, x + w / 2, y + min(h / 2, 200), False)
    js(view, "1")


# ── Zoom ─────────────────────────────────────────────────────────────────────

def test_booklet_zoom_buttons_leave_the_sheet_alone(open_exam, questions):
    win, view = open_exam(questions)
    js(view, "zoomIn(); zoomIn()")
    assert pct(view, "#zoom-pct") == "125%"
    assert abs(booklet_scale(view) - 1.25) < 0.01
    assert sheet_zoom(view) == 1
    assert pct(view, "#sheet-zoom-pct") == "100%"


def test_sheet_has_its_own_zoom(open_exam, questions):
    win, view = open_exam(questions)
    w0 = rect(view, "#b-0-A")[2]
    js(view, "document.getElementById('sheet-zoom-in').click()")
    js(view, "document.getElementById('sheet-zoom-in').click()")
    assert pct(view, "#sheet-zoom-pct") == "125%"
    assert abs(sheet_zoom(view) - 1.25) < 0.001
    assert abs(rect(view, "#b-0-A")[2] - w0 * 1.25) < 1.5
    assert pct(view, "#zoom-pct") == "100%"
    assert abs(booklet_scale(view) - 1) < 0.01
    js(view, "document.getElementById('sheet-zoom-out').click()")
    assert pct(view, "#sheet-zoom-pct") == "110%"
    js(view, "document.getElementById('sheet-zoom-pct').click()")
    assert pct(view, "#sheet-zoom-pct") == "100%"
    assert sheet_zoom(view) == 1


def test_sheet_zoom_limits(open_exam, questions):
    win, view = open_exam(questions)
    for _ in range(15):
        js(view, "document.getElementById('sheet-zoom-in').click()")
    assert pct(view, "#sheet-zoom-pct") == "200%"
    for _ in range(15):
        js(view, "document.getElementById('sheet-zoom-out').click()")
    assert pct(view, "#sheet-zoom-pct") == "70%"


def test_zoomed_sheet_boxes_still_take_clicks(open_exam, questions):
    win, view = open_exam(questions)
    for _ in range(3):
        js(view, "document.getElementById('sheet-zoom-in').click()")
    x, y, w, h = rect(view, "#b-1-C")
    drag(view, [(x + w / 2, y + h / 2)])
    assert js(view, "document.getElementById('b-1-C').getAttribute('aria-checked')") == "true"
    assert js(view, "document.getElementById('ans-count').textContent") == "1"


def test_keyboard_zooms_the_side_under_the_mouse(open_exam, questions):
    win, view = open_exam(questions)
    ctrl = Qt.KeyboardModifier.ControlModifier
    hover(view, "#sheet")
    key(view, Qt.Key.Key_Equal, "=", ctrl)
    assert pct(view, "#sheet-zoom-pct") == "110%"
    assert pct(view, "#zoom-pct") == "100%"
    hover(view, "#booklet")
    key(view, Qt.Key.Key_Equal, "=", ctrl)
    key(view, Qt.Key.Key_Equal, "=", ctrl)
    assert pct(view, "#zoom-pct") == "125%"
    assert pct(view, "#sheet-zoom-pct") == "110%"
    hover(view, "#sheet")
    key(view, Qt.Key.Key_0, "0", ctrl)
    assert pct(view, "#sheet-zoom-pct") == "100%"
    assert pct(view, "#zoom-pct") == "125%"
    key(view, Qt.Key.Key_Minus, "-", ctrl)
    assert pct(view, "#sheet-zoom-pct") == "90%"


# ── Clear highlights ─────────────────────────────────────────────────────────

def highlight(view, selector):
    x, y, w, h = rect(view, selector)
    drag(view, [(x + 1, y + h / 2), (x + w - 1, y + h / 2)])


def test_clear_highlights_keeps_drawings_and_can_be_undone(open_exam, questions):
    win, view = open_exam(questions)
    key(view, Qt.Key.Key_H, "h")
    highlight(view, '#qblock-0 [data-part="B"]')
    highlight(view, '#qblock-1 [data-part="Q"]')
    key(view, Qt.Key.Key_P, "p")
    x, y, w, h = rect(view, "#qblock-2")
    drag(view, [(x + 40 + i * 6, y + 20) for i in range(12)])
    assert js(view, "highlights.length") == 2 and js(view, "strokes.length") == 1

    js(view, "document.getElementById('clear-hl-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-cancel').click()")
    assert js(view, "highlights.length") == 2

    js(view, "document.getElementById('clear-hl-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "highlights.length") == 0)
    assert js(view, "document.querySelectorAll('#booklet mark.hl').length") == 0
    assert js(view, "strokes.length") == 1

    key(view, Qt.Key.Key_Z, "z", Qt.KeyboardModifier.ControlModifier)
    assert js(view, "highlights.length") == 2
    assert js(view, "document.querySelectorAll('#booklet mark.hl').length") >= 2


def test_clear_highlights_with_none_asks_nothing(open_exam, questions):
    win, view = open_exam(questions)
    js(view, "document.getElementById('clear-hl-btn').click()")
    assert not wait_until(lambda: js(view, "modalOpen()"), 0.5)


def test_cleared_highlights_do_not_reach_results(open_exam, questions):
    win, view = open_exam(questions[:2])
    key(view, Qt.Key.Key_H, "h")
    highlight(view, '#qblock-0 [data-part="Q"]')
    js(view, "document.getElementById('clear-hl-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "highlights.length") == 0)
    js(view, "document.getElementById('submit-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "document.title").startswith("Results"))
    assert js(view, "document.querySelectorAll('mark.hl').length") == 0
