"""Build the module dependency graph and derive the translation order.

An edge dep -> module means `dep` must be translated before `module`, so a
topological sort yields a safe translation order.

Real codebases are not acyclic, though, and a plain topological sort raises on
the first circular import. So the graph is condensed into its strongly-connected
components first: every cycle collapses to one node, the condensation is always
a DAG, and sorting *that* always succeeds. Each cycle is then expanded into a
deterministic internal order and reported, because a module translated before
one of its own dependencies got less context than the pipeline normally
guarantees — the translator degrades quietly there, and quiet degradation is
exactly what should show up in the report.

Ordering is lexicographic throughout, so the same project always produces the
same order. With a nondeterministic model downstream, the parts that *can* be
reproducible should be.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from codeshift.adapters.base import ParsedProject


@dataclass
class TranslationPlan:
    """The dependency graph, the order to walk it, and the cycles found."""
    graph: dict                                   # serialized networkx digraph
    order: list[str] = field(default_factory=list)
    #: One entry per circular-import group, in the order they will be
    #: translated. The first name in each is the module the cycle was broken
    #: at — the one translated without all of its dependencies available.
    cycles: list[list[str]] = field(default_factory=list)


def _order_within(graph: nx.DiGraph, members: set[str]) -> list[str]:
    """Order one strongly-connected component.

    Fewest dependencies *inside the cycle* first: that module is missing the
    least context when it is translated ahead of its own dependents. Ties break
    alphabetically so the result is stable.
    """
    if len(members) == 1:
        return list(members)
    sub = graph.subgraph(members)
    return sorted(members, key=lambda n: (sub.in_degree(n), n))


def build_order(project: ParsedProject) -> TranslationPlan:
    """Return the translation plan for a parsed project."""
    graph = nx.DiGraph()
    for mod in project.modules:
        graph.add_node(mod.module)
        for dep in mod.imports:
            graph.add_edge(dep, mod.module)   # dep before module

    serialized = nx.node_link_data(graph, edges="links")
    if not graph.number_of_nodes():
        return TranslationPlan(graph=serialized)

    # Every SCC becomes one node, so the result is a DAG even when the source
    # is not. `members` is the set of modules that collapsed into it.
    condensed = nx.condensation(graph)
    order: list[str] = []
    cycles: list[list[str]] = []

    for scc in nx.lexicographical_topological_sort(
        condensed, key=lambda n: min(condensed.nodes[n]["members"])
    ):
        members = condensed.nodes[scc]["members"]
        ordered = _order_within(graph, members)
        order.extend(ordered)
        # A single module that imports itself is a cycle too, and `len > 1`
        # would miss it.
        if len(members) > 1 or graph.has_edge(ordered[0], ordered[0]):
            cycles.append(ordered)

    return TranslationPlan(graph=serialized, order=order, cycles=cycles)
