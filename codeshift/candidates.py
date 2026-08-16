"""Track the best attempt per module, so a run that improves then regresses
does not ship the regression.

The retry loop is not monotonic. Fixing a type error lets a module reach the
differential run for the first time, which surfaces drift; fixing that drift can
reintroduce the type error. Observed in practice as `1 -> 0 -> 1` type errors
across three attempts, with the final (worse) attempt being the one emitted.

So every fully-evaluated attempt is scored and the winner is restored before the
module is finalized. Scoring is lexicographic on
`(type errors, distinct failure modes)`: code that does not compile is worse than
code that compiles and misbehaves, because the latter can at least be reasoned
about from real output. Ties keep the earlier attempt, which is the one the later
ones failed to improve on.
"""
from __future__ import annotations

from typing import Optional

from codeshift.equivalence.diff import distinct_divergences
from codeshift.state import FileUnit


def score(unit: FileUnit) -> tuple[int, int]:
    """Lower is better. See the module docstring for the ordering rationale."""
    type_errors = len(unit.get("type_errors") or [])
    modes = len(distinct_divergences(list(unit.get("divergences") or [])))
    return (type_errors, modes)


def record_candidate(unit: FileUnit) -> Optional[tuple[int, int]]:
    """Snapshot this attempt if it beats the best so far; return its score.

    Call only where both metrics are real — i.e. after the differential run.
    An attempt that bounced off the type gate has no divergence data, and
    scoring it would compare a measured zero against an unmeasured one.
    """
    code = unit.get("translated_code")
    if not code:
        return None

    current = score(unit)
    best = unit.get("best")
    if best is not None and tuple(best["score"]) <= current:
        return current

    unit["best"] = {
        "score": list(current),
        "attempt": unit.get("attempts", 0),
        "code": code,
        "target_path": unit.get("target_path"),
        "type_errors": list(unit.get("type_errors") or []),
        "divergences": list(unit.get("divergences") or []),
    }
    return current


def adopt_best(unit: FileUnit) -> Optional[dict]:
    """Restore the best-scoring attempt onto the unit.

    Returns the adopted snapshot when it differs from what is currently on the
    unit (so the caller can re-emit and log), else None.
    """
    best = unit.get("best")
    if not best or best["code"] == unit.get("translated_code"):
        return None

    unit["translated_code"] = best["code"]
    unit["type_errors"] = list(best["type_errors"])
    unit["divergences"] = list(best["divergences"])
    if best.get("target_path"):
        unit["target_path"] = best["target_path"]
    return best
