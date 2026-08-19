"""Validators and sign conventions for a single journal line."""
from __future__ import annotations

from core.codes import CREDIT, DEBIT, normal_side
from core.errors import format_error
from core.money import abs_cents
from validation.rules import first_problem, require_amount, require_date


def validate_side(side: str) -> str:
    cleaned = side.strip().lower()
    if cleaned != DEBIT and cleaned != CREDIT:
        return format_error("E301", "side must be debit or credit, got " + side)
    return ""


def validate_line(date: str, side: str, amount: str) -> str:
    return first_problem(
        first_problem(require_date(date, "entry date"), validate_side(side)),
        require_amount(amount, "entry amount"),
    )


def signed_amount(side: str, cents: int) -> int:
    """Debits are positive and credits negative in the internal convention."""
    if validate_side(side):
        raise ValueError("bad side: " + side)
    magnitude = abs_cents(cents)
    if side.strip().lower() == DEBIT:
        return magnitude
    return -magnitude


def opposite(side: str) -> str:
    if side.strip().lower() == DEBIT:
        return CREDIT
    if side.strip().lower() == CREDIT:
        return DEBIT
    return ""


def increases(code: str, side: str) -> bool:
    """Whether posting `side` to `code` makes its balance larger."""
    return normal_side(code) == side.strip().lower()
