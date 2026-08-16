"""Tests for the dependency/structure mapper (parse + translation order)."""
from pathlib import Path

from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.depgraph.builder import build_order

FIXTURE = str(Path(__file__).resolve().parents[1] / "fixtures" / "sample_app")


def _parse():
    return PythonSourceAdapter().parse(FIXTURE)


def test_discovers_all_modules():
    names = {m.module for m in _parse().modules}
    assert names == {"models", "utils", "service", "main"}


def test_resolves_internal_imports_only():
    deps = {m.module: set(m.imports) for m in _parse().modules}
    assert deps["service"] == {"models", "utils"}
    assert deps["main"] == {"service"}
    assert deps["models"] == set()
    assert deps["utils"] == set()


def test_translation_order_respects_dependencies():
    _, order = build_order(_parse())
    assert set(order) == {"models", "utils", "service", "main"}
    assert order.index("models") < order.index("service")
    assert order.index("utils") < order.index("service")
    assert order.index("service") < order.index("main")
