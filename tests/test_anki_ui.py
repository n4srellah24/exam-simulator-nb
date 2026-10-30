"""The add-on inside (headless) Anki: menu entry, picker filters, launcher."""

from PyQt6.QtWidgets import QApplication

from conftest import NOTE_TYPE, wait_until


def test_addon_adds_tools_menu_entry(addon, mw):
    titles = [a.text() for a in mw.form.menuTools.actions()]
    assert "Exam Simulator - NB" in titles


def picker(addon):
    return addon.launcher.CardPickerDialog(None, NOTE_TYPE)


def visible(dlg):
    return dlg.result_list.count()


def test_picker_loads_all_valid_notes(addon, questions):
    dlg = picker(addon)
    assert visible(dlg) == len(questions) == 40


def test_picker_deck_filter_includes_subdecks(addon):
    dlg = picker(addon)
    dlg._active_deck = "Gastro"
    dlg._apply_filters()
    assert visible(dlg) == 32
    dlg._active_deck = "Gastro::Foie"
    dlg._apply_filters()
    assert visible(dlg) == 12


def test_picker_tag_flag_and_search_filters(addon, col):
    dlg = picker(addon)
    dlg._active_tags = {"hard"}
    dlg._apply_filters()
    assert visible(dlg) == 12
    dlg._active_tags = set()
    dlg.search_box.setText("cardio question 3")
    dlg._apply_filters()
    assert visible(dlg) == 1
    dlg.search_box.setText("")

    nid = sorted(col.find_notes('"deck:Cardio"'))[0]
    card = col.get_note(nid).cards()[0]
    card.set_user_flag(4)
    col.update_card(card)
    try:
        dlg = picker(addon)
        dlg._active_flags = {4}
        dlg._apply_filters()
        assert visible(dlg) == 1
    finally:
        card.set_user_flag(0)
        col.update_card(card)


def test_launcher_defaults_to_mcq_note_type(addon):
    dlg = addon.launcher.LauncherDialog(None)
    assert dlg.note_type_combo.currentText() == NOTE_TYPE
    assert not dlg.start_btn.isEnabled()


def test_launcher_starts_balanced_named_exam(addon, col, clean_history):
    dlg = addon.launcher.LauncherDialog(None)
    nids = sorted(col.find_notes(f'note:"{NOTE_TYPE}"'))
    meta = {}
    for nid in nids:
        deck = col.decks.name(col.get_note(nid).cards()[0].did)
        meta[nid] = {"deck": deck}
    dlg._picked_ids, dlg._picked_meta = nids, meta
    dlg.limit_check.setChecked(True)
    dlg.limit_spin.setMaximum(len(nids))
    dlg.limit_spin.setValue(6)
    dlg.exam_name_edit.setText("Mock 1")
    dlg.timer_check.setChecked(True)
    dlg.timer_spin.setValue(90)
    dlg.scoring_combo.setCurrentIndex(2)
    dlg.start_btn.setEnabled(True)

    before = set(QApplication.topLevelWidgets())
    dlg._start()
    wins = [w for w in QApplication.topLevelWidgets()
            if w not in before and type(w).__name__ == "ExamWindow"]
    assert len(wins) == 1
    win = wins[0]
    try:
        assert len(win.questions) == 6
        decks = {meta[q["nid"]]["deck"] for q in win.questions}
        assert decks == {"Gastro::Colon", "Gastro::Foie", "Cardio"}
        assert win.timer_seconds == 90 * 60
        assert win.scoring == {"mode": "negative"}
        assert win.exam_name == "Mock_1" and win.save_history
    finally:
        win.close()
        wait_until(lambda: True, 0.1)
