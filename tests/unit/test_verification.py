"""Tests for the verified/unverified distinction.

The bug this guards: an empty `divergences` list means both "compared and
matched" and "never compared", and every consumer used to read it as the former.
"""
from codeshift.adapters import registry
from codeshift.adapters.base import CallOutcome
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.agents import test_equivalence
from codeshift.verification import (
    is_trustworthy,
    unverified_by_reason,
    unverified_names,
    verdict,
)


def _unit(**over) -> dict:
    base = {
        "divergences": [], "verified_functions": [], "unverified": [], "type_errors": [],
    }
    base.update(over)
    return base


# --- verdict ---

def test_checked_and_clean_is_verified():
    assert verdict(_unit(verified_functions=["f"])) == "verified"
    assert is_trustworthy(_unit(verified_functions=["f"]))


def test_nothing_checked_but_something_skipped_is_unverified():
    unit = _unit(unverified=[{"name": "User", "reason": "class"}])
    assert verdict(unit) == "unverified"
    assert not is_trustworthy(unit)


def test_some_checked_some_skipped_is_partial():
    unit = _unit(
        verified_functions=["f"], unverified=[{"name": "User", "reason": "class"}]
    )
    assert verdict(unit) == "partial"
    assert not is_trustworthy(unit)


def test_nothing_at_all_is_empty_not_verified():
    assert verdict(_unit()) == "empty"
    assert not is_trustworthy(_unit())


def test_drift_outranks_coverage():
    unit = _unit(
        verified_functions=["f"],
        divergences=[{"function": "f", "category": "value_mismatch"}],
        unverified=[{"name": "User", "reason": "class"}],
    )
    assert verdict(unit) == "drift"


def test_type_errors_are_not_trustworthy_even_when_verified():
    unit = _unit(verified_functions=["f"], type_errors=[{"code": "TS2322"}])
    assert verdict(unit) == "verified"          # behaviorally, yes
    assert not is_trustworthy(unit)             # but it does not compile


def test_missing_keys_do_not_imply_success():
    """A FileUnit from an older run, or one that never reached equivalence."""
    assert verdict({}) == "empty"
    assert not is_trustworthy({})


# --- helpers ---

def test_unverified_names_and_grouping():
    unit = _unit(unverified=[
        {"name": "User", "reason": "class"},
        {"name": "Session", "reason": "class"},
        {"name": "fetch", "reason": "runtime_unavailable"},
    ])
    assert unverified_names(unit) == ["User", "Session", "fetch"]
    assert unverified_by_reason(unit) == {
        "class": ["User", "Session"],
        "runtime_unavailable": ["fetch"],
    }


# --- the source adapter's half of the contract ---

def test_reachable_methods_are_signatures_async_defs_are_not():
    src = (
        "class User:\n"
        "    def name(self) -> str:\n"
        "        return 'x'\n"
        "\n"
        "async def fetch(url: str) -> str:\n"
        "    return url\n"
        "\n"
        "def slugify(text: str) -> str:\n"
        "    return text\n"
    )
    adapter = PythonSourceAdapter()

    assert [s.name for s in adapter.signatures(src)] == ["User.name", "slugify"]
    assert [(u.name, u.reason) for u in adapter.untestable(src)] == [
        ("fetch", "async_function"),
    ]


def test_untestable_names_each_unreachable_method_not_just_the_class():
    """A skipped method is named on its own: "not checked: A" would not say which."""
    src = (
        "class A:\n"
        "    async def fetched(self): pass\n"
        "    def _hidden(self): pass\n"
        "    @property\n"
        "    def size(self): return 0\n"
    )
    assert [(u.name, u.reason) for u in PythonSourceAdapter().untestable(src)] == [
        ("A.fetched", "async_method"),
        ("A._hidden", "private_method"),
        ("A.size", "property"),
    ]


def test_a_class_that_cannot_be_built_is_reported_once_against_the_class():
    """No receiver, so no method is reachable — but the gap still gets named."""
    src = "class Session(Base):\n    def open(self): pass\n"
    assert [(u.name, u.reason) for u in PythonSourceAdapter().untestable(src)] == [
        ("Session.open", "inherited_constructor"),
    ]
    assert PythonSourceAdapter().signatures(src) == []


def test_untestable_on_plain_functions_is_empty():
    assert PythonSourceAdapter().untestable("def f(a: int) -> int:\n    return a\n") == []


def test_untestable_survives_a_syntax_error():
    assert PythonSourceAdapter().untestable("def broken(:\n") == []


# --- the agent that has to put the two halves together ---

def _state(source_code: str, root: str) -> dict:
    return {
        "source_lang": "python", "target_lang": "typescript",
        "source_root": root, "output_root": root, "current": "mod",
        "files": {"mod": {
            "module": "mod", "path": "mod.py", "imports": [],
            "source_code": source_code, "translated_code": None, "symbol_map": {},
            "status": "translated", "attempts": 1,
            "divergences": [], "verified_functions": [], "unverified": [],
        }},
    }


class _NeverRuns:
    """A target that fails the test if the harness tries to execute anything."""

    def run(self, *args, **kwargs):
        raise AssertionError("no signatures were extracted; nothing should run")


def test_agent_flags_an_unreachable_class_as_unverified(monkeypatch):
    """The original silent pass: no signatures, no divergences, ergo "verified".

    Reachable classes are executed now, so the module that still has nothing to
    run is one whose class cannot be constructed.
    """
    monkeypatch.setattr(registry, "target", lambda lang, output_root: _NeverRuns())

    state = _state("class User(Base):\n    def name(self):\n        return 'x'\n", "unused")
    unit = test_equivalence.run(state)["files"]["mod"]

    assert unit["divergences"] == []                 # as before...
    assert unit["verified_functions"] == []          # ...but now we know why
    assert unit["unverified"] == [{"name": "User.name", "reason": "inherited_constructor"}]
    assert verdict(unit) == "unverified"
    assert not is_trustworthy(unit)


def test_agent_marks_a_genuinely_checked_module_verified(monkeypatch, tmp_path):
    """Same source on both sides, so the comparison is real and must pass."""
    src = "def add(a: int, b: int) -> int:\n    return a + b\n"
    (tmp_path / "mod.py").write_text(src, encoding="utf-8")
    # The Python adapter stands in for the target, pointed at the same tree.
    monkeypatch.setattr(registry, "target", lambda lang, output_root: PythonSourceAdapter())

    unit = test_equivalence.run(_state(src, str(tmp_path)))["files"]["mod"]

    assert unit["verified_functions"] == ["add"]
    assert unit["unverified"] == []
    assert verdict(unit) == "verified"
    assert is_trustworthy(unit)


def test_agent_separates_the_two_reasons_for_being_unchecked(monkeypatch):
    """A class the harness cannot reach, and a function it cannot run.

    The report groups by reason, so the two must not be flattened together.
    """
    class _Unavailable:
        def run(self, root, module, func, inputs, ctor_inputs=None):
            return [CallOutcome(ok=False, error="runtime_unavailable") for _ in inputs]

    monkeypatch.setattr(registry, "target", lambda lang, output_root: _Unavailable())

    src = "class User(Base):\n    pass\n\n\ndef add(a: int, b: int) -> int:\n    return a + b\n"
    unit = test_equivalence.run(_state(src, "unused"))["files"]["mod"]

    assert unverified_by_reason(unit) == {
        "inherited_constructor": ["User"],
        "runtime_unavailable": ["add"],
    }
    assert unit["verified_functions"] == []
    assert verdict(unit) == "unverified"
