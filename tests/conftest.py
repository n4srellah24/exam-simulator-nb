"""
Test harness: a real Anki collection, the real add-on package and a real
Qt WebEngine window, running headless. Only Anki's main window (`mw`) is a
stand-in, since there is no Anki profile manager or main UI under test.
"""

import importlib
import importlib.util
import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: F401  (must load before QApplication)
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = "exam_simulator"
NOTE_TYPE = "MCQ-NB"
FIELDS = ["Question", "option_1 (A)", "option_2 (B)", "option_3 (C)",
          "option_4 (D)", "option_5 (E)", "Ans", "Source", "Explanation"]


# ── Qt + Anki ────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv[:1])
    yield app
    # Web pages must be gone before the web engine profile shuts down.
    from PyQt6 import sip
    for w in QApplication.allWidgets():
        if isinstance(w, QWebEngineView) and not sip.isdeleted(w):
            sip.delete(w.page())
    for w in QApplication.topLevelWidgets():
        if not sip.isdeleted(w):
            sip.delete(w)
    QApplication.processEvents()


def _make_note_type(col):
    mm = col.models
    m = mm.new(NOTE_TYPE)
    for f in FIELDS:
        mm.add_field(m, mm.new_field(f))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Question}}"
    t["afmt"] = "{{FrontSide}}<hr>{{Ans}}"
    mm.add_template(m, t)
    mm.add(m)
    return mm.by_name(NOTE_TYPE)


def add_mcq(col, deck, question, options, ans, source="", explanation="", tags=()):
    m = col.models.by_name(NOTE_TYPE)
    note = col.new_note(m)
    note["Question"] = question
    for i, text in enumerate(options[:5]):
        note[FIELDS[1 + i]] = text
    note["Ans"] = ans
    note["Source"] = source
    note["Explanation"] = explanation
    for t in tags:
        note.add_tag(t)
    col.add_note(note, col.decks.id(deck))
    return note.id


@pytest.fixture(scope="session")
def profile_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("profile")


@pytest.fixture(scope="session")
def col(profile_dir):
    from anki.collection import Collection
    c = Collection(str(profile_dir / "collection.anki2"))
    _make_note_type(c)
    opts = ["Option un", "Option deux", "Option trois", "Option quatre", "Option cinq"]
    for i in range(20):
        add_mcq(c, "Gastro::Colon", f"Colon question {i + 1} :", opts, "AC",
                source=f"Q{i + 1} P2021 A", tags=("colon",))
    for i in range(12):
        add_mcq(c, "Gastro::Foie", f"Foie question {i + 1} :", opts, "2",
                source=f"Q{i + 1} P2022 B", tags=("foie", "hard"),
                explanation="<b>Le foie</b> est un organe.")
    for i in range(8):
        add_mcq(c, "Cardio", f"Cardio question {i + 1} :", opts[:4], "D",
                tags=("cardio",))
    yield c
    c.close()


@pytest.fixture(scope="session")
def mw(qapp, col, profile_dir):
    import aqt
    # Anki's mw is a QMainWindow; the add-on parents Qt objects to it.
    fake = QMainWindow()
    fake.col = col
    fake.pm = SimpleNamespace(profileFolder=lambda: str(profile_dir))
    fake.form = SimpleNamespace(menuTools=QMenu(fake))
    fake.reset = lambda: None
    aqt.mw = fake
    return fake


