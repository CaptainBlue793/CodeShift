"""The facade the rest of the world calls: open a book, post to it, report."""
from __future__ import annotations

from core.money import format_cents
from posting.ledger import Ledger
from posting.periods import period_of
from query.aggregate import share_bps
from reporting.format import row
from reporting.trial_balance import footer


class Engine:
    """One set of books, with the reporting entry points attached.

    Everything here delegates: the engine's job is to be the only thing a
    caller has to know about, not to hold rules of its own.
    """

    def __init__(self, name: str) -> None:
        self.name = name.strip()
        self.book = Ledger(name)
        self.postings = 0

    def open_account(self, code: str, name: str, is_group: bool) -> int:
        return self.book.open_account(code, name, is_group)

    def post(self, code: str, side: str, cents: int, date: str) -> int:
        """Post one line and return the account's new balance."""
        balance = self.book.post(code, side, cents, date)
        self.postings = self.postings + 1
        return balance

    def balance(self, code: str) -> int:
        return self.book.balance(code)

    def balance_label(self, code: str) -> str:
        return code + " " + format_cents(self.balance(code))

    def report_line(self, code: str, width: int) -> str:
        return row(code, self.balance(code), width)

    def share_of_total(self, code: str) -> int:
        """This account's balance as basis points of all debits posted."""
        return share_bps(self.balance(code), self.book.debits)

    def close(self, date: str) -> str:
        """Close the period containing `date`."""
        return self.book.close_period(period_of(date))

    def health(self, width: int) -> str:
        return footer(self.book.debits, self.book.credits, width)

    def is_balanced(self) -> bool:
        return self.book.is_balanced()
