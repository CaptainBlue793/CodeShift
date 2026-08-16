"""How much behavioral evidence a module actually has.

`divergences == []` is not evidence of equivalence. It is equally what a module
looks like when nothing in it could be executed — a module of abstract classes
yields no signatures, so the harness loops zero times and reports zero failures.
Both the report and the dashboard used to read that empty list as success, which
meant a module nobody had tested shipped with a green check.

The verdict separates "checked and matched" from "never checked". It lives here,
alone, because the report and the dashboard have to agree on it: two copies of
this rule would eventually disagree, and the one that drifts optimistic is the
one that misleads.
"""
from __future__ import annotations

from typing import Any, Literal, Mapping

Verdict = Literal["verified", "partial", "unverified", "drift", "empty"]

#: A FileUnit, or the loose snapshot dict the dashboard holds. These read a
#: handful of keys and must tolerate their absence — a unit that never reached
#: the differential run has to come out "unverified", not crash and not pass.
Unit = Mapping[str, Any]

#: Verdict -> the word used in the report table and the dashboard.
LABEL: dict[str, str] = {
    "verified": "verified",
    "partial": "partial",
    "unverified": "not verified",
    "drift": "drift",
    "empty": "nothing to run",
}

#: `Untestable.reason` slug -> prose, for the report's grouped listing.
REASON_LABEL: dict[str, str] = {
    "class": "classes are not differential-tested (top-level functions only)",
    "async_function": "async functions are not differential-tested",
    "async_method": "async methods are not differential-tested",
    "private_method": "private and dunder methods are treated as implementation detail",
    "property": "properties take no arguments to generate, so they are not called",
    "abstract_method": "abstract methods have no body to compare",
    # Why a class can be untestable at all: every method needs a receiver, and a
    # receiver we cannot build the same way on both sides would fail on one and
    # succeed on the other. See `adapters.python.classes`.
    "abstract_class": "the class is abstract, so no instance can be built to call it on",
    "variadic_constructor": "the constructor takes *args/**kwargs, so no receiver could be built",
    "keyword_only_constructor": (
        "the constructor requires keyword-only arguments, so no receiver could be built"
    ),
    "inherited_constructor": (
        "the constructor is inherited from a base class this analysis cannot see, "
        "so no receiver could be built"
    ),
    # Same asymmetry as the constructor cases, one level down: the harness only
    # passes positional arguments, so a required keyword-only parameter raises
    # in Python and binds to `undefined` in the target.
    "keyword_only_method": (
        "the method requires keyword-only arguments, which the harness cannot supply"
    ),
    "keyword_only_function": (
        "the function requires keyword-only arguments, which the harness cannot supply"
    ),
    "runtime_unavailable": "the target runtime was unavailable",
    "sandbox_unavailable": "the sandbox was unavailable, so nothing was executed",
}


def verdict(unit: Unit) -> Verdict:
    """Classify a module by what the differential run actually established.

    Drift outranks everything: a module with a known mismatch is not described
    by how much of the rest of it was covered.
    """
    if unit.get("divergences"):
        return "drift"
    checked = unit.get("verified_functions") or []
    skipped = unit.get("unverified") or []
    if checked:
        return "partial" if skipped else "verified"
    return "unverified" if skipped else "empty"


def is_trustworthy(unit: Unit) -> bool:
    """True only when everything runnable was compared, matched, and compiles.

    The one predicate allowed to mean "this module is fine".
    """
    return verdict(unit) == "verified" and not unit.get("type_errors")


def unverified_names(unit: Unit) -> list[str]:
    """Just the names, for compact contexts like the report's Notes column."""
    return [entry.get("name", "?") for entry in (unit.get("unverified") or [])]


def unverified_by_reason(unit: Unit) -> dict[str, list[str]]:
    """Group a module's unverified entries by reason slug, order preserved."""
    grouped: dict[str, list[str]] = {}
    for entry in unit.get("unverified") or []:
        grouped.setdefault(entry.get("reason", "unknown"), []).append(entry.get("name", "?"))
    return grouped
