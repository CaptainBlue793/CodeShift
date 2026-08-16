"""Tests for the source (mypy) and target (tsc) type oracles.

The parsing layers are tested without a toolchain; the two live tests are
skipped when mypy or the Node toolchain is missing.
"""
import importlib.util
import textwrap

import pytest

from codeshift.adapters.python.type_extraction import (
    extract_types,
    module_file,
    normalize_type,
    parse_callable,
)
from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
from codeshift.adapters.typescript.typecheck import parse_diagnostics, tsc_available
from codeshift.graph import _route_after_type_inference
from codeshift.utils.typestr import parse_generic, split_top_level

# --------------------------------------------------------------- tsc parsing

TSC_OUTPUT = """\
main.ts(5,12): error TS2304: Cannot find name 'register'.
main.ts(8,5): error TS2591: Cannot find name 'require'. Do you need to install type definitions for node?
main.ts(8,22): error TS2591: Cannot find name 'module'.
utils.ts(3,9): error TS2345: Argument of type 'string' is not assignable to parameter of type 'number'.
"""


def test_parse_diagnostics_keeps_real_errors():
    diags = parse_diagnostics(TSC_OUTPUT)
    assert [d["code"] for d in diags] == ["TS2304", "TS2345"]
    first = diags[0]
    assert (first["file"], first["line"], first["column"]) == ("main.ts", 5, 12)
    assert first["severity"] == "error"
    assert first["message"] == "Cannot find name 'register'."


def test_parse_diagnostics_drops_ambient_node_noise():
    """TS2591 means "no @types/node here", not a translation defect."""
    assert all(d["code"] != "TS2591" for d in parse_diagnostics(TSC_OUTPUT))


def test_parse_diagnostics_ignores_node_builtin_imports_only():
    output = (
        "a.ts(1,1): error TS2307: Cannot find module 'node:fs' or its corresponding type declarations.\n"
        "b.ts(1,1): error TS2307: Cannot find module 'path' or its corresponding type declarations.\n"
        "c.ts(1,1): error TS2307: Cannot find module './models' or its corresponding type declarations.\n"
    )
    diags = parse_diagnostics(output)
    assert [d["file"] for d in diags] == ["c.ts"]  # a real broken relative import


def test_parse_diagnostics_ignores_non_diagnostic_lines():
    assert parse_diagnostics("npm warn deprecated foo\n\nFound 2 errors.\n") == []


def test_parse_diagnostics_relativizes_paths(tmp_path):
    (tmp_path / "pkg").mkdir()
    target = tmp_path / "pkg" / "mod.ts"
    target.write_text("export const x = 1;\n", encoding="utf-8")
    diags = parse_diagnostics(
        f"{target}(1,1): error TS2304: Cannot find name 'x'.", root=str(tmp_path)
    )
    assert diags[0]["file"] == "pkg/mod.ts"


# ------------------------------------------------------------- mypy parsing


def test_parse_callable_extracts_params_and_return():
    parsed = parse_callable("def (user_id: builtins.int, name: builtins.str) -> builtins.dict[Any, Any]")
    assert parsed == {
        "params": {"user_id": "int", "name": "str"},
        "returns": "dict[Any, Any]",
    }


def test_parse_callable_handles_defaults_and_varargs():
    parsed = parse_callable("def (a: builtins.int, b: builtins.str =, *args: Any) -> None")
    assert parsed is not None
    assert parsed["params"] == {"a": "int", "b": "str"}  # *args is not positionally testable


def test_parse_callable_handles_nested_generics():
    parsed = parse_callable(
        "def (m: builtins.dict[builtins.str, builtins.list[builtins.int]]) -> builtins.bool"
    )
    assert parsed is not None
    assert parsed["params"]["m"] == "dict[str, list[int]]"


def test_parse_callable_rejects_non_callables():
    assert parse_callable("builtins.int") is None


def test_normalize_type_simplifies_optional():
    assert normalize_type("Union[builtins.str, None]") == "Optional[str]"
    # A three-member union is not an Optional and must stay a Union.
    assert normalize_type("Union[builtins.str, builtins.int, None]").startswith("Union[")


def test_module_file_resolves_packages(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "mod.py").write_text("", encoding="utf-8")
    assert module_file(str(tmp_path), "mod") == tmp_path / "mod.py"
    assert module_file(str(tmp_path), "pkg") == tmp_path / "pkg" / "__init__.py"
    assert module_file(str(tmp_path), "nope") is None


