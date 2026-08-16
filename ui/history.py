"""Per-attempt history folding for the dashboard.

Kept out of `app.py` because that module executes a Streamlit page on import;
this is the part with actual logic, so it lives where it can be tested.

The thing being reconstructed is the retry loop's trace — the sequence of error
counts across a module's attempts (`1 -> 0 -> 1`). It is the project's most
diagnostic signal: counts that never move mean the loop is not feeding anything
back, and counts that go down then up mean it is oscillating.
"""
from __future__ import annotations


def record_history(history: dict, snapshot: dict) -> None:
    """Fold a state snapshot into per-module, per-attempt counts (in place).

    Keyed by attempt number rather than appended, because one attempt produces
    several snapshots — the translator bumps the count, then the type oracle
    fills in errors, then the differential run fills in divergences — and each
    should refine the same row instead of adding a new one.
    """
    for module, unit in (snapshot.get("files") or {}).items():
        attempt = unit.get("attempts", 0)
        if not attempt:
            continue
        row = history.setdefault(module, {}).setdefault(attempt, {})
        row["type_errors"] = len(unit.get("type_errors") or [])
        row["divergences"] = len(unit.get("divergences") or [])
        row["rejected"] = unit.get("rejected")


def counts(per_module: dict, key: str) -> list[int]:
    """Counts for `key` ordered by attempt number."""
    return [per_module[attempt].get(key, 0) for attempt in sorted(per_module)]


def trace(per_module: dict, key: str) -> str:
    """Render the attempt sequence, e.g. `1 → 0 → 1`."""
    values = counts(per_module, key)
    return " → ".join(str(v) for v in values) if values else "—"


def trend(per_module: dict, key: str) -> str:
    """Label the last transition: improving, regressed, or stuck."""
    values = counts(per_module, key)
    if len(values) < 2:
        return ""
    if values[-1] == values[-2]:
        return "  ·  stuck"
    return "  ·  improving" if values[-1] < values[-2] else "  ·  regressed"
