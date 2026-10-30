"""The add-on follows Anki's interface language: French for fr*, else English."""

import re
from datetime import date

import pytest
from anki import lang as anki_lang

from conftest import js, wait_until


@pytest.fixture
def ui(monkeypatch):
    """Switch Anki's interface language the way Anki stores it."""
    return lambda code: monkeypatch.setattr(anki_lang, "current_lang", code)


# ── Detection and formats ────────────────────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    ("fr", "fr"), ("fr-CA", "fr"), ("fr_FR", "fr"), ("FR", "fr"),
    ("en", "en"), ("en-GB", "en"), ("ar", "en"), ("es", "en"), ("", "en"), (None, "en"),
])
def test_language_follows_anki(addon, ui, code, expected):
    ui(code)
    assert addon.i18n.lang() == expected


def test_language_is_read_each_time(addon, ui):
    ui("fr")
    assert addon.i18n.t("submit") == "Rendre la copie"
    ui("en")
    assert addon.i18n.t("submit") == "Submit Exam"


def test_every_string_exists_in_both_languages(addon):
    en, fr = addon.i18n.STRINGS["en"], addon.i18n.STRINGS["fr"]
    assert set(en) == set(fr)
    assert all(v.strip() for v in list(en.values()) + list(fr.values()))


def test_number_percent_and_date_formats(addon, ui):
    i = addon.i18n
    ui("fr")
    assert i.fmt_num(16.17) == "16,17"
    assert i.fmt_num(10.0) == "10"
    assert i.fmt_num(2 / 3) == "0,67"
    assert i.fmt_pct(80.83) == "80,83 %"
    assert i.fmt_date(date(2026, 10, 30)) == "30/10/2026"
    ui("en")
    assert i.fmt_num(16.17) == "16.17"
    assert i.fmt_num(10.0) == "10"
    assert i.fmt_pct(80.83) == "80.83%"
    assert i.fmt_date(date(2026, 10, 30)) == "30 Oct 2026"
    assert i.fmt_date(date(2026, 3, 5)) == "5 Mar 2026"


# ── Results page ─────────────────────────────────────────────────────────────

def _results(addon):
    qs = [{"question": "Q", "options": {"A": "a", "B": "b"}, "correct": ["A"], "nid": n}
          for n in range(8)]
    answers = {str(i): ["A"] for i in range(3)} | {str(i): ["B"] for i in range(3, 8)}
    r = addon.scorer.compute_score(qs, answers, {"mode": "partial"})
    r["exam_name"] = "Gastro"
    r["timer_seconds"] = 5400
    return addon.scorer.build_results_html(r)


def test_results_page_in_french(addon, ui):
    ui("fr")
    page = _results(addon)
    assert '<html lang="fr">' in page
    assert "<title>Résultats — Gastro</title>" in page
    assert 'class="note-val">7,5<small> / 20</small>' in page
    assert "37,5 %" in page
    for word in ("Ajourné", "Fermer", "Nouvel examen", "Tout sélectionner",
                 "Juste", "Partiel", "Faux", "Sans réponse", "Partiel positif +",
                 "Durée :", "8 QCM", "votre réponse", "bonne réponse"):
        assert word in page, word
    for word in ("Close", "Take another exam", "Select all", "Skipped", "your answer"):
        assert word not in page, word


def test_results_page_in_english(addon, ui):
    ui("en")
    page = _results(addon)
    assert '<html lang="en">' in page
    assert "<title>Results — Gastro</title>" in page
    assert 'class="note-val">7.5<small> / 20</small>' in page
    assert "37.5%" in page
    for word in ("Fail", "Close", "Take another exam", "Select all", "Correct",
                 "Partial", "Wrong", "Skipped", "Partial Positive +",
                 "Duration:", "8 MCQs", "your answer", "correct answer"):
        assert word in page, word
    for word in ("Ajourné", "Fermer", "Durée", "QCM", "Consignes"):
        assert word not in page, word


# ── Exam window ──────────────────────────────────────────────────────────────

def _texts(view):
    return js(view, """({
        lang: document.documentElement.lang,
        submit: document.getElementById('submit-btn').textContent.trim(),
        progress: document.getElementById('progress').textContent.trim(),
        head: document.querySelector('#booklet .paper-head').textContent.replace(/\\s+/g, ' ').trim(),
        rules: document.querySelector('.sheet-rules').textContent.replace(/\\s+/g, ' ').trim(),
        tools: [...document.querySelectorAll('#tools .tool span')].map(s => s.textContent.trim()),
        sheet: document.getElementById('sheet').getAttribute('aria-label'),
        comb: document.querySelector('#sheet .comb-label').textContent,
    })""")


