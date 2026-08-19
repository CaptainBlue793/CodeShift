"""Reconciling a ledger balance against an external statement.

Half of a deliberate import cycle with `posting.ledger`: the ledger asks this
module for a verdict from inside a method, and this module reads balances back
off the ledger.
"""
from __future__ import annotations

from core.dates import days_between
from core.money import abs_cents, format_cents
from posting.balancing import within_tolerance
from posting.ledger import Ledger

MATCHED = "matched"
SHORT = "short"
OVER = "over"


def difference(cleared: int, statement: int) -> int:
    """Statement less cleared: positive when the bank shows more than we did."""
    return statement - cleared


def status(cleared: int, statement: int) -> str:
    """One of `matched`, `short` or `over`."""
    gap = difference(cleared, statement)
    if gap == 0:
        return MATCHED
    if gap > 0:
        return SHORT
    return OVER


def is_reconciled(cleared: int, statement: int, tolerance: int) -> bool:
    return within_tolerance(statement, cleared, tolerance)


def outstanding(cleared: int, statement: int) -> int:
    """The magnitude still unaccounted for."""
    return abs_cents(difference(cleared, statement))


def summary(cleared: int, statement: int) -> str:
    verdict = status(cleared, statement)
    if verdict == MATCHED:
        return "reconciled"
    return verdict + " by " + format_cents(outstanding(cleared, statement))


def staleness(last_reconciled: str, as_of: str) -> int:
    """Days since the account was last reconciled."""
    return days_between(last_reconciled, as_of)


def needs_attention(last_reconciled: str, as_of: str, limit_days: int) -> bool:
    return staleness(last_reconciled, as_of) > limit_days


def clear_against(book: Ledger, code: str, statement: int) -> int:
    """The gap between an account's ledger balance and a statement."""
    return difference(book.balance(code), statement)


def clearing_note(code: str, cleared: int, statement: int) -> str:
    """The line a reconciliation report shows for one account."""
    return code + ": " + summary(cleared, statement)
