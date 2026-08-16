"""Dashboard tests: the history fold, the diff view, and headless page renders."""
import pytest

from ui.diffview import align, changed_rows, to_html, whitespace_only
from ui.history import counts, record_history, trace, trend
from ui.runner import RunHandle


def _snapshot(attempts, type_errors=0, divergences=0, module="utils"):
    return {
        "files": {
            module: {
                "attempts": attempts,
                "type_errors": [{"code": "TS1"}] * type_errors,
                "divergences": [{"function": "f"}] * divergences,
            }
        }
    }


# ------------------------------------------------------------------- history

def test_one_attempt_refines_a_single_row():
    """The translator, type oracle and differential run each emit a snapshot for
    the same attempt; they must not become three rows."""
    history: dict = {}
    record_history(history, _snapshot(1))                       # translator
    record_history(history, _snapshot(1, type_errors=1))        # type oracle
    record_history(history, _snapshot(1, type_errors=1, divergences=4))

    assert list(history["utils"]) == [1]
    assert history["utils"][1] == {"type_errors": 1, "divergences": 4, "rejected": None}


def test_trace_renders_the_observed_oscillation():
    history: dict = {}
    for attempt, errors in enumerate([1, 0, 1], start=1):
        record_history(history, _snapshot(attempt, type_errors=errors))

    assert counts(history["utils"], "type_errors") == [1, 0, 1]
    assert trace(history["utils"], "type_errors") == "1 → 0 → 1"


@pytest.mark.parametrize(
    "sequence, expected",
    [([1], ""), ([1, 1], "stuck"), ([1, 0], "improving"), ([0, 1], "regressed")],
)
def test_trend_labels_the_last_transition(sequence, expected):
    history: dict = {}
    for attempt, errors in enumerate(sequence, start=1):
        record_history(history, _snapshot(attempt, type_errors=errors))

    assert expected in trend(history["utils"], "type_errors")


def test_untranslated_modules_are_skipped():
    history: dict = {}
    record_history(history, _snapshot(0))
    assert history == {}


# ------------------------------------------------------------------ diffview

def test_identical_versions_highlight_nothing():
    """The calm case: a module that shipped what it first produced."""
    code = "export function add(a: number, b: number): number {\n  return a + b;\n}\n"
    rows = align(code, code)

    assert changed_rows(rows) == 0
    assert all(r.left == r.right for r in rows)
    assert "cs-chg" not in to_html(rows, "left")


def test_changed_line_is_marked_on_both_sides():
    before = "export function add(a: number, b: number) {\n  return a - b;\n}\n"
    after = "export function add(a: number, b: number) {\n  return a + b;\n}\n"
    rows = align(before, after)

    assert changed_rows(rows) == 1
    changed = next(r for r in rows if r.changed)
    assert changed.left is not None and changed.right is not None  # both sides real
    assert changed.left.strip() == "return a - b;"
    assert changed.right.strip() == "return a + b;"


def test_sides_stay_in_step_when_a_line_is_added():
    """Without padding the columns drift apart after the first insertion and the
    reader has to re-find their place on every change."""
    rows = align("a\nb\n", "a\nNEW\nb\n")

    assert len(rows) == 3
    assert [r.left for r in rows] == ["a", None, "b"]
    assert [r.right for r in rows] == ["a", "NEW", "b"]


def test_padding_rows_are_not_numbered_as_code():
    """Line numbers must count real lines, or they stop matching the file."""
    html = to_html(align("a\nb\n", "a\nNEW\nb\n"), "left")
    assert html.count("cs-pad") == 1
    assert ">1<" in html and ">2<" in html and ">3<" not in html


def test_whitespace_only_change_is_recognised():
    """A run with no retries still passes through the formatter."""
    assert whitespace_only("function f(){return 1;}", "function f() {\n  return 1;\n}")
    assert not whitespace_only("return a + b;", "return a - b;")


def test_code_is_escaped_not_injected():
    rows = align("const x = a < b && c > d;", "const x = a < b;")
    html = to_html(rows, "left")
    assert "&lt; b &amp;&amp; c &gt;" in html
    assert "<b" not in html


# -------------------------------------------------------------------- runner

def test_drain_records_terminal_events_on_the_handle():
    handle = RunHandle()
    handle.events.put(("state", {"a": 1}))
    handle.events.put(("error", "boom"))
    handle.events.put(("done", None))

    snapshots = handle.drain()

    assert snapshots == [{"a": 1}]      # only state is returned
    assert handle.error == "boom"
    assert handle.finished
    assert handle.drain() == []         # queue is consumed


