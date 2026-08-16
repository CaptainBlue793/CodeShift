"""Dependency/structure mapper — builds the DAG and the translation order.

Runs once at the start: parses the source project via the source adapter, builds
a networkx dependency graph, topologically sorts it, and seeds `state["files"]`
with one FileUnit per module (status="pending").
"""
from __future__ import annotations

from codeshift.adapters import registry
from codeshift.depgraph.builder import build_order
from codeshift.state import FileUnit, MigrationState
from codeshift.utils.logging import get_logger

log = get_logger(__name__)


def run(state: MigrationState) -> dict:
    src = registry.source(state["source_lang"])
    project = src.parse(state["source_root"])
    dep_graph, order = build_order(project)

    files: dict[str, FileUnit] = {}
    for mod in project.modules:
        files[mod.module] = FileUnit(
            module=mod.module,
            path=mod.path,
            imports=mod.imports,
            source_code=mod.source_code,
            translated_code=None,
            first_code=None,
            target_path=None,
            symbol_map={},
            inferred_types=None,
            type_errors=[],
            status="pending",
            attempts=0,
            divergences=[],
            verified_functions=[],
            unverified=[],
            test_inputs={},
            rejected=None,
            best=None,
        )

    log.info("mapper: %d modules discovered; translation order: %s", len(files), order)
    # TODO(mapper): optionally resolve ambiguous/dynamic refs with the LLM
    #   (prompts/mapper.md) before finalizing the order.
    return {"dep_graph": dep_graph, "translation_order": order, "files": files}
