"""Build the module dependency DAG and derive the translation order.

An edge dep -> module means `dep` must be translated before `module`, so a
topological sort yields a safe translation order.
"""
from __future__ import annotations

import networkx as nx

from codeshift.adapters.base import ParsedProject


def build_order(project: ParsedProject) -> tuple[dict, list[str]]:
    """Return (serialized graph, topologically sorted module names)."""
    g = nx.DiGraph()
    for mod in project.modules:
        g.add_node(mod.module)
        for dep in mod.imports:
            g.add_edge(dep, mod.module)   # dep before module

    # TODO: detect and break cycles (nx.simple_cycles) before sorting; a real
    # codebase may have circular imports that need special handling.
    order = list(nx.topological_sort(g)) if g.number_of_nodes() else []
    return nx.node_link_data(g, edges="links"), order
