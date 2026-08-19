"""A transaction: several lines that must balance before they can be posted."""
from __future__ import annotations

from core.dates import is_valid_date
from core.money import abs_cents, format_cents
from core.text import truncate
from model.entries import describe, entry_signed
from validation.entry_rules import validate_side


class Transaction:
    """A set of debit and credit lines under one reference.

    Lines are held as running totals rather than a list, because everything the
    engine asks of a transaction is a total: nothing downstream needs the lines
    back in the order they arrived.
    """

    def __init__(self, ref: str, date: str, memo: str) -> None:
        if not is_valid_date(date):
            raise ValueError("bad transaction date: " + date)
        self.ref = ref.strip().upper()
        self.date = date
        self.memo = memo.strip()
        self.debits = 0
        self.credits = 0
        self.lines = 0

    def add(self, account: str, side: str, cents: int) -> int:
        """Record one line and return the running line count."""
        if validate_side(side):
            raise ValueError("bad side: " + side)
        amount = abs_cents(cents)
        if entry_signed(side, amount) > 0:
            self.debits = self.debits + amount
        else:
            self.credits = self.credits + amount
        self.lines = self.lines + 1
        return self.lines

    def delta(self) -> int:
        """Debits less credits: zero when the transaction balances."""
        return self.debits - self.credits

    def is_balanced(self) -> bool:
        return self.lines > 0 and self.delta() == 0

    def total(self, side: str) -> int:
        if side.strip().lower() == "debit":
            return self.debits
        if side.strip().lower() == "credit":
            return self.credits
        raise ValueError("bad side: " + side)

    def summary(self, width: int) -> str:
        head = self.ref + " " + self.date + " " + format_cents(self.debits)
        return truncate(head + " " + self.memo, width)

    @staticmethod
    def line_label(date: str, account: str, side: str, cents: int) -> str:
        return describe(date, account, side, cents)
