# Design

The exam and results screens copy the real Algerian faculty MCQ exam: a photocopied question booklet in Arial, and a separate answer sheet ("grille") that students mark with a pen cross. The reference photos the user supplied set the bar. The app frame (top bar, toolbars) stays a quiet control layer around the paper.

Shared paper styles, the pen cross and the red-pen marks live in `paper.py`. The exam screen is in `exam_window.py` and the corrected booklet in `scorer.py`.

## World

- **Desk:** the screen background is a warm grey desk (`--desk #d5d3cd`). Paper sheets sit on it with a soft two-layer shadow.
- **Paper:** pure white. Arial throughout, because that is what the real paper is printed in. Don't replace it with a "nicer" face.
- **Three inks, each with one job:**
  - print black `--print #141414` for everything printed on the paper;
  - ballpoint blue `--pen #1f3a93` for whatever the student writes or marks (crosses, comb-field letters);
  - red pen `--red-pen #c0261f` for the corrector: circled right answers, struck wrong choices, scores and the Note box.
- **App frame:** slate top bar `--bar #1e293b` with one blue action colour `--accent #2563eb`. It never appears on the paper.

## Question booklet

- Header: **Module :** / **Date :** on one row, question count / **Durée :** on the next, then a 1.5px black rule.
- Question: bold number, then a bold stem, no full stop after the number (`1  La prednisone…`).
- Options: `A:` then the text, no indent, normal weight. The source line sits below in small grey.
- No dividers between questions. Space separates them, like on the printed page.
- Zoom magnifies the whole page (70–200%, Ctrl + / Ctrl − / Ctrl 0, with a % readout that resets on click). Lines never re-wrap, so pen drawings stay on their words. The answer sheet zooms with it, up to 150%.

## Booklet tools

- A toolbar sits above the booklet on the desk: Pointer, Highlight (yellow / green / pink), Pen (blue / red), Eraser, Undo, Clear drawings, and zoom. Keys: H, P, E, Esc, Ctrl Z. Clicking the active tool goes back to Pointer.
- Highlights are stored as character ranges inside the stem or an option. Pen strokes are stored relative to their question block. Both last for the whole exam and start clean on a new exam.
- `paper.py` holds the shared highlight and ink rendering (`NOTES_CSS`, `NOTES_JS`) so the results page redraws notes in exactly the same places.

## Answer sheet

- A separate sheet to the right of the booklet.
- Header: a comb field (one box per character) for Module, with the student's entry in pen blue. Next to them, a bordered **Consignes** box with an example cross. Then a black rule.
- Grid: blocks of 10 rows. The first half of the blocks run down the left column and the rest down the right (1–10, 11–20 | 21–30, 31–40). Each block has a 1.5px black border, a grey header row with A–E, `Q#` labels, and 22px square boxes. A small pencil tick appears beside `Q#` once that row has a cross.
- Marking places a hand-drawn SVG cross, slightly rotated per box. Never use a fill, a highlight or a typed glyph.
- Clicking a `Q#` label scrolls the booklet to that question, which flashes once in pale yellow. That flash is the only animation.

## Corrected booklet (results)

- The same booklet, annotated. A red, slightly rotated **Note** box gives the /20 score, grade, % and points.
- On each option: the student's blue cross in the left margin, a red circle around the letter of each right answer, and a red strike-through on wrong choices.
- In the right margin of each question: the red-pen status mark (check = correct, tilde = partial, cross = wrong, grey dash = skipped) and the score. Each status has its own shape, so colour is never the only signal.
- A legend under the header explains the three marks.
- The student's highlights and pen drawings are drawn on top. **Show my notes** in the toolbar turns them on and off.
- The question text column is exactly 692px, the same as the exam booklet, so notes land on the same words.
- Filters, selection, flag/tag and navigation sit in the toolbar above the desk, outside the paper.

## Language

Text printed on the paper is in French, as on the real exam (Module, Date, Durée, Consignes, Source). App controls are in English for now. PRODUCT.md requires English and French, but there is no language switch yet.