def test_exam_window_in_french(open_exam, questions, ui):
    ui("fr")
    win, view = open_exam(questions, timer_seconds=5400)
    t = _texts(view)
    assert win.windowTitle().startswith("Simulateur d'examen")
    assert t["lang"] == "fr"
    assert t["submit"] == "Rendre la copie"
    assert t["progress"] == "0 / 40 répondues"
    assert re.search(r"Module : Gastro Date : \d\d/\d\d/\d{4} 40 QCM Durée : 1h30", t["head"]), t["head"]
    assert t["rules"].startswith("Consignes Cochez d'une croix") and "Exemple :" in t["rules"]
    assert t["tools"] == ["Pointeur", "Surligner", "Stylo", "Gomme", "Annuler", "Effacer les surlignages", "Effacer les dessins"]
    assert t["sheet"] == "Grille de réponses"
    assert t["comb"] == "Module"

    js(view, "document.getElementById('submit-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    assert js(view, "document.getElementById('modal-title').textContent") == "Rendre votre copie ?"
    assert "40 question(s) sans réponse" in js(view, "document.getElementById('modal-msg').textContent")
    assert js(view, "document.getElementById('modal-ok').textContent") == "Rendre quand même"
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "document.title").startswith("Résultats"))
    assert js(view, "document.documentElement.lang") == "fr"


def test_exam_window_in_english(open_exam, questions, ui):
    ui("en")
    win, view = open_exam(questions, timer_seconds=5400)
    t = _texts(view)
    assert win.windowTitle().startswith("Exam Simulator")
    assert t["lang"] == "en"
    assert t["submit"] == "Submit Exam"
    assert t["progress"] == "0 / 40 answered"
    assert re.search(r"Module: Gastro Date: \d{1,2} [A-Z][a-z]{2} \d{4} 40 MCQs Duration: 1h30", t["head"]), t["head"]
    assert t["rules"].startswith("Instructions Mark the correct answer(s)") and "Example:" in t["rules"]
    assert t["tools"] == ["Pointer", "Highlight", "Pen", "Eraser", "Undo", "Clear highlights", "Clear drawings"]
    assert t["sheet"] == "Answer sheet"


def test_results_messages_in_french(open_exam, questions, ui):
    ui("fr")
    win, view = open_exam(questions[:2])
    js(view, "document.getElementById('submit-btn').click()")
    assert wait_until(lambda: js(view, "modalOpen()"))
    js(view, "document.getElementById('modal-ok').click()")
    assert wait_until(lambda: js(view, "document.title").startswith("Résultats"))
    js(view, "applyTag()")
    assert js(view, "document.getElementById('action-feedback').textContent") == \
        "Sélectionnez d'abord au moins une question."
    js(view, "document.querySelector('.q-check').click()")
    assert js(view, "document.getElementById('sel-count').textContent") == "1 sélectionnée(s)"
    js(view, "document.querySelector('.expl-toggle') && document.querySelector('.expl-toggle').click()")


# ── Setup window and picker ──────────────────────────────────────────────────

def test_setup_and_picker_in_french(addon, ui):
    ui("fr")
    dlg = addon.launcher.LauncherDialog(None)
    assert dlg.windowTitle() == "Simulateur d'examen — Configuration"
    assert "Commencer l'examen" in dlg.start_btn.text()
    assert [dlg.scoring_combo.itemText(i) for i in range(3)] == \
        ["Tout ou rien", "Partiel positif +", "Partiel négatif −"]
    assert dlg.shuffle_check.text() == "Mélanger l'ordre des questions"
    picker = addon.launcher.CardPickerDialog(None, "MCQ-NB")
    assert picker.windowTitle() == "Parcourir et choisir les questions"
    assert picker.count_lbl.text() == "Sélectionnées : 0"
    assert picker.visible_lbl.text() == "40 affichées"


def test_setup_and_picker_in_english(addon, ui):
    ui("en")
    dlg = addon.launcher.LauncherDialog(None)
    assert dlg.windowTitle() == "Exam Simulator — Setup"
    assert "Start Exam" in dlg.start_btn.text()
    assert [dlg.scoring_combo.itemText(i) for i in range(3)] == \
        ["All or Nothing", "Partial Positive +", "Partial Negative −"]
    picker = addon.launcher.CardPickerDialog(None, "MCQ-NB")
    assert picker.windowTitle() == "Browse & Select Questions"
    assert picker.count_lbl.text() == "Selected: 0"
    assert picker.visible_lbl.text() == "40 shown"
