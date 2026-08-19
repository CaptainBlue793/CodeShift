"""The journal: transactions in the order they were recorded."""
from __future__ import annotations

from core.dates import is_valid_date, quarter_of
from core.ids import make_ref
from core.text import title_case
from model.transactions import Transaction


class Journal:
    """An append-only book of transactions.

    Balances are not kept here. A journal records what happened; deciding what
    the totals now are is the ledger's job, and keeping both would let the two
    disagree.
    """

    def __init__(self, name: str) -> None:
        self.name = title_case(name)
        self.sequence = 0
        self.entries = 0
        self.periods: dict[str, int] = {}

    def next_ref(self, prefix: str) -> str:
        """Allocate the next reference under `prefix`."""
        self.sequence = self.sequence + 1
        return make_ref(prefix, self.sequence)

    def record(self, ref: str, date: str, memo: str) -> int:
        """Record a transaction and return the running entry count."""
        transaction = Transaction(ref, date, memo)
        period = self.period_of(transaction.date)
        self.periods[period] = self.periods.get(period, 0) + 1
        self.entries = self.entries + 1
        return self.entries

    def count_in(self, period: str) -> int:
        return self.periods.get(period, 0)

    def count(self) -> int:
        return self.entries

    @staticmethod
    def period_of(date: str) -> str:
        if not is_valid_date(date):
            raise ValueError("bad date: " + date)
        return date[0:4] + "-Q" + str(quarter_of(date))