# ------------------------------------------------------------ type strings


def test_split_top_level_respects_nesting():
    assert split_top_level("str, list[int, str], bool") == ["str", "list[int, str]", "bool"]


def test_parse_generic():
    assert parse_generic("list[int]") == ("list", ["int"])
    assert parse_generic("int") == ("int", None)
    assert parse_generic("typing.List[bool]") == ("List", ["bool"])


@pytest.mark.parametrize(
    "source_type, expected",
    [
        ("int", "number"),
        ("list[int]", "number[]"),
        ("list[list[str]]", "string[][]"),
        ("dict[str, int]", "Record<string, number>"),
        ("dict[Any, Any]", "Record<string, any>"),      # a plain dict
        ("dict[tuple[int, int], str]", "Map<[number, number], string>"),
        ("Optional[str]", "string | null"),
        ("str | None", "string | null"),
        ("Union[int, str]", "number | string"),
        ("tuple[int, str]", "[number, string]"),
        ("tuple[int, ...]", "number[]"),
        ("set[str]", "Set<string>"),
        ("Sequence[float]", "number[]"),
        ("Nonexistent[int]", "unknown"),
        ("", "unknown"),
    ],
)
def test_map_type_handles_generics(source_type, expected):
    assert TypeScriptTargetAdapter().map_type(source_type) == expected


# ----------------------------------------------------------------- routing


def _unit(**overrides):
    unit = {"attempts": 1, "type_errors": [], "divergences": []}
    unit.update(overrides)
    return unit


def _state(unit, max_retries=3):
    return {"current": "m", "max_retries": max_retries, "files": {"m": unit}}


def test_route_back_to_translator_on_type_errors():
    state = _state(_unit(type_errors=[{"code": "TS2304"}]))
    assert _route_after_type_inference(state) == "translator"


def test_route_forward_when_clean():
    assert _route_after_type_inference(_state(_unit())) == "test_equivalence"


def test_route_forward_when_retries_exhausted():
    """Out of budget: run the differential test anyway rather than looping."""
    state = _state(_unit(type_errors=[{"code": "TS2304"}], attempts=3), max_retries=3)
    assert _route_after_type_inference(state) == "test_equivalence"


# -------------------------------------------------------------- live oracles


@pytest.mark.skipif(
    importlib.util.find_spec("mypy") is None, reason="mypy not importable"
)
def test_extract_types_resolves_bare_generics(tmp_path):
    """mypy's contribution: concrete type arguments for bare containers.

    Note what it does *not* do — `tally` has no return annotation and mypy
    leaves it `Any` rather than inferring `int`. mypy only infers variable
    types, never a function's return type; that needs pyright.
    """
    code = textwrap.dedent(
        """\
        def tally(items: list[int]):
            return len(items)


        def pack(name: str) -> dict:
            return {"name": name}
        """
    )
    (tmp_path / "m.py").write_text(code, encoding="utf-8")
    types = extract_types(str(tmp_path), "m", code)
    assert types["tally"]["params"] == {"items": "list[int]"}
    assert types["tally"]["returns"] == "Any"
    assert types["pack"]["returns"] == "dict[Any, Any]"   # source said bare `dict`


def test_extract_types_returns_empty_for_unknown_module(tmp_path):
    assert extract_types(str(tmp_path), "missing", "def f(): pass\n") == {}


@pytest.mark.skipif(not tsc_available(), reason="Node toolchain (node/npx) not available")
def test_tsc_oracle_catches_undefined_name(tmp_path):
    (tmp_path / "broken.ts").write_text(
        "export function run(): number {\n  return missingHelper();\n}\n", encoding="utf-8"
    )
    diags = TypeScriptTargetAdapter().typecheck(str(tmp_path))
    assert any(d["code"] == "TS2304" and d["file"] == "broken.ts" for d in diags)


@pytest.mark.skipif(not tsc_available(), reason="Node toolchain (node/npx) not available")
def test_tsc_oracle_clean_on_valid_code(tmp_path):
    (tmp_path / "ok.ts").write_text(
        "export function add(a: number, b: number): number {\n  return a + b;\n}\n",
        encoding="utf-8",
    )
    assert TypeScriptTargetAdapter().typecheck(str(tmp_path)) == []
