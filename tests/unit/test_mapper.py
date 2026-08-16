"""Tests for the dependency/structure mapper (parse + translation order)."""
from pathlib import Path

from codeshift.adapters.base import ParsedModule, ParsedProject
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.depgraph.builder import build_order

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE = str(FIXTURES / "sample_app")
CYCLIC = str(FIXTURES / "cyclic_app")


def _parse():
    return PythonSourceAdapter().parse(FIXTURE)


def _project(**deps: list[str]) -> ParsedProject:
    """A project from a {module: [dependencies]} sketch."""
    return ParsedProject(
        modules=[
            ParsedModule(module=name, path=f"{name}.py", source_code="", imports=list(imports))
            for name, imports in deps.items()
        ]
    )


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
    plan = build_order(_parse())
    order = plan.order
    assert set(order) == {"models", "utils", "service", "main"}
    assert order.index("models") < order.index("service")
    assert order.index("utils") < order.index("service")
    assert order.index("service") < order.index("main")
    assert plan.cycles == []          # an acyclic project reports no cycles


# --- circular imports ---------------------------------------------------
# A plain topological sort raises NetworkXUnfeasible on any cycle, which is
# what every real codebase would have hit. Cycles are now condensed, ordered
# and reported instead.

def test_a_cycle_no_longer_raises_and_still_orders_everything():
    plan = build_order(PythonSourceAdapter().parse(CYCLIC))
    assert set(plan.order) == {"models", "customers", "orders"}
    # Whatever happens inside the cycle, a dependency outside it still comes first.
    assert plan.order.index("models") == 0
    assert plan.cycles == [["customers", "orders"]]


def test_a_cycle_is_broken_at_its_least_dependent_member():
    """Fewest dependencies *within* the cycle goes first: that module is
    missing the least context when translated ahead of its dependents."""
    # b and c depend on each other; c also depends on b's other partner a.
    plan = build_order(_project(a=[], b=["c"], c=["b", "a"]))
    assert plan.cycles == [["b", "c"]]
    assert plan.order.index("b") < plan.order.index("c")


def test_a_module_importing_itself_counts_as_a_cycle():
    """A one-member component would otherwise slip past a `len > 1` check."""
    plan = build_order(_project(solo=["solo"]))
    assert plan.order == ["solo"]
    assert plan.cycles == [["solo"]]


def test_two_independent_cycles_are_reported_separately():
    plan = build_order(_project(a=["b"], b=["a"], x=["y"], y=["x"]))
    assert plan.cycles == [["a", "b"], ["x", "y"]]


def test_order_is_deterministic():
    """A nondeterministic model downstream is reason enough to pin down
    everything upstream that can be pinned."""
    sketch = dict(main=["service"], service=["models", "utils"], models=[], utils=[])
    orders = {tuple(build_order(_project(**sketch)).order) for _ in range(5)}
    assert len(orders) == 1


def test_an_empty_project_produces_an_empty_plan():
    plan = build_order(ParsedProject())
    assert plan.order == [] and plan.cycles == []
