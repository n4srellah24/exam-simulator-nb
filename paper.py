"""
Printed-paper world shared by the exam booklet, the answer sheet and the
corrected booklet on the results page. No Qt imports, so it renders anywhere.
"""

import html


# Ballpoint cross: two slightly bowed strokes rather than a typed glyph.
PEN_SVG = ('<svg class="pen" viewBox="0 0 20 20" aria-hidden="true">'
           '<path d="M4.3 4.4C7.9 8.3 11.7 12.2 16.1 16.2"/>'
           '<path d="M15.9 4.0C12.2 7.8 8.7 12.3 4.5 16.5"/></svg>')


# Corrector's red-pen marks, one distinct shape per status so colour is never
# the only signal.
MARK_PATHS = {
    "correct": "M3 10.5 8 16 17.5 4",
    "partial": "M2.5 11.5C5 6.5 8 6.5 10 10s5 4 7.5-1",
    "wrong":   "M4 4 16 16M16 4 4 16",
    "skipped": "M4.5 10h11",
}


def mark_svg(status: str) -> str:
    return (f'<svg class="mark mark-{status}" viewBox="0 0 20 20" aria-hidden="true">'
            f'<path d="{MARK_PATHS.get(status, MARK_PATHS["skipped"])}"/></svg>')


def fmt_duration(seconds) -> str:
    if not seconds:
        return ""
    h, m = divmod(int(seconds) // 60, 60)
    if not h:
        return f"{m} min"
    return f"{h}h{m:02d}" if m else f"{h}h"


def comb_field(label: str, text: str, cells: int) -> str:
    chars = list(text[:cells]) + [""] * max(0, cells - len(text))
    boxes = "".join(f'<span class="cell">{html.escape(c)}</span>' for c in chars)
    return (f'<div class="comb"><span class="comb-label">{label}</span>'
            f'<span class="cells">{boxes}</span></div>')


def comb_date(label: str, dmy: str) -> str:
    groups = []
    for part in dmy.split("/"):
        groups.append("".join(f'<span class="cell">{c}</span>' for c in part))
    sep = '<span class="cell-sep">/</span>'
    return (f'<div class="comb"><span class="comb-label">{label}</span>'
            f'<span class="cells">{sep.join(groups)}</span></div>')


# The printed-paper world: shared by the exam and the corrected booklet.
PAPER_CSS = """
:root {
  --desk: #d5d3cd;
  --desk-ink: #3b3a36;
  --paper: #ffffff;
  --print: #141414;
  --print-soft: #555555;
  --rule: #1c1c1c;
  --head-fill: #cfcfcf;
  --pen: #1f3a93;
  --red-pen: #c0261f;
  --bar: #1e293b;
  --bar-ink: #f1f5f9;
  --bar-soft: #a8b3c4;
  --accent: #2563eb;
  --accent-hover: #1d4ed8;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; overflow: hidden; }
body {
  font-family: Arial, Helvetica, sans-serif;
  background: var(--desk); color: var(--print);
  display: flex; flex-direction: column;
}
::selection { background: #fde68a; color: var(--print); }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.desk { background: var(--desk); }
.desk::-webkit-scrollbar { width: 12px; }
.desk::-webkit-scrollbar-track { background: var(--desk); }
.desk::-webkit-scrollbar-thumb { background: #a9a69e; border: 3px solid var(--desk); border-radius: 6px; }
.desk::-webkit-scrollbar-thumb:hover { background: #8d8a82; }

.paper {
  background: var(--paper);
  box-shadow: 0 1px 2px rgba(0,0,0,.18), 0 6px 18px rgba(0,0,0,.10);
}
.paper-head {
  border-bottom: 1.5px solid var(--rule);
  padding-bottom: 10px; margin-bottom: 26px;
  font-size: .93em; line-height: 1.6;
}
.ph-row { display: flex; justify-content: space-between; gap: 24px; }

/* Booklet type: plain photocopied Arial, bold stems, "A:" options */
.q-block { margin-bottom: 1.35em; scroll-margin-top: 16px; border-radius: 2px; }
.q-header { display: flex; gap: .45em; margin-bottom: .3em; line-height: 1.45; font-weight: bold; }
.q-num  { flex-shrink: 0; min-width: 1.3em; }
.q-opts { display: flex; flex-direction: column; gap: .12em; }
.q-opt  { display: flex; gap: .4em; line-height: 1.45; }
.opt-letter { flex-shrink: 0; min-width: 1.2em; }
.q-source { margin-top: .3em; font-size: .82em; color: var(--print-soft); }
.q-target { animation: q-flash 1.6s cubic-bezier(.16,1,.3,1); }
@keyframes q-flash {
  from { background: #fff3b0; box-shadow: 0 0 0 8px #fff3b0; }
  to   { background: transparent; box-shadow: 0 0 0 8px transparent; }
}

/* Red pen: the corrector's marks */
.mark { width: 22px; height: 22px; overflow: visible; }
.mark path { fill: none; stroke: var(--red-pen); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
.mark-skipped path { stroke: #8a8a8a; }

/* Pen marks */
.pen { width: 100%; height: 100%; display: block; overflow: visible; transform-origin: 50% 50%; }
.pen path { fill: none; stroke: var(--pen); stroke-width: 2.6; stroke-linecap: round; }
"""