# --------------------------------------------------------------- page render

def test_page_renders_without_exception():
    """Catches import errors and unsupported Streamlit APIs, which a plain HTTP
    check cannot — the script only executes once a client connects."""
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("ui/app.py", default_timeout=30)
    app.run()

    assert not app.exception, app.exception
    # The wordmark is an `<h1>` inside the header block rather than `st.title`,
    # because the mark and the title share one flex row and two Streamlit
    # elements cannot. Still a real h1, just not one AppTest indexes.
    page = "".join(block.value for block in app.markdown)
    assert "<h1>CodeShift</h1>" in page


def test_the_mark_and_the_wordmark_share_one_row():
    """Side by side, not stacked — which is only possible if both are emitted
    in a single block."""
    from ui.theme import header_html

    header = header_html()
    assert header.index("<img") < header.index("<h1>")     # mark first, then title
    assert header.startswith('<div class="cs-lockup">')


def _render_with(files: dict, **extra):
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file("ui/app.py", default_timeout=30)
    app.session_state["snapshot"] = {
        "translation_order": list(files), "files": files,
        "source_lang": "python", "target_lang": "typescript",
        **extra,
    }
    app.run()
    assert not app.exception, app.exception
    return app


def _metric(app, label: str) -> str:
    """Read one stat tile's value.

    The tiles are custom HTML rather than `st.metric`, so there is no widget to
    query — the value is pulled back out of the rendered markup. What is being
    asserted is unchanged: the count the page shows a reader.
    """
    import re

    # `[^<]*` rather than `.*?`: the tiles are concatenated into one string, and
    # a dot-match would span from an earlier tile's value to this tile's label.
    pattern = re.compile(
        r'<div class="v"[^>]*>([^<]*)</div><div class="l">' + re.escape(label) + "</div>"
    )
    for block in app.markdown:
        found = pattern.search(block.value)
        if found:
            return found.group(1)
    raise AssertionError(f"no tile labelled {label!r} on the page")


def test_dashboard_does_not_count_an_untested_module_as_verified():
    """The page's own copy of the silent pass: 0 divergences read as clean."""
    app = _render_with({"models": {
        "module": "models", "status": "idiomatic", "attempts": 1,
        "divergences": [], "type_errors": [], "verified_functions": [],
        "unverified": [{"name": "User", "reason": "class"}],
    }})

    assert _metric(app, "Verified") == "0"
    assert _metric(app, "Not verified") == "1"


def test_dashboard_counts_a_genuinely_checked_module():
    app = _render_with({"utils": {
        "module": "utils", "status": "idiomatic", "attempts": 1,
        "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
        "unverified": [],
    }})

    assert _metric(app, "Verified") == "1"
    assert _metric(app, "Not verified") == "0"


_CHECKED = {"utils": {
    "module": "utils", "status": "idiomatic", "attempts": 1,
    "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
    "unverified": [],
}}


def test_dashboard_says_when_verification_ran_without_isolation():
    """A "Verified: 1" next to no warning would read as stronger evidence than
    it is — the code ran on the host. The report says so; so must the page."""
    app = _render_with(_CHECKED, isolation="host")

    assert _metric(app, "Verified") == "1"
    assert any("without isolation" in w.value for w in app.warning)


def test_dashboard_is_quiet_about_isolation_when_sandboxed():
    app = _render_with(_CHECKED, isolation="docker")

    assert not any("without isolation" in w.value for w in app.warning)
    assert any("no network" in c.value for c in app.caption)


# ------------------------------------------------- three-column comparison
# The panes are source | what the model emitted | the file on disk, so the
# highlighting between the last two is the formatter's contribution. That is
# only recoverable because `idiom` records the code before formatting -
# `translated_code` is re-read from the file and would otherwise equal it.

def _three_col(emitted, on_disk, attempts=1, first=None):
    return _render_with({"utils": {
        "module": "utils", "path": "utils.py", "status": "idiomatic",
        "attempts": attempts, "source_code": "def slugify(text):\n    return text\n",
        "pre_format_code": emitted, "translated_code": on_disk,
        "first_code": first, "target_path": "utils.ts",
        "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
        "unverified": [],
    }})


def _captions(app):
    return " ".join(c.value for c in app.caption)


