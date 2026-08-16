"""Tests for the type-inference agent: extraction, mapping, and wiring."""
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
from codeshift.agents import type_inference
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
