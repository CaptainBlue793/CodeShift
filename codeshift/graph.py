"""Wires the CodeShift agents into a LangGraph StateGraph.

Two loops:
  * outer (per-file): `dispatch` selects the next unfinished module and routes
    to `translator`, or to `reviewer` when none remain.
  * inner (translate<->verify): `type_inference` routes back to `translator` when
    the target type oracle rejects the emitted code, short-circuiting the
    expensive differential run; otherwise `test_equivalence` routes back on
    semantic drift. Both share one `max_retries` budget per file, after which
    the module moves on to `idiom` with its failures recorded.

This module knows nothing about Python/TypeScript specifics — that lives in the
agents and adapters.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from codeshift.agents import (
    idiom,
    mapper,
    reviewer,
    test_equivalence,
    translator,
    type_inference,
)
from codeshift.state import MigrationState

_UNFINISHED = ("pending", "translated", "verified")


def _dispatch(state: MigrationState) -> dict:
    """Select the next module that is not yet idiomatic/failed."""
    files = state.get("files", {})
    for module in state.get("translation_order", []):
        unit = files.get(module)
        if unit and unit["status"] in _UNFINISHED:
            return {"current": module}
    return {"current": None}


def _route_after_dispatch(state: MigrationState) -> str:
    return "translator" if state.get("current") else "reviewer"


def _retries_left(state: MigrationState, unit) -> bool:
    return unit["attempts"] < state.get("max_retries", 3)


def _current_unit(state: MigrationState):
    current = state.get("current")
    return state.get("files", {}).get(current) if current else None


def _route_after_translator(state: MigrationState) -> str:
    """A rejected (empty/export-less) emission never reaches the oracles.

    Nothing was written, so type-checking would grade a stale file — and an
    empty module would pass. Go straight back with the rejection as feedback.
    """
    unit = _current_unit(state)
    if unit and unit.get("rejected") and _retries_left(state, unit):
        return "translator"
    return "type_inference"


def _route_after_type_inference(state: MigrationState) -> str:
    """Non-compiling code goes back to the translator without being run."""
    unit = _current_unit(state)
    if unit and unit.get("type_errors") and _retries_left(state, unit):
        return "translator"
    return "test_equivalence"


def _route_after_equivalence(state: MigrationState) -> str:
    unit = _current_unit(state)
    if unit and unit["divergences"] and _retries_left(state, unit):
        return "translator"
    return "idiom"


def build_graph():
    """Construct and compile the migration graph."""
    g = StateGraph(MigrationState)

    g.add_node("mapper", mapper.run)
    g.add_node("dispatch", _dispatch)
    g.add_node("translator", translator.run)
    g.add_node("type_inference", type_inference.run)
    g.add_node("test_equivalence", test_equivalence.run)
    g.add_node("idiom", idiom.run)
    g.add_node("reviewer", reviewer.run)

    g.add_edge(START, "mapper")
    g.add_edge("mapper", "dispatch")
    g.add_conditional_edges(
        "dispatch",
        _route_after_dispatch,
        {"translator": "translator", "reviewer": "reviewer"},
    )
    g.add_conditional_edges(
        "translator",
        _route_after_translator,
        {"translator": "translator", "type_inference": "type_inference"},
    )
    g.add_conditional_edges(
        "type_inference",
        _route_after_type_inference,
        {"translator": "translator", "test_equivalence": "test_equivalence"},
    )
    g.add_conditional_edges(
        "test_equivalence",
        _route_after_equivalence,
        {"translator": "translator", "idiom": "idiom"},
    )
    g.add_edge("idiom", "dispatch")
    g.add_edge("reviewer", END)

    return g.compile()
