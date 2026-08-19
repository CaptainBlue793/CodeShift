"""A journal line: one date, one account, one side, one amount."""
from __future__ import annotations

from dataclasses import dataclass

from core.dates import is_valid_date, quarter_of
from core.money import format_cents
from core.text import truncate
from validation.entry_rules import signed_amount, validate_line


@dataclass
class Entry:
    """One posting line. Amounts are unsigned; `side` carries the direction."""

    date: str
    account: str
    side: str
    cents: int
    memo: str


def describe(date: str, account: str, side: str, cents: int) -> str:
    """`2024-03-01 1000-CASH debit 1234.56`, for logs and reports."""
    return date + " " + account + " " + side.lower() + " " + format_cents(cents)


def entry_problem(date: str, side: str, amount: str) -> str:
    """Empty when the line is postable, otherwise the first diagnostic."""
    return validate_line(date, side, amount)


def entry_signed(side: str, cents: int) -> int:
    return signed_amount(side, cents)


def entry_period(date: str) -> str:
    """`2024-Q1`, the period a line falls in."""
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    return date[0:4] + "-Q" + str(quarter_of(date))


def short_memo(memo: str, width: int) -> str:
    return truncate(memo.strip(), width)