def test_all_three_panes_are_labelled():
    """Labels live in each pane's own header now, not in a caption above it."""
    code = "export function slugify(text: string) {\n  return text;\n}\n"
    page = "".join(b.value for b in _three_col(code, code).markdown)

    assert "① source" in page and "utils.py" in page
    assert "② as the model wrote it" in page
    assert "③ on disk" in page and "utils.ts" in page
    # Match the rendered attribute, not the bare class name — the stylesheet on
    # the same page mentions the class too.
    assert page.count('class="cs-pane-h"') == 3


def test_the_source_pane_uses_the_same_renderer_as_the_target_panes():
    """The complaint this fixes: `st.code` gave the source a different typeface
    and size from the panes beside it, so the columns would not line up."""
    code = "export function slugify(text: string) {\n  return text;\n}\n"
    page = "".join(b.value for b in _three_col(code, code).markdown)

    # Three `.cs-diff` blocks means all three columns went through `to_html`.
    assert page.count('class="cs-diff"') == 3


def test_untouched_file_says_the_formatter_changed_nothing():
    code = "export function slugify(text: string) {\n  return text;\n}\n"
    assert "byte-for-byte" in _captions(_three_col(code, code))


def test_formatting_only_difference_is_named_as_the_formatter():
    app = _three_col(
        "export function slugify(text: string){return text;}",
        "export function slugify(text: string) {\n  return text;\n}\n",
    )
    assert "formatter's work only" in _captions(app)


def test_a_real_code_difference_between_panes_is_reported():
    app = _three_col(
        "export function slugify(text: string) {\n  return text.split(/\\s+/);\n}\n",
        "export function slugify(text: string) {\n  return text.split(/[\\s\\x1c]+/);\n}\n",
    )
    captions = _captions(app)
    assert "line(s) differ" in captions
    assert "what the model emitted" in captions


def test_the_retry_count_is_still_reported_without_a_column():
    """The retry loop lost its pane, not its visibility - it is the project's
    core diagnostic and must not quietly disappear from this tab."""
    app = _three_col(
        "export function f() { return 1; }",
        "export function f() {\n  return 1;\n}\n",
        attempts=3,
        first="export function f() { return 2; }",
    )
    captions = _captions(app)
    assert "3 attempts" in captions
    assert "first attempt" in captions


def test_missing_pre_format_code_does_not_break_the_view():
    """Snapshots predating the field, and modules that never reached `idiom`,
    must still render rather than blanking the tab."""
    app = _render_with({"utils": {
        "module": "utils", "path": "utils.py", "status": "idiomatic", "attempts": 1,
        "source_code": "def slugify(text):\n    return text\n",
        "translated_code": "export function slugify(t: string) { return t; }",
        "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
        "unverified": [],
    }})
    assert "byte-for-byte" in _captions(app)


# ------------------------------------------------------------------- theming

def test_trace_names_the_last_transition():
    """The retry trace is the page's most diagnostic element; its label has to
    match what the numbers actually did."""
    from ui.theme import trace_html

    assert "improving" in trace_html([1, 0])
    assert "regressed" in trace_html([0, 1])
    assert "stuck" in trace_html([1, 1])
    assert "1 &rarr; 0 &rarr; 1" in trace_html([1, 0, 1])
    # One attempt has no transition to label, and none has nothing to show.
    assert "improving" not in trace_html([1])
    assert trace_html([]) == '<span class="cs-dim">-</span>'


def test_a_module_row_is_coloured_by_its_verdict_not_its_status():
    from ui.theme import CYAN, LAVENDER, module_row

    def row(slug):
        return module_row(
            module="m", icon="x", verdict_label=slug, verdict_slug=slug, attempts=1,
            type_errors=[], divergences=[], notes=[], is_current=False,
        )

    assert CYAN in row("verified")
    assert LAVENDER in row("drift")


def test_module_names_and_notes_are_escaped_not_injected():
    """Rows are raw HTML, and a module name reaches them from the filesystem."""
    from ui.theme import module_row

    html = module_row(
        module="<img src=x>", icon="o", verdict_label="v", verdict_slug="verified",
        attempts=0, type_errors=[], divergences=[], notes=["<script>"], is_current=False,
    )
    assert "&lt;img src=x&gt;" in html and "<img" not in html
    assert "&lt;script&gt;" in html and "<script>" not in html


def test_rows_render_for_every_module_in_order():
    app = _render_with({
        "models": {"module": "models", "status": "idiomatic", "attempts": 1,
                   "divergences": [], "type_errors": [], "verified_functions": ["f"],
                   "unverified": []},
        "utils": {"module": "utils", "status": "pending", "attempts": 0,
                  "divergences": [], "type_errors": [], "verified_functions": [],
                  "unverified": []},
    })
    page = "".join(b.value for b in app.markdown)
    assert "cs-row" in page
    assert "models" in page and "utils" in page


