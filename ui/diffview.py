"""Line-aligned comparison of two versions of the same translated file.

Kept separate from `app.py` and free of any `st.*` call so the alignment can be
tested without rendering a page.

The two sides are padded to the same length so row *n* on the left and row *n*
on the right describe the same place in the file. Without that the columns drift
apart after the first inserted line and the reader has to re-find their place on
every change.

Highlighting marks changed lines only. Two files that agree produce no
highlighting at all, which is the signal: a clean module should look calm.
"""
from __future__ import annotations

import html
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Optional

Side = Literal["left", "right"]


@dataclass(frozen=True)
class Row:
    """One visual line of the comparison. `None` is padding, not an empty line."""
    left: Optional[str]
    right: Optional[str]
    changed: bool


def align(before: str, after: str) -> list[Row]:
    """Pair up the lines of two versions, padding so both sides stay in step."""
    left_lines = before.splitlines()
    right_lines = after.splitlines()
    rows: list[Row] = []

    for tag, i1, i2, j1, j2 in SequenceMatcher(None, left_lines, right_lines).get_opcodes():
        if tag == "equal":
            rows += [Row(left_lines[i], right_lines[j], False)
                     for i, j in zip(range(i1, i2), range(j1, j2))]
            continue
        # replace/delete/insert all become "these lines differ", padded to the
        # longer side. Distinguishing them further would buy nothing here: the
        # reader wants "look at this line", not the edit-script verb.
        left_block = left_lines[i1:i2]
        right_block = right_lines[j1:j2]
        for k in range(max(len(left_block), len(right_block))):
            rows.append(Row(
                left_block[k] if k < len(left_block) else None,
                right_block[k] if k < len(right_block) else None,
                True,
            ))
    return rows


def changed_rows(rows: list[Row]) -> int:
    return sum(1 for r in rows if r.changed)


def whitespace_only(before: str, after: str) -> bool:
    """True when the two differ by nothing but whitespace.

    Deliberately narrow. A run with no retries still goes through the formatter,
    so its "first attempt" and "shipped" versions differ by indentation and line
    breaks alone — worth saying plainly rather than lighting up every line as if
    something had been fixed. Anything beyond whitespace (a changed quote, an
    added semicolon) counts as a real difference: over-reporting a change is a
    smaller sin here than hiding one.
    """
    return "".join(before.split()) == "".join(after.split())


#: Injected once per page, not once per column — the CSS is global to the
#: document, so repeating it with every block would be pure duplication.
STYLE = """
<style>
.cs-diff { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           font-size: 0.78rem; line-height: 1.45; overflow-x: auto;
           border: 1px solid rgba(128,128,128,0.25); border-radius: 6px;
           padding: 0.5rem 0; background: rgba(128,128,128,0.06); }
.cs-diff div { white-space: pre; padding: 0 0.6rem; }
.cs-num { display: inline-block; width: 2.2em; margin-right: 0.6rem;
          text-align: right; opacity: 0.35; user-select: none; }
/* Tinted overlays rather than solid colours: they read correctly against both
   the light and the dark Streamlit themes without being redefined per theme. */
.cs-chg-left  { background: rgba(232, 90, 90, 0.20); }
.cs-chg-right { background: rgba(60, 190, 120, 0.22); }
.cs-pad       { background: rgba(128,128,128,0.10); }
</style>
"""


def to_html(rows: list[Row], side: Side) -> str:
    """Render one column. Changed lines are tinted; padding is inert.

    Returns the markup only; the caller injects `STYLE` once for the page.
    """
    out = ['<div class="cs-diff">']
    number = 0
    for row in rows:
        text = row.left if side == "left" else row.right
        if text is None:
            out.append('<div class="cs-pad"><span class="cs-num"></span>&nbsp;</div>')
            continue
        number += 1
        cls = f"cs-chg-{side}" if row.changed else ""
        body = html.escape(text) or "&nbsp;"
        out.append(
            f'<div class="{cls}"><span class="cs-num">{number}</span>{body}</div>'
        )
    out.append("</div>")
    return "".join(out)
