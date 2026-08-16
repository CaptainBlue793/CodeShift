"""Tests for the differential-testing engine.

Input generation and diffing are pure. The Python source runner is exercised for
real. Cross-implementation drift detection is proven by running a correct vs. a
buggy Python implementation through the harness (no Node needed).
"""
from pathlib import Path

from codeshift.adapters.base import CallOutcome, FuncSig
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.equivalence.diff import classify_divergence
from codeshift.equivalence.harness import check_equivalence
from codeshift.equivalence.inputs import generate_inputs

FIXTURE = str(Path(__file__).resolve().parents[1] / "fixtures" / "sample_app")


# --- input generation ---

def test_generate_inputs_types():
    rows = generate_inputs(["int", "str"], n=10)
    assert len(rows) == 10
    for a, b in rows:
        assert isinstance(a, int) and isinstance(b, str)


def test_generate_inputs_no_args_is_single_empty_call():
    assert generate_inputs([], n=5) == [[]]


# --- signature extraction ---

def test_signatures_from_source():
    sigs = PythonSourceAdapter().signatures("def f(a: int, b: str) -> dict:\n    return {}\n")
    assert len(sigs) == 1
    assert sigs[0].name == "f"
    assert sigs[0].params == ["int", "str"]


# --- diff classification ---

def test_classify_equal_returns_none():
    assert classify_divergence("f", [1], CallOutcome(True, 2), CallOutcome(True, 2)) is None


def test_classify_value_mismatch():
    d = classify_divergence("f", [1], CallOutcome(True, 2), CallOutcome(True, 3))
    assert d is not None
    assert d["category"] == "value_mismatch"


def test_classify_exception_behavior():
    d = classify_divergence("f", [1], CallOutcome(True, 2), CallOutcome(False, error="TypeError"))
    assert d is not None
    assert d["category"] == "exception_behavior"


# --- real Python execution ---

def test_python_source_runner_executes_real_function():
    outs = PythonSourceAdapter().run(FIXTURE, "models", "make_user", [[1, "Ada"]])
    assert outs[0].ok
    assert outs[0].value == {"id": 1, "name": "Ada"}


# --- end-to-end drift detection (correct vs buggy implementation) ---

def test_harness_detects_real_drift(tmp_path):
    good, bad = tmp_path / "good", tmp_path / "bad"
    good.mkdir()
    bad.mkdir()
    (good / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    (bad / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8")

    adapter = PythonSourceAdapter()
    sigs = adapter.signatures((good / "calc.py").read_text(encoding="utf-8"))
    divergences, unverifiable, _ = check_equivalence(
        source_adapter=adapter,
        source_root=str(good),
        target_adapter=adapter,   # buggy dir stands in for the "target"
        target_root=str(bad),
        module="calc",
        signatures=sigs,
        n=15,
    )
    assert unverifiable == []
    assert divergences, "correct vs buggy add() should diverge"
    assert all(d["category"] == "value_mismatch" for d in divergences)


# --- unverifiable when target runtime is missing ---

class _UnavailableTarget:
    def run(self, root, module, func, inputs, ctor_inputs=None):
        return [CallOutcome(ok=False, error="runtime_unavailable") for _ in inputs]


def test_harness_flags_unverifiable_when_target_missing():
    adapter = PythonSourceAdapter()
    sigs = [FuncSig(name="make_user", params=["int", "str"])]
    divergences, unverifiable, _ = check_equivalence(
        source_adapter=adapter,
        source_root=FIXTURE,
        target_adapter=_UnavailableTarget(),
        target_root="unused",
        module="models",
        signatures=sigs,
        n=5,
    )
    assert [(u.name, u.reason) for u in unverifiable] == [("make_user", "runtime_unavailable")]
    assert divergences == []


# --- an unavailable sandbox is "never checked", never drift ---

class _UnsandboxedSource:
    """Stands in for a source runner that could not start at all."""
    def run(self, root, module, func, inputs, ctor_inputs=None):
        return [CallOutcome(ok=False, error="sandbox_unavailable") for _ in inputs]


class _WorkingTarget:
    def run(self, root, module, func, inputs, ctor_inputs=None):
        return [CallOutcome(ok=True, value=1) for _ in inputs]


def test_harness_reports_unavailable_sandbox_as_unverifiable_not_drift():
    """The failure mode this guards: a stopped Docker daemon makes every source
    call fail while the target returns fine, which reads as `exception_behavior`
    on every input — a wall of behavioral findings about code never executed."""
    sigs = [FuncSig(name="make_user", params=["int", "str"])]
    divergences, unverifiable, _ = check_equivalence(
        source_adapter=_UnsandboxedSource(),
        source_root="unused",
        target_adapter=_WorkingTarget(),
        target_root="unused",
        module="models",
        signatures=sigs,
        n=5,
    )
    assert divergences == []
    assert [(u.name, u.reason) for u in unverifiable] == [("make_user", "sandbox_unavailable")]


def test_harness_still_reports_genuine_source_errors_as_divergence():
    """The other side of the line: `source_run_error` is evidence, not infra."""
    class _BrokenSource:
        def run(self, root, module, func, inputs, ctor_inputs=None):
            return [CallOutcome(ok=False, error="source_run_error") for _ in inputs]

    divergences, unverifiable, _ = check_equivalence(
        source_adapter=_BrokenSource(),
        source_root="unused",
        target_adapter=_WorkingTarget(),
        target_root="unused",
        module="models",
        signatures=[FuncSig(name="f", params=[])],
    )
    assert unverifiable == []
    assert divergences and divergences[0]["category"] == "exception_behavior"


def test_check_equivalence_reuses_provided_inputs(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")
    adapter = PythonSourceAdapter()
    sigs = adapter.signatures((src / "calc.py").read_text(encoding="utf-8"))
    fixed = {"add": {"args": [[1, 2], [10, 20]], "ctor": None}}

    divergences, unverifiable, used = check_equivalence(
        source_adapter=adapter,
        source_root=str(src),
        target_adapter=adapter,   # same dir -> equivalent
        target_root=str(src),
        module="calc",
        signatures=sigs,
        inputs_by_func=fixed,
    )
    assert used["add"] == fixed["add"]   # reused, not regenerated
    assert divergences == []             # add vs add on identical source