@pytest.fixture(scope="session")
def addon(mw):
    """Load the add-on folder as a package, exactly as Anki imports it."""
    spec = importlib.util.spec_from_file_location(
        PKG, REPO / "__init__.py", submodule_search_locations=[str(REPO)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PKG] = module
    spec.loader.exec_module(module)
    return SimpleNamespace(
        package=module,
        scorer=importlib.import_module(PKG + ".scorer"),
        launcher=importlib.import_module(PKG + ".launcher"),
        history=importlib.import_module(PKG + ".history_store"),
        exam_window=importlib.import_module(PKG + ".exam_window"),
        i18n=importlib.import_module(PKG + ".i18n"),
    )


@pytest.fixture
def clean_history(profile_dir):
    path = profile_dir / "exam_simulator_history.json"
    if path.exists():
        path.unlink()
    yield path
    if path.exists():
        path.unlink()


@pytest.fixture
def questions(addon, col):
    """All valid questions in the collection, in a stable order, with nids."""
    out = []
    for nid in sorted(col.find_notes(f'note:"{NOTE_TYPE}"')):
        q = addon.launcher._parse_note(col.get_note(nid), NOTE_TYPE)
        if q:
            q["nid"] = nid
            out.append(q)
    return out


# ── Driving the web view ─────────────────────────────────────────────────────

def wait_until(pred, timeout=15.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        try:
            if pred():
                return True
        except Exception:
            pass
        time.sleep(0.01)
    return False


def js(view, code, timeout=15.0):
    """Run JavaScript and return its result.

    Qt drops the callback when the page navigates mid-call (exam → results).
    open_exam counts finished page loads on view._loads, so if a new page
    finishes loading while we wait, run the script again on that page.
    """
    box = {}
    gen = getattr(view, "_loads", [0])[0]
    view.page().runJavaScript(code, lambda r: box.setdefault("r", r))
    end = time.time() + timeout
    while time.time() < end and "r" not in box:
        QApplication.processEvents()
        now = getattr(view, "_loads", [0])[0]
        if now != gen:
            gen = now
            view.page().runJavaScript(code, lambda r: box.setdefault("r", r))
        time.sleep(0.005)
    assert "r" in box, f"JavaScript timed out: {code}"
    return box["r"]


def mouse(view, kind, x, y, pressed):
    w = view.focusProxy() or view
    p = QPointF(x, y)
    button = Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton
    buttons = Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, p, w.mapToGlobal(p), button, buttons, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(w, ev)
    QApplication.processEvents()


def drag(view, points):
    """Press at the first point, move through the rest, release at the last."""
    (x0, y0), rest = points[0], points[1:]
    mouse(view, QEvent.Type.MouseMove, x0, y0, False)
    mouse(view, QEvent.Type.MouseButtonPress, x0, y0, True)
    for x, y in rest:
        mouse(view, QEvent.Type.MouseMove, x, y, True)
        time.sleep(0.005)
    xl, yl = points[-1]
    mouse(view, QEvent.Type.MouseButtonRelease, xl, yl, False)
    js(view, "1")  # let the page process the queued input


def key(view, qt_key, text, modifiers=Qt.KeyboardModifier.NoModifier):
    w = view.focusProxy() or view
    for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
        QApplication.sendEvent(w, QKeyEvent(kind, qt_key, modifiers, text))
    js(view, "1")


def rect(view, selector):
    r = js(view, f"""(() => {{ const e = document.querySelector({selector!r});
        if (!e) return null; const b = e.getBoundingClientRect();
        return [b.left, b.top, b.width, b.height]; }})()""")
    assert r, f"element not found: {selector}"
    return r


@pytest.fixture
def open_exam(qapp, addon, mw):
    windows = []

    def _open(qs, timer_seconds=0, mode="partial", name="Gastro", save_history=False):
        win = addon.exam_window.ExamWindow(None, qs, timer_seconds, {"mode": mode},
                                           name, save_history=save_history)
        view = win._web
        # Count page loads from the start, so js() can tell a real exam →
        # results navigation from the exam page's own (sometimes late) load.
        view._loads = [0]
        view.loadFinished.connect(lambda ok: view._loads.__setitem__(0, view._loads[0] + 1))
        win.resize(1600, 900)
        win.show()
        windows.append(win)
        assert wait_until(lambda: view._loads[0] >= 1), "exam page never finished loading"
        assert wait_until(lambda: js(view, "typeof N !== 'undefined' && document.querySelectorAll('.q-block').length") == len(qs)), \
            "exam page did not render its questions"
        assert wait_until(lambda: js(view, "pybridge !== null")), "Python bridge never connected"
        return win, view

    yield _open
    for w in windows:
        w.close()
    for _ in range(10):
        QApplication.processEvents()
        time.sleep(0.01)
