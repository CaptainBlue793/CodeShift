"""Presentation layer for the dashboard: palette, CSS, and HTML fragments.

Separate from `app.py` for the same reason `history.py` is — `app.py` executes a
Streamlit page on import, so anything worth testing has to live outside it.
Every function here returns a string and touches no `st.*`.

The accent colours are the logo's, so the dashboard and the README read as one
project. Neutral surfaces are deliberately `rgba` greys rather than fixed hex:
the app ships a dark theme, but a user who overrides it should get something
that still reads, instead of dark-on-dark panels.
"""
from __future__ import annotations

import base64
import html as _html
from functools import lru_cache
from pathlib import Path

from ui import codetheme

#: The same mark the README uses — referenced, never duplicated, so the two
#: cannot drift apart. `tools/make_logo.py` regenerates it. Lives here rather
#: than in `app.py` so tests can reach it without executing a Streamlit page.
LOGO = Path(__file__).resolve().parents[1] / "images" / "codeshift.png"

PINK = "#FF76B4"      # the logo's pink — reserved for the wordmark gradient
CYAN = "#66F1FF"      # the target side, and anything that improved
#: Accents: the source pane, drift, and a regressed retry. This is Tokyo
#: Night's own lavender, the same value the code panes use for keywords, so
#: the page's furniture and its syntax highlighting are one palette rather
#: than two. Deliberately not cyan: the good/bad split is carried by hue,
#: and reusing one colour for both would erase it.
LAVENDER = codetheme.LAVENDER
AMBER = "#E3B341"     # checked, but not cleanly
MUTED = codetheme.FG_DIM      # captions, labels, subtitles
FAINT = codetheme.GUTTER      # the dimmest readable text

#: Raised surfaces, tinted from the foreground rather than neutral grey —
#: grey panels on a violet background read as dirt rather than as depth.
SURFACE = "rgba(192,202,245,.06)"
SURFACE_STRONG = "rgba(192,202,245,.10)"
BORDER = "rgba(192,202,245,.14)"

#: Verdict slug -> accent. Keys match `codeshift.verification.Verdict`.
VERDICT_COLOR = {
    "verified": CYAN,
    "partial": AMBER,
    "unverified": AMBER,
    "drift": LAVENDER,
    "empty": FAINT,
}

CSS = f"""
<style>
  /* The wordmark picks up the logo's two colours, so the mark beside it and the
     title read as one lockup. Targets h1 directly — the page has exactly one,
     and a wrapper div does not survive Streamlit's own DOM nesting. */
  h1 {{
    background: linear-gradient(90deg, {PINK}, {CYAN});
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 800; letter-spacing: -.02em; margin-bottom: .1rem;
    text-align: center;
  }}
  /* Mark and wordmark on one line, centred as a group. They have to live in a
     single flex container to sit side by side, which is why the header is one
     HTML block rather than `st.image` followed by `st.title` — two Streamlit
     elements are two stacked blocks and cannot be put on a shared baseline. */
  .cs-lockup {{
    display: flex; align-items: center; justify-content: center;
    gap: .8rem; flex-wrap: wrap; margin-bottom: .15rem;
  }}
  .cs-lockup h1 {{ margin: 0; padding: 0; line-height: 1.1; }}
  .cs-mark {{ display: block; margin: 0; height: auto; }}
  .cs-sub {{
    color: {MUTED}; font-size: .82rem; margin-bottom: .9rem;
    text-align: center;
  }}
  .cs-sub code {{ background: {SURFACE_STRONG}; padding: .05rem .35rem; border-radius: 4px; }}

  /* Modules / Report / Code. Streamlit's default tab label is a plain body
     string; these are the page's primary navigation, so they get the same
     sans stack and weight as the pane headers. Selectors reach into Streamlit's
     own markup, which is the one place that is unavoidable — if a future
     version renames them the tabs simply fall back to the default styling
     rather than breaking. */
  .stTabs [data-baseweb="tab-list"] {{ gap: .15rem; }}
  .stTabs [data-baseweb="tab"] {{
    font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
    font-size: .86rem; font-weight: 600; letter-spacing: .03em;
    padding: .35rem .9rem;
  }}
  .stTabs [data-baseweb="tab"][aria-selected="true"] {{ color: {LAVENDER}; }}

  .cs-tiles {{ display: flex; gap: .6rem; flex-wrap: wrap; margin: .2rem 0 .4rem; }}
  .cs-tile {{
    flex: 1 1 120px; padding: .6rem .8rem; border-radius: 10px;
    background: {SURFACE}; border: 1px solid {BORDER};
  }}
  .cs-tile .v {{ font-size: 1.55rem; font-weight: 700; line-height: 1.15; }}
  .cs-tile .l {{
    font-size: .68rem; text-transform: uppercase; letter-spacing: .07em;
    color: {MUTED};
  }}

  /* One row per module. The left edge is the verdict, so the shape of a run is
     legible before reading a single word. */
  .cs-row {{
    display: grid; grid-template-columns: 2.3fr 1.1fr .6fr 1.5fr 1.5fr;
    gap: .6rem; align-items: baseline;
    padding: .5rem .75rem; margin-bottom: .35rem; border-radius: 8px;
    background: {SURFACE};
    border: 1px solid {BORDER}; border-left: 4px solid;
  }}
  .cs-row.is-current {{ background: rgba(102,241,255,.10); }}
  .cs-head {{
    display: grid; grid-template-columns: 2.3fr 1.1fr .6fr 1.5fr 1.5fr;
    gap: .6rem; padding: 0 .75rem .3rem; font-size: .68rem;
    text-transform: uppercase; letter-spacing: .07em; color: {MUTED};
  }}
  .cs-mod {{ font-weight: 600; }}
  .cs-note {{ display: block; font-size: .72rem; color: {FAINT}; margin-top: .15rem; }}

  .cs-pill {{
    font-size: .7rem; padding: .1rem .5rem; border-radius: 999px;
    border: 1px solid currentColor; white-space: nowrap;
  }}
  .cs-trace {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82rem; }}
  .cs-tag {{ font-size: .68rem; margin-left: .35rem; }}
  .cs-improving {{ color: {CYAN}; }}
  .cs-regressed {{ color: {LAVENDER}; }}
  .cs-stuck {{ color: {AMBER}; }}
  .cs-dim {{ color: {FAINT}; }}
</style>
"""


