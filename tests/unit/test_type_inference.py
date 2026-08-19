"""Tests for the type-inference agent: extraction, mapping, and wiring."""
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
from codeshift.agents import idiom, test_equivalence, translator, type_inference
from codeshift.state import FileUnit
from codeshift.typing_hints import build_type_hints


def test_infer_types_annotated():
    t = PythonSourceAdapter().infer_types("def f(a: int, b: str) -> bool:\n    return True\n")
    assert t["f"]["params"] == {"a": "int", "b": "str"}
    assert t["f"]["returns"] == "bool"


def test_infer_types_unannotated_is_any():
    t = PythonSourceAdapter().infer_types("def g(x):\n    return x\n")
    assert t["g"]["params"] == {"x": "Any"}
    assert t["g"]["returns"] == "Any"


def test_map_type():
    ta = TypeScriptTargetAdapter()
    assert ta.map_type("int") == "number"
    assert ta.map_type("str") == "string"
    assert ta.map_type("bool") == "boolean"
    assert ta.map_type("float") == "number"
    assert ta.map_type("dict") == "Record<string, unknown>"
    assert ta.map_type("None") == "null"
    assert ta.map_type("Any") == "any"
    assert ta.map_type("Nonexistent") == "unknown"


def test_build_type_hints():
    hints = build_type_hints(
        PythonSourceAdapter(),
        TypeScriptTargetAdapter(),
        "def make_user(user_id: int, name: str) -> dict:\n    return {}\n",
    )
    assert hints["make_user"]["params"] == {"user_id": "number", "name": "string"}
    assert hints["make_user"]["returns"] == "Record<string, unknown>"


def test_agent_populates_inferred_types():
    src = "def make_user(user_id: int, name: str) -> dict:\n    return {}\n"
    state = {
        "source_lang": "python", "target_lang": "typescript", "output_root": "data/output",
        "current": "models",
        "files": {"models": {
            "module": "models", "path": "models.py", "imports": [],
            "source_code": src, "translated_code": None, "symbol_map": {},
            "inferred_types": None, "status": "translated", "attempts": 1,
            "divergences": [], "unverified": [],
        }},
    }
    inferred = type_inference.run(state)["files"]["models"]["inferred_types"]
    assert inferred["source"]["make_user"]["returns"] == "dict"
    assert inferred["target"]["make_user"]["params"]["user_id"] == "number"
    assert inferred["target"]["make_user"]["returns"] == "Record<string, unknown>"


# ------------------------------- nodes that skip must still write state


def _rejected_state():
    """A module whose final emission was rejected as degenerate."""
    return {
        "source_lang": "python",
        "target_lang": "typescript",
        "output_root": "data/output",
        "current": "core.text",
        "max_retries": 3,
        "files": {
            "core.text": FileUnit(
                module="core.text",
                path="core/text.py",
                imports=[],
                source_code="def slug(t: str) -> str:\n    return t\n",
                translated_code="export function slug(t: string) { return t; }",
                inferred_types=None,
                status="translated",
                attempts=3,
                divergences=[],
                rejected="the model returned no code at all",
            )
        },
    }


def test_a_skipping_node_writes_state_back_instead_of_returning_nothing():
    """LangGraph raises `InvalidUpdateError` on an empty update.

    Found by a 31-module run, not by the fixtures: the path needs an emission
    rejected as degenerate *on its last attempt*, so the graph cannot loop back
    to the translator and hands a rejected unit to a node with nothing to do.
    On a 4-module project that combination never came up.
    """
    update = type_inference.run(_rejected_state())
    assert update, "a node that skips must still write at least one state key"
    assert update["files"]["core.text"]["rejected"]


def test_a_node_with_no_current_module_writes_state_back():
    state = _rejected_state()
    state["current"] = None
    for node in (translator, type_inference, test_equivalence, idiom):
        assert node.run(state), f"{node.__name__} returned an empty update"
