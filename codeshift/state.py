"""LangGraph shared-state schema for a single migration run.

The graph nodes (agents) each receive the whole `MigrationState` and return a
partial dict update. `files` is keyed by dotted module name; the per-file loop
walks `translation_order`.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict, cast

FileStatus = Literal["pending", "translated", "verified", "idiomatic", "failed"]


class FileUnit(TypedDict):
    module: str                      # dotted module name (the `files` key)
    path: str                        # relative source path
    imports: list[str]               # internal modules this module depends on
    source_code: str
    translated_code: Optional[str]
    first_code: Optional[str]        # the first accepted emission, kept for the retry diff
    target_path: Optional[str]       # emitted target file, relative to output_root
    symbol_map: dict[str, str]       # source callable name -> the target's name for it
    inferred_types: Optional[dict]
    type_errors: list[dict]          # target type-oracle diagnostics for this module
    status: FileStatus
    attempts: int                    # translate<->verify attempts so far
    divergences: list[dict]          # populated by the test-equivalence agent
    verified_functions: list[str]    # callables actually run on both sides and compared
    unverified: list[dict]           # {"name", "reason"} per construct never compared
    #: Per-callable inputs, generated once and reused across retries. Each value
    #: is `{"args": [...], "ctor": [...] | None}` — see `equivalence.harness`.
    test_inputs: dict[str, dict]
    rejected: Optional[str]          # why the last emission was discarded unwritten
    best: Optional[dict]             # best-scoring attempt so far (see codeshift.candidates)


class MigrationState(TypedDict, total=False):
    source_root: str
    output_root: str
    source_lang: str                 # v1: "python"
    target_lang: str                 # v1: "typescript"
    dep_graph: dict                  # serialized networkx DAG (node_link_data)
    translation_order: list[str]     # topologically sorted module names
    files: dict[str, FileUnit]
    current: Optional[str]           # module being processed now
    max_retries: int
    isolation: Optional[str]         # isolation the differential run got (sandbox.policy)
    report: Optional[str]
    errors: list[str]


def new_state(
    *,
    source_root: str,
    output_root: str,
    source_lang: str,
    target_lang: str,
    max_retries: int,
) -> MigrationState:
    """Build the initial state for a run."""
    return MigrationState(
        source_root=source_root,
        output_root=output_root,
        source_lang=source_lang,
        target_lang=target_lang,
        dep_graph={},
        translation_order=[],
        files={},
        current=None,
        max_retries=max_retries,
        isolation=None,
        report=None,
        errors=[],
    )


def get_files(state: MigrationState) -> dict[str, FileUnit]:
    """Typed shallow copy of the state's files map (safe to mutate)."""
    return cast("dict[str, FileUnit]", dict(state.get("files") or {}))


def copy_unit(unit: FileUnit) -> FileUnit:
    """Typed shallow copy of a FileUnit (safe to mutate before writing back)."""
    return cast(FileUnit, dict(unit))