def test_a_cycle_is_surfaced_on_the_page():
    """The report warns about cycles; the page must not be quieter than it."""
    app = _render_with(
        {"a": {"module": "a", "status": "pending", "attempts": 0, "divergences": [],
               "type_errors": [], "verified_functions": [], "unverified": []}},
        cycles=[["a", "b"]],
    )
    assert any("Circular imports" in w.value for w in app.warning)


def test_the_logo_the_page_uses_actually_exists():
    """The page renders the mark only `if LOGO.exists()`, so a moved or renamed
    file would silently produce a logo-less header rather than an error.

    Imported from `theme`, not `app` - importing `app` executes the page."""
    from ui.theme import LOGO

    assert LOGO.exists(), f"dashboard logo missing at {LOGO}"
    assert LOGO.stat().st_size > 0


def test_the_page_header_is_centred_and_carries_the_mark():
    """The mark is inlined as a data URI rather than served through st.image,
    so it can be centred inside our own block instead of Streamlit's."""
    from ui.theme import CSS, logo_img

    assert "text-align: center" in CSS
    assert 'class="cs-mark"' in logo_img()
    assert logo_img().startswith('<img class="cs-mark"')
    assert "data:image/png;base64," in logo_img()


def test_streamlit_chrome_uses_the_same_palette_as_the_code_panes():
    """The page background, sidebar, body text and accent are all set from
    ui.codetheme. A TOML file cannot import the module, so nothing but this
    test stops the two halves of the palette drifting apart — and a drift
    would show as the chrome and the code panes being subtly different
    shades of almost the same colour, which is worse than an obvious mismatch."""
    import tomllib
    from pathlib import Path

    from ui import codetheme

    config = Path(__file__).resolve().parents[2] / ".streamlit" / "config.toml"
    assert config.exists(), "the dashboard theme config is missing"
    cfg = tomllib.loads(config.read_text(encoding="utf-8"))["theme"]

    assert cfg["primaryColor"].upper() == codetheme.LAVENDER.upper()
    assert cfg["backgroundColor"].upper() == codetheme.BG.upper()
    assert cfg["secondaryBackgroundColor"].upper() == codetheme.BG_ELEVATED.upper()
    assert cfg["textColor"].upper() == codetheme.FG.upper()


def test_the_page_background_matches_the_code_pane_background():
    """The panes sit directly on the page, so a mismatch here reads as a seam."""
    from ui import codetheme
    from ui.diffview import CODE_BG

    assert CODE_BG == codetheme.BG


# ------------------------------------------------------ syntax highlighting

def test_both_languages_are_highlighted():
    from ui.diffview import highlight_lines

    py = highlight_lines(["def f(x):", "    return x"], "python")
    ts = highlight_lines(["export function f(a: string) {", "  return a;"], "typescript")

    assert any('class="k"' in line for line in py)          # keyword tokens
    assert any("<span" in line for line in ts)


def test_a_multiline_string_does_not_break_line_alignment():
    """The reason the whole block is lexed at once: a line inside a docstring
    is only recognisable with the lines around it. Splitting afterwards is safe
    because Pygments closes and reopens its spans at every newline."""
    from ui.diffview import highlight_lines

    lines = ['def f():', '    """doc', '    spans', '    lines"""', '    return 1']
    rendered = highlight_lines(lines, "python")

    assert len(rendered) == len(lines)                      # rows stay in step
    for line in rendered:
        assert line.count("<span") == line.count("</span>")  # each row balanced


def test_an_unknown_language_falls_back_to_plain_text():
    """A new target language should render unhighlighted, not fail."""
    from ui.diffview import highlight_lines

    assert highlight_lines(["a < b"], "klingon") == ["a &lt; b"]
    assert highlight_lines(["a < b"], None) == ["a &lt; b"]


def test_highlighted_code_is_still_escaped():
    """Source text reaches the page as raw HTML either way — the highlighter
    must not become a way around the escaping."""
    from ui.diffview import highlight_lines

    rendered = highlight_lines(['x = "<img src=x>"'], "python")[0]
    assert "&lt;img src=x&gt;" in rendered
    assert "<img" not in rendered


def test_the_code_theme_is_one_switch():
    from ui.diffview import CODE_STYLE, STYLE

    assert CODE_STYLE.name == "tokyo-night"
    assert ".cs-diff .k" in STYLE          # Pygments rules, scoped to the panes
    assert "#1a1b26" in STYLE              # and the theme's own background
