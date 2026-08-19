"""Whether a set of postings balances, and what it would take to fix it."""
from __future__ import annotations

from core.codes import CREDIT, DEBIT
from core.money import abs_cents, format_cents


def delta(debits: int, credits: int) -> int:
    """Debits less credits. Zero is the only acceptable answer at close."""
    return debits - credits


def is_balanced(debits: int, credits: int) -> bool:
    return delta(debits, credits) == 0


def suspense_amount(debits: int, credits: int) -> int:
    """The magnitude of the balancing line the books would need."""
    return abs_cents(delta(debits, credits))


def suspense_side(debits: int, credits: int) -> str:
    """Which side that balancing line goes on; empty when already balanced."""
    difference = delta(debits, credits)
    if difference == 0:
        return ""
    if difference > 0:
        return CREDIT
    return DEBIT


def balance_report(debits: int, credits: int) -> str:
    """A one-line verdict, for the trial balance footer."""
    if is_balanced(debits, credits):
        return "balanced"
    return (
        "out by "
        + format_cents(suspense_amount(debits, credits))
        + " ("
        + suspense_side(debits, credits)
        + ")"
    )


def within_tolerance(debits: int, credits: int, tolerance: int) -> bool:
    """Balanced to within `tolerance` cents, for reconciliations."""
    if tolerance < 0:
        raise ValueError("tolerance must not be negative")
    return suspense_amount(debits, credits) <= tolerance
