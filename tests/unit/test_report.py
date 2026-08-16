"""Tests for the reviewer's migration-report builder."""
from codeshift.report.builder import build_report


def _state():
    return {
        "source_lang": "python",
        "target_lang": "typescript",
        "source_root": "src",
        "output_root": "out",
        "translation_order": ["models", "service", "main"],
        "files": {
            "models": {
                "module": "models", "status": "idiomatic", "attempts": 1,
                "divergences": [], "verified_functions": ["make_user"], "unverified": [],
            },
            "service": {
                "module": "service", "status": "idiomatic", "attempts": 3,
                "divergences": [
                    {"function": "register", "args": [1, "x"],
                     "category": "value_mismatch", "detail": "source=A target=B"}
                ],
                "verified_functions": ["register"],
                "unverified": [],
            },
            "main": {
                "module": "main", "status": "verified", "attempts": 1,
                "divergences": [], "verified_functions": [],
                "unverified": [{"name": "run", "reason": "runtime_unavailable"}],
            },
        },
        "errors": [],
    }


def test_report_header_and_summary_counts():
    r = build_report(_state())
    assert r.startswith("# CodeShift Migration Report")
    assert "3 module(s)" in r
    assert "1 verified equivalent" in r      # only models was checked and clean
    assert "1 with unresolved drift" in r    # service
    assert "1 never verified" in r           # main: nothing was executed


def test_report_table_and_details():
    r = build_report(_state())
    assert "| 2 | service |" in r            # ordered table row
    assert "unresolved behavioral drift" in r
    assert "register" in r                   # divergence detail
    assert "value_mismatch" in r
    assert "### main (not verified)" in r    # its own section, with the verdict
    assert "the target runtime was unavailable" in r   # the reason, spelled out


def test_report_names_circular_imports_and_where_they_were_broken():
    """A cycle changes what the table means: one module in it was translated
    before its own dependencies existed, so the report has to say which."""
    state = _state()
    state["cycles"] = [["customers", "orders"]]
    r = build_report(state)
    assert "Circular imports" in r
    assert "`customers` -> `orders`" in r
    assert "broken at **`customers`**" in r


def test_report_says_nothing_about_cycles_when_there_are_none():
    assert "Circular imports" not in build_report(_state())


def test_report_empty_project():
    r = build_report({
        "source_lang": "python", "target_lang": "typescript",
        "source_root": "src", "output_root": "out",
        "translation_order": [], "files": {}, "errors": [],
    })
    assert "0 module(s)" in r
    assert "0 verified equivalent" in r


# --- the silent pass this section exists to prevent ---

def _one_module(unit: dict) -> dict:
    return {
        "source_lang": "python", "target_lang": "typescript",
        "source_root": "src", "output_root": "out",
        "translation_order": ["mod"], "files": {"mod": {"module": "mod", **unit}},
        "errors": [],
    }


def test_untested_module_is_not_counted_as_verified():
    """A module of classes yields no signatures, so it diverges zero times.

    That must not read as success anywhere in the report.
    """
    r = build_report(_one_module({
        "status": "idiomatic", "attempts": 1, "divergences": [],
        "verified_functions": [],
        "unverified": [{"name": "User", "reason": "class"}],
    }))
    assert "0 verified equivalent" in r
    assert "1 never verified" in r
    assert "Not verified - no behavioral evidence" in r
    assert "classes are not differential-tested" in r


def test_partially_verified_module_is_called_out():
    r = build_report(_one_module({
        "status": "idiomatic", "attempts": 1, "divergences": [],
        "verified_functions": ["slugify"],
        "unverified": [{"name": "Session", "reason": "class"}],
    }))
    assert "0 verified equivalent" in r
    assert "1 only partially verified" in r
    assert "### mod (partial)" in r


def test_module_with_nothing_runnable_is_neither_verified_nor_flagged():
    """An `__init__.py` has no functions and no classes — that is not a failure."""
    r = build_report(_one_module({
        "status": "idiomatic", "attempts": 1, "divergences": [],
        "verified_functions": [], "unverified": [],
    }))
    assert "0 verified equivalent" in r
    assert "1 with nothing to run" in r
    assert "Not verified - no behavioral evidence" not in r


def test_type_errors_block_a_verified_claim():
    r = build_report(_one_module({
        "status": "idiomatic", "attempts": 3, "divergences": [],
        "verified_functions": ["slugify"], "unverified": [],
        "type_errors": [{"file": "mod.ts", "line": 2, "column": 1,
                         "code": "TS2322", "message": "type mismatch"}],
    }))
    assert "0 verified equivalent" in r
    assert "1 that do not type-check" in r