def _esc(value: object) -> str:
    return _html.escape(str(value))


@lru_cache(maxsize=1)
def logo_img(width: int = 84) -> str:
    """The mark as a centred `<img>`, inlined as a data URI.

    Inlined rather than served through `st.image` so it sits inside our own
    centred block — centring Streamlit's image container means targeting its
    internal DOM, which breaks on upgrades. Cached because the page reruns
    twice a second while a migration is running.
    """
    if not LOGO.exists():
        return ""
    encoded = base64.b64encode(LOGO.read_bytes()).decode("ascii")
    return (
        f'<img class="cs-mark" style="width:{width}px" alt="CodeShift logo" '
        f'src="data:image/png;base64,{encoded}">'
    )


def header_html(width: int = 68) -> str:
    """The page header: mark and wordmark side by side, centred as one unit.

    Emitted as a single block, `<h1>` included, because a flex row cannot span
    two Streamlit elements — `st.image` then `st.title` would stack them.
    """
    return f'<div class="cs-lockup">{logo_img(width)}<h1>CodeShift</h1></div>'


def tiles(items: list[tuple[str, object, str | None]]) -> str:
    """A row of stat tiles from (label, value, accent) triples."""
    cells = "".join(
        f'<div class="cs-tile"><div class="v"'
        f'{f" style=\"color:{accent}\"" if accent else ""}>{_esc(value)}</div>'
        f'<div class="l">{_esc(label)}</div></div>'
        for label, value, accent in items
    )
    return f'<div class="cs-tiles">{cells}</div>'


def pill(text: str, color: str) -> str:
    return f'<span class="cs-pill" style="color:{color}">{_esc(text)}</span>'


def trace_html(values: list[int]) -> str:
    """The retry trace, with the last transition named and coloured.

    This is the one number on the page worth staring at: counts that never move
    mean the loop is feeding nothing back, and counts that fall then rise mean
    it is oscillating between fixing types and fixing behaviour.
    """
    if not values:
        return '<span class="cs-dim">-</span>'
    seq = " &rarr; ".join(str(v) for v in values)
    if len(values) < 2:
        return f'<span class="cs-trace">{seq}</span>'
    if values[-1] == values[-2]:
        tag, cls = "stuck", "cs-stuck"
    elif values[-1] < values[-2]:
        tag, cls = "improving", "cs-improving"
    else:
        tag, cls = "regressed", "cs-regressed"
    return f'<span class="cs-trace">{seq}</span><span class="cs-tag {cls}">{tag}</span>'


def module_row(
    *,
    module: str,
    icon: str,
    verdict_label: str,
    verdict_slug: str,
    attempts: int,
    type_errors: list[int],
    divergences: list[int],
    notes: list[str],
    is_current: bool,
) -> str:
    """One module's row, keyed on its verdict rather than its pipeline status."""
    accent = VERDICT_COLOR.get(verdict_slug, "rgba(127,127,127,.45)")
    note_html = "".join(f'<span class="cs-note">{_esc(n)}</span>' for n in notes)
    classes = "cs-row is-current" if is_current else "cs-row"
    return (
        f'<div class="{classes}" style="border-left-color:{accent}">'
        f'<div><span class="cs-mod">{_esc(icon)} {_esc(module)}</span>{note_html}</div>'
        f"<div>{pill(verdict_label, accent)}</div>"
        f'<div class="cs-trace">{_esc(attempts)}</div>'
        f"<div>{trace_html(type_errors)}</div>"
        f"<div>{trace_html(divergences)}</div>"
        "</div>"
    )


HEADER_ROW = (
    '<div class="cs-head">'
    "<div>Module</div><div>Verdict</div><div>Att.</div>"
    "<div>Type errors</div><div>Divergences</div>"
    "</div>"
)
