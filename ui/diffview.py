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

from pygments import highlight as _highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from ui import codetheme

#: Pygments style for the code panes. Tokyo Night is not one of the 49 styles
#: Pygments ships, so it is defined in `ui.codetheme`; any built-in name
#: ("dracula", "nord", "github-dark") works here too. Swapping it restyles all
#: three columns at once, since they share one renderer.
CODE_STYLE = codetheme.TokyoNight

#: The theme's own background, so the panes read as code blocks rather than as
#: page furniture with coloured text on it.
CODE_BG = codetheme.BG
CODE_FG = codetheme.FG
CODE_GUTTER = codetheme.GUTTER

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
/* Every pane -- source and target alike -- renders through this one block, so
   the three columns share a font, a size and a baseline. Streamlit's own
   `st.code` was used for the source before, which gave it a different typeface
   and metrics from the panes beside it and made the columns impossible to read
   against each other. */
.cs-pane { border: 1px solid rgba(192,202,245,0.16); border-radius: 8px;
           overflow: hidden; background: rgba(192,202,245,0.04);
           margin-bottom: 0.35rem; }
.cs-pane-h { display: flex; align-items: center; gap: 0.45rem;
             padding: 0.4rem 0.7rem; font-size: 0.7rem; letter-spacing: 0.05em;
             text-transform: uppercase; opacity: 0.75;
             font-family: ui-sans-serif, system-ui, sans-serif;
             border-bottom: 1px solid rgba(192,202,245,0.14);
             background: rgba(192,202,245,0.06); }
.cs-pane-h .cs-file { text-transform: none; letter-spacing: 0;
                      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                      opacity: 0.8; }
.cs-dot { width: 0.55rem; height: 0.55rem; border-radius: 50%;
          display: inline-block; flex: none; }

.cs-diff { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
           font-size: 0.8rem; line-height: 1.55; tab-size: 4;
           overflow: auto; max-height: 62vh; padding: 0.45rem 0;
           background: CODE_BG_PLACEHOLDER; color: CODE_FG_PLACEHOLDER; }
.cs-diff div { white-space: pre; padding: 0 0.6rem; }
.cs-num { display: inline-block; width: 2.6em; margin-right: 0.7rem;
          text-align: right; user-select: none; color: CODE_GUTTER_PLACEHOLDER; }
/* Tinted overlays sit on top of the code theme's own background, so they use
   that theme's red and green: strong enough to read against it, while leaving
   the syntax colours legible underneath. */
.cs-chg-left  { background: rgba(247, 118, 142, 0.22); }
.cs-chg-right { background: rgba(158, 206, 106, 0.20); }
.cs-pad       { background: rgba(86, 95, 137, 0.18); }
</style>
"""


#: Pygments emits its own class names (`.k`, `.nf`, `.s2`), scoped here to the
#: code panes so they cannot leak into the rest of the page. Generated rather
#: than pasted, so changing `CODE_STYLE` is genuinely a one-line change.
STYLE = (
    STYLE.replace("CODE_BG_PLACEHOLDER", CODE_BG)
    .replace("CODE_FG_PLACEHOLDER", CODE_FG)
    .replace("CODE_GUTTER_PLACEHOLDER", CODE_GUTTER)
    .replace(
        "</style>",
        HtmlFormatter(style=CODE_STYLE).get_style_defs(".cs-diff") + "\n</style>",
    )
)


def highlight_lines(lines: list[str], language: Optional[str]) -> list[str]:
    """Syntax-highlight `lines`, returning one HTML fragment per input line.

    Highlighting the whole block at once and splitting afterwards is what keeps
    it correct: a lexer needs the surrounding context to know that a line is
    inside a docstring or a block comment, which a line-at-a-time pass cannot
    see. Pygments closes and reopens its spans at every newline, so each
    fragment is independently balanced and safe to drop into its own row.

    Falls back to escaped plain text for an unknown language, so a new target
    language renders unhighlighted rather than failing.
    """
    if not lines:
        return []
    escaped = [html.escape(line) for line in lines]
    if not language:
        return escaped
    try:
        lexer = get_lexer_by_name(language)
    except ClassNotFound:
        return escaped

    rendered = _highlight(
        "\n".join(lines), lexer, HtmlFormatter(nowrap=True, style=CODE_STYLE)
    ).split("\n")
    # Pygments appends a trailing newline; anything shorter than the input means
    # an assumption broke, and plain text is better than misaligned rows.
    return rendered[: len(lines)] if len(rendered) >= len(lines) else escaped


def plain_html(code: str, language: Optional[str] = None) -> str:
    """One pane with no comparison, framed and typeset exactly like `to_html`.

    Used for the source column. It goes through the same renderer purely so the
    three columns line up: same typeface, same size, same line-number gutter.
    """
    rows = [Row(line, line, False) for line in code.splitlines()]
    return to_html(rows, "left", language)


def pane(label: str, file: str, body: str, accent: str) -> str:
    """Wrap rendered code in a titled, bordered box."""
    name = f'<span class="cs-file">{html.escape(file)}</span>' if file else ""
    return (
        f'<div class="cs-pane"><div class="cs-pane-h">'
        f'<span class="cs-dot" style="background:{accent}"></span>'
        f"{html.escape(label)}{name}</div>{body}</div>"
    )


def to_html(rows: list[Row], side: Side, language: Optional[str] = None) -> str:
    """Render one column. Changed lines are tinted; padding is inert.

    Returns the markup only; the caller injects `STYLE` once for the page.
    """
    texts = [row.left if side == "left" else row.right for row in rows]
    # Padding rows are not part of the file, so they are held out of the lexer
    # and put back afterwards — feeding them in would shift every line.
    rendered = iter(highlight_lines([t for t in texts if t is not None], language))

    out = ['<div class="cs-diff">']
    number = 0
    for row, text in zip(rows, texts):
        if text is None:
            out.append('<div class="cs-pad"><span class="cs-num"></span>&nbsp;</div>')
            continue
        number += 1
        cls = f"cs-chg-{side}" if row.changed else ""
        body = next(rendered) or "&nbsp;"
        out.append(
            f'<div class="{cls}"><span class="cs-num">{number}</span>{body}</div>'
        )
    out.append("</div>")
    return "".join(out)
