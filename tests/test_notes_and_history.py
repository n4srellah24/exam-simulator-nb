"""Reading MCQ-NB notes, balanced sampling, and simulation history."""

import json

from conftest import NOTE_TYPE, add_mcq

OPTS = ["un", "deux", "trois", "quatre", "cinq"]


def parse(addon, col, **kw):
    nid = add_mcq(col, "Tests::Parsing", kw.pop("question", "Stem"), kw.pop("options", OPTS),
                  kw.pop("ans", "A"), **kw)
    note = col.get_note(nid)
    col.remove_notes([nid])
    return addon.launcher._parse_note(note, NOTE_TYPE)


# ── Parsing ──────────────────────────────────────────────────────────────────

def test_letter_and_digit_answers(addon, col):
    assert parse(addon, col, ans="AC")["correct"] == ["A", "C"]
    assert parse(addon, col, ans="13")["correct"] == ["A", "C"]
    assert parse(addon, col, ans="b")["correct"] == ["B"]
    assert parse(addon, col, ans="5")["correct"] == ["E"]
    assert parse(addon, col, ans="A, C")["correct"] == ["A", "C"]


def test_unused_option_e_is_dropped(addon, col):
    q = parse(addon, col, options=OPTS[:4], ans="D")
    assert list(q["options"]) == ["A", "B", "C", "D"]


def test_answer_pointing_to_empty_option_is_invalid(addon, col):
    assert parse(addon, col, options=OPTS[:4], ans="E") is None


def test_missing_answer_or_question_is_invalid(addon, col):
    assert parse(addon, col, ans="") is None
    assert parse(addon, col, question="", ans="A") is None


def test_html_is_stripped_but_explanation_keeps_it(addon, col):
    q = parse(addon, col, question="<b>Le diagnostic</b> de la RCH :",
              options=["<i>Rectorragies</i>", "B", "C", "D"], ans="A",
              source="<span>Q5 P2021</span>", explanation="<b>Voir</b> cours")
    assert q["question"] == "Le diagnostic de la RCH :"
    assert q["options"]["A"] == "Rectorragies"
    assert q["source"] == "Q5 P2021"
    assert q["explanation"] == "<b>Voir</b> cours"


# ── Balanced sampling ────────────────────────────────────────────────────────

def test_smart_sample_round_robins_decks(addon):
    pairs = [(i, {"deck": "A"}) for i in range(1, 6)] + \
            [(10, {"deck": "B"})] + [(20, {"deck": "C"}), (21, {"deck": "C"})]
    out = addon.launcher._smart_sample(pairs, 6)
    assert out == [1, 10, 20, 2, 21, 3]


def test_smart_sample_never_exceeds_pool(addon):
    pairs = [(1, {"deck": "A"}), (2, {"deck": "B"})]
    assert sorted(addon.launcher._smart_sample(pairs, 10)) == [1, 2]


# ── Simulation history ───────────────────────────────────────────────────────

def test_record_and_group_history(addon, clean_history):
    h = addon.history
    h.record_simulation("Gastro_1", [3, 1, 1, None])
    h.record_simulation("Gastro_1", [5])
    h.record_simulation("Cardio", [9])
    data = json.loads(clean_history.read_text(encoding="utf-8"))
    assert data["version"] == 1 and len(data["entries"]) == 3
    assert data["entries"][0]["note_ids"] == [1, 3]
    groups = {g["label"]: g for g in h.grouped_history()}
    assert groups["Gastro_1"]["note_ids"] == [1, 3, 5]
    assert groups["Gastro_1"]["runs"] == 2
    assert groups["Cardio"]["runs"] == 1


def test_record_without_notes_saves_nothing(addon, clean_history):
    addon.history.record_simulation("Empty", [])
    assert not clean_history.exists()


def test_delete_and_clear_history(addon, clean_history):
    h = addon.history
    h.record_simulation("A", [1])
    h.record_simulation("B", [2])
    h.delete_history_labels(["A"])
    assert [g["label"] for g in h.grouped_history()] == ["B"]
    h.clear_history()
    assert h.grouped_history() == []


def test_corrupt_or_foreign_history_file_is_ignored(addon, clean_history):
    h = addon.history
    clean_history.write_text("{not json", encoding="utf-8")
    assert h.load_history() == {"version": 1, "entries": []}
    clean_history.write_text(json.dumps({"version": 99, "entries": [1]}), encoding="utf-8")
    assert h.load_history()["entries"] == []
    h.record_simulation("After", [7])
    assert [g["label"] for g in h.grouped_history()] == ["After"]
