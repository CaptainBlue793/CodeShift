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
    assert "CodeShift" in app.title[0].value


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
    return next(m.value for m in app.metric if m.label == label)


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

def _three_col(first, shipped, attempts=1):
    return _render_with({"utils": {
        "module": "utils", "path": "utils.py", "status": "idiomatic",
        "attempts": attempts, "source_code": "def slugify(text):\n    return text\n",
        "first_code": first, "translated_code": shipped, "target_path": "utils.ts",
        "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
        "unverified": [],
    }})


def _captions(app):
    return " ".join(c.value for c in app.caption)


def test_unchanged_module_says_so_instead_of_highlighting():
    code = "export function slugify(text: string) {\n  return text;\n}\n"
    app = _three_col(code, code)

    assert "no retries, no edits" in _captions(app)


def test_formatting_only_difference_is_not_sold_as_a_fix():
    app = _three_col(
        "export function slugify(text: string){return text;}",
        "export function slugify(text: string) {\n  return text;\n}\n",
    )
    assert "formatting only" in _captions(app)


def test_real_change_is_reported_as_a_retry_fix():
    app = _three_col(
        "export function slugify(text: string) {\n  return text.split(/\\s+/);\n}\n",
        "export function slugify(text: string) {\n  return text.split(/[\\s\\x1c]+/);\n}\n",
        attempts=2,
    )
    captions = _captions(app)
    assert "line(s) changed" in captions
    assert "retry loop" in captions


def test_missing_first_code_does_not_break_the_view():
    """Snapshots from runs predating `first_code` must still render."""
    app = _render_with({"utils": {
        "module": "utils", "path": "utils.py", "status": "idiomatic", "attempts": 1,
        "source_code": "def slugify(text):\n    return text\n",
        "translated_code": "export function slugify(t: string) { return t; }",
        "divergences": [], "type_errors": [], "verified_functions": ["slugify"],
        "unverified": [],
    }})
    assert "no retries, no edits" in _captions(app)
