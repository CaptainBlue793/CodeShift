"""The ledger: current balances, maintained as transactions are posted."""
from __future__ import annotations

from core.codes import DEBIT, normal_side
from core.money import abs_cents, format_cents
from core.text import pad_right
from model.chart import ChartOfAccounts
from model.journal import Journal
from posting.balancing import delta, is_balanced
from posting.periods import is_closed, period_of
from validation.account_rules import posting_problem


class Ledger:
    """Balances by account code, plus the totals a trial balance needs.

    Balances are stored in each account's own normal direction, so an asset
    with money in it is positive and so is a liability that is owed. The signed
    view needed for the accounting equation is `signed_balance`.
    """

    def __init__(self, name: str) -> None:
        self.name = name.strip()
        self.chart = ChartOfAccounts(name)
        self.journal = Journal(name)
        self.balances: dict[str, int] = {}
        self.debits = 0
        self.credits = 0
        self.closed_through = ""

    def open_account(self, code: str, name: str, is_group: bool) -> int:
        return self.chart.add(code, name, is_group)

    def post(self, code: str, side: str, cents: int, date: str) -> int:
        """Post one line and return the account's new balance."""
        key = code.strip().upper()
        problem = posting_problem(key, self.chart.is_group(key))
        if problem:
            raise ValueError(problem)
        if self.closed_through and is_closed(period_of(date), self.closed_through):
            raise ValueError("period " + period_of(date) + " is closed")
        amount = abs_cents(cents)
        if side.strip().lower() == DEBIT:
            self.debits = self.debits + amount
        else:
            self.credits = self.credits + amount
        movement = amount if side.strip().lower() == normal_side(key) else -amount
        self.balances[key] = self.balances.get(key, 0) + movement
        return self.balances[key]

    def balance(self, code: str) -> int:
        return self.balances.get(code.strip().upper(), 0)

    def signed_balance(self, code: str) -> int:
        """The balance in debit-positive terms, whatever the account's side."""
        key = code.strip().upper()
        if normal_side(key) == DEBIT:
            return self.balance(key)
        return -self.balance(key)

    def trial_delta(self) -> int:
        return delta(self.debits, self.credits)

    def is_balanced(self) -> bool:
        return is_balanced(self.debits, self.credits)

    def close_period(self, period: str) -> str:
        """Close `period` and return the new high-water mark."""
        if period > self.closed_through:
            self.closed_through = period
        return self.closed_through

    def line(self, code: str, width: int) -> str:
        return pad_right(code, width) + format_cents(self.balance(code))

    def reconciliation_hint(self, cleared: int, statement: int) -> str:
        """What the reconciliation of this ledger against a statement says.

        Imported inside the function: `posting.reconcile` reads balances off a
        ledger, so importing it at module level would be a circular import.
        """
        from posting.reconcile import status

        return status(cleared, statement)
