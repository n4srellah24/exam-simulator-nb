"""Scoring rules: All or Nothing, Partial Positive +, Partial Negative −."""

import pytest


def q(correct, options="ABCDE"):
    return {"question": "Q", "options": {l: l.lower() for l in options},
            "correct": list(correct), "nid": 1}


def score(addon, mode, items):
    """items: list of (correct, chosen) pairs."""
    qs = [q(c) for c, _ in items]
    answers = {str(i): list(ch) for i, (_, ch) in enumerate(items) if ch}
    return addon.scorer.compute_score(qs, answers, {"mode": mode})


def statuses(r):
    return [x["status"] for x in r["questions"]]


def earned(r):
    return [x["earned"] for x in r["questions"]]


# ── All or Nothing ───────────────────────────────────────────────────────────

def test_raw_exact_match_only(addon):
    r = score(addon, "raw", [("AC", "AC"), ("AC", "A"), ("AC", "ACD"), ("B", "")])
    assert statuses(r) == ["correct", "wrong", "wrong", "skipped"]
    assert earned(r) == [1, 0, 0, 0]
    assert r["total_earned"] == 1 and r["total_possible"] == 4
    assert r["percentage"] == 25 and r["score_20"] == 5


def test_raw_answer_order_does_not_matter(addon):
    r = score(addon, "raw", [("ACE", "ECA")])
    assert statuses(r) == ["correct"]


# ── Partial Positive + ───────────────────────────────────────────────────────

def test_partial_positive_credit_and_floor(addon):
    r = score(addon, "partial", [
        ("AC", "AC"),    # full
        ("AC", "A"),     # half
        ("AC", "ABC"),   # 1 − ½ = ½
        ("AC", "AB"),    # ½ − ½ = 0
        ("A", "BC"),     # −2 → floored at 0
        ("AB", ""),      # skipped
    ])
    assert statuses(r) == ["correct", "partial", "partial", "wrong", "wrong", "skipped"]
    assert earned(r) == [1, 0.5, 0.5, 0, 0, 0]
    assert r["total_earned"] == 2
    assert r["n_correct"] == 1 and r["n_partial"] == 2 and r["n_wrong"] == 2 and r["n_skipped"] == 1


def test_partial_thirds_are_clean(addon):
    r = score(addon, "partial", [("ABC", "AB")])
    assert r["questions"][0]["earned"] == pytest.approx(2 / 3, abs=1e-6)
    assert r["questions"][0]["status"] == "partial"


# ── Partial Negative − ───────────────────────────────────────────────────────

def test_negative_can_go_below_zero_per_question(addon):
    r = score(addon, "negative", [("A", "B"), ("AC", "B"), ("AC", "ABD")])
    assert earned(r) == [-1, -0.5, -0.5]
    assert statuses(r) == ["wrong", "wrong", "wrong"]


def test_negative_question_score_capped_at_minus_one(addon):
    r = score(addon, "negative", [("A", "BCDE")])
    assert earned(r) == [-1]


def test_negative_total_never_below_zero(addon):
    r = score(addon, "negative", [("A", "B"), ("A", "B"), ("A", "A")])
    assert r["total_earned"] == 0
    assert r["percentage"] == 0 and r["score_20"] == 0


def test_negative_penalties_reduce_total(addon):
    r = score(addon, "negative", [("A", "A"), ("A", "A"), ("A", "B")])
    assert r["total_earned"] == 1
    assert r["score_20"] == pytest.approx(20 / 3, abs=1e-6)


# ── Totals and the results page ──────────────────────────────────────────────

def test_score_out_of_20_matches_percentage(addon):
    r = score(addon, "raw", [("A", "A")] * 3 + [("A", "B")] * 5)
    assert r["percentage"] == pytest.approx(37.5)
    assert r["score_20"] == pytest.approx(7.5)


def test_empty_exam_does_not_crash(addon):
    r = addon.scorer.compute_score([], {}, {"mode": "partial"})
    assert r["percentage"] == 0 and r["score_20"] == 0


def test_results_html_shows_note_and_escapes_name(addon):
    r = score(addon, "raw", [("A", "A"), ("B", "")])
    r["exam_name"] = "<script>alert(1)</script>"
    page = addon.scorer.build_results_html(r)
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page
    assert 'class="note-val">10<small> / 20</small>' in page
    assert page.count('class="r-q"') == 2


def test_results_html_hides_partial_filter_in_all_or_nothing(addon):
    r = score(addon, "raw", [("A", "A")])
    assert 'data-filter="partial"' not in addon.scorer.build_results_html(r)
    r = score(addon, "partial", [("A", "A")])
    assert 'data-filter="partial"' in addon.scorer.build_results_html(r)
