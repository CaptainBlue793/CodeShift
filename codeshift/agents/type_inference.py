"""Type-inference agent — dynamic (Python) -> static (TypeScript) typing.

Two jobs, both feeding the translator:

1. Extract the source module's declared/inferred types (mypy oracle, falling
   back to declared annotations) and map them into the target type system.
   These become the translator's type hints and land in the migration report.
2. Run the *target* type oracle (tsc) over the emitted code. Code that does not
   compile is sent straight back to the translator by the graph, before the far
   more expensive differential run — a `Cannot find name` is both cheaper to
   detect and clearer to act on than the `ReferenceError` it would surface as.
"""
from __future__ import annotations

from codeshift.adapters import registry
from codeshift.config import settings
from codeshift.state import MigrationState, copy_unit, get_files, unchanged
from codeshift.typing_hints import map_types
from codeshift.utils.logging import get_logger

log = get_logger(__name__)


def _diagnostics_for(unit_path: str | None, diagnostics: list[dict]) -> list[dict]:
    """Keep only diagnostics raised in this module's own emitted file.

    Errors in dependencies belong to those modules' retry budgets; blaming the
    current module for them would loop on code it cannot fix.
    """
    if not unit_path:
        return []
    want = unit_path.replace("\\", "/")
    return [d for d in diagnostics if str(d.get("file", "")).replace("\\", "/") == want]


def run(state: MigrationState) -> dict:
    module = state.get("current")
    files = get_files(state)
    if not module or module not in files:
        return unchanged(state)

    # Reached only when a rejected emission has also run out of retries: the
    # graph loops back to the translator otherwise. Nothing new was written, so
    # keep the rejection as the recorded failure instead of grading a stale file.
    if files[module].get("rejected"):
        return unchanged(state)

    unit = copy_unit(files[module])
    source = registry.source(state.get("source_lang", "python"))
    target = registry.target(
        state.get("target_lang", "typescript"),
        output_root=state.get("output_root", "data/output"),
    )

    source_types = source.infer_types(
        unit["source_code"],
        root=state.get("source_root"),
        module=module,
    )
    target_hints = map_types(target, source_types)   # reuse the run above
    unit["inferred_types"] = {"source": source_types, "target": target_hints}

    type_errors: list[dict] = []
    if settings.use_tsc_oracle:
        all_diagnostics = target.typecheck(state.get("output_root", "data/output"))
        type_errors = _diagnostics_for(unit.get("target_path"), all_diagnostics)
    unit["type_errors"] = type_errors

    files[module] = unit
    log.info(
        "type_inference: %s -> typed %d function(s), %d type error(s)",
        module,
        len(source_types),
        len(type_errors),
    )
    return {"files": files}
