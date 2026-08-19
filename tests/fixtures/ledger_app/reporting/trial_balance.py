"""The trial balance: every account's balance, and whether the books agree."""
from __future__ import annotations

from core.codes import DEBIT, class_of, normal_side
from core.money import abs_cents
from posting.balancing import balance_report, delta
from reporting.format import row, rule, total_row


def column_for(code: str, cents: int) -> str:
    """Which column a balance belongs in once its sign is taken into account."""
    side = normal_side(code)
    if cents < 0:
        if side == DEBIT:
            return "credit"
        return "debit"
    return side


def debit_column(code: str, cents: int) -> int:
    """The amount to show in the debit column; zero when it belongs in credit."""
    if column_for(code, cents) == DEBIT:
        return abs_cents(cents)
    return 0


def credit_column(code: str, cents: int) -> int:
    if column_for(code, cents) == DEBIT:
        return 0
    return abs_cents(cents)


def account_line(code: str, name: str, cents: int, width: int) -> str:
    return row(code + "  " + name, cents, width)


def section_of(code: str) -> str:
    return class_of(code)


def footer(debits: int, credits: int, width: int) -> str:
    """The closing lines: a rule, the difference, and the verdict."""
    return (
        rule(width, "-")
        + "\n"
        + total_row("difference", delta(debits, credits), width)
        + "\n"
        + balance_report(debits, credits)
    )
