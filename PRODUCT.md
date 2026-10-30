# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Desktop Anki add-on (PyQt6). The exam and results surfaces are HTML/CSS rendered in a `QWebEngineView` (`exam_window.py`, `scorer.py`); the setup launcher and question picker are native Qt widgets (`launcher.py`). "web" applies to the HTML surfaces; Qt dialogs follow desktop/Anki conventions.

## Users

Medical students preparing for MCQ exams, sitting mock papers drawn from their own Anki MCQ note banks in the run-up to faculty exams. They already use Anki for spaced-repetition recall and want a separate mode that reproduces exam conditions, then lets them review mistakes. French-speaking students are a core audience.

## Product Purpose

Turn an Anki MCQ note bank into an exam-simulation workflow: build an exam from filtered questions, sit it under time and scoring rules in a dedicated window, then review performance question by question. Success means the student practises under realistic exam conditions and leaves with a clear, actionable picture of what they got wrong.

## Positioning

Runs entirely inside Anki on the student's own note bank. No export, server, or account: the questions they already wrote or imported become real mock papers, and the results feed straight back into Anki through flags and tags.

## Operating Context

- Started from Anki: **Tools → Exam Simulator - NB**.
- Flow: setup (note type, deck/tag/history/flag filters, manual picking, count, name, shuffle, timing, scoring mode) → exam window → submit → results review → optional bulk flag/tag → start another exam.
- Sessions are often long, timed mock papers taken in focused revision blocks.
- Named exams are saved to local simulation history (`exam_simulator_history.json` in the Anki profile) and can be reused as a filter source.

## Capabilities and Constraints

- Expected note type `MCQ-NB` with fields `Question`, `option_1 (A)` … `option_5 (E)` (E optional), `Ans`, `Source` (optional), `Explanation` (optional).
- `Ans` accepts letters or digits (`AC`, `13`; 1→A … 5→E); questions may have multiple correct answers.
- Scoring modes: All or Nothing, Partial Positive +, Partial Negative −. Results show raw score, score out of 20, percentage, and correct/partial/wrong/skipped counts.
- Balanced round-robin sampling across subdecks.
- Exam window: paper-style question layout, side answer-sheet grid, timer, zoom, jump between answer sheet and questions.
- History is add-on-owned and local; it never writes normal Anki tags, and deleting history never deletes notes. Unnamed exams are not saved.
- Must stay compatible with Anki's PyQt6 / QtWebEngine runtime; no external backend.
- Known limits: fixed field schema; answer-choice order is not randomised.
- Roadmap, undecided: configurable field mapping, more note schemas, exportable reports, richer analytics, exam presets, answer-choice randomisation.

## Brand Commitments

- Name: **Exam Simulator - NB**.
- The exam phase must faithfully mimic a real paper exam with an answer sheet; realism is the point of the product, not a styling choice.
- The UI language must support both **English and French**. Today's UI is English only; French support is a confirmed requirement, not yet implemented.

## Evidence on Hand

- Screenshots: `screenshots/launcher.png`, `screenshots/exam-interface.png`, `screenshots/results.png`.
- README feature descriptions and AnkiWeb listing copy.
- No testimonials, user counts, reviews, or benchmarks exist; do not invent any.

## Product Principles

1. **Exam fidelity first.** During the exam, behave like the real paper and answer sheet; avoid conveniences that a real exam would not offer.
2. **Review should lead to action.** Results exist to turn mistakes into next steps: flag, tag, and re-sit.
3. **Stay inside Anki, stay local.** No accounts, no servers, and nothing written to the user's notes or tags unless they ask for it.
4. **Respect the student's bank.** Work with the notes they already have; don't make them restructure or duplicate content.
5. **Bilingual by design.** Write English and French as equals; layouts must fit French strings, which run longer.

## Accessibility & Inclusion

Long timed sessions need text that stays readable for hours: zoom has to keep working, and status (correct/partial/wrong/skipped) must never rely on colour alone. No formal standard has been established.
