"""The chart of accounts: every account the ledger is allowed to post to."""
from __future__ import annotations

from core.codes import UNKNOWN, class_of, is_valid_code
from core.text import title_case
from model.accounts import Account
from validation.account_rules import validate_account


class ChartOfAccounts:
    """A flat collection of accounts, keyed by code.

    Flat rather than a tree: the roll-up parent of a code is computable from
    the code itself (`Account.group_of`), so a tree would be a second source of
    truth for the same fact.
    """

    def __init__(self, name: str) -> None:
        self.name = title_case(name)
        self.accounts: dict[str, str] = {}
        self.groups: dict[str, bool] = {}

    def add(self, code: str, name: str, is_group: bool) -> int:
        """Add one account and return the new size. Rejects bad codes."""
        problem = validate_account(code, name)
        if problem:
            raise ValueError(problem)
        key = code.strip().upper()
        self.accounts[key] = title_case(name)
        self.groups[key] = is_group
        return len(self.accounts)

    def has(self, code: str) -> bool:
        return code.strip().upper() in self.accounts

    def name_of(self, code: str) -> str:
        """The account's name, or an empty string when it is not in the chart."""
        return self.accounts.get(code.strip().upper(), "")

    def kind_of(self, code: str) -> str:
        if not self.has(code):
            return UNKNOWN
        return class_of(code)

    def is_group(self, code: str) -> bool:
        return self.groups.get(code.strip().upper(), False)

    def size(self) -> int:
        return len(self.accounts)

    def build(self, code: str, name: str) -> Account:
        """An `Account` object for a code already in the chart."""
        if not self.has(code):
            raise ValueError("unknown account: " + code)
        return Account(code, name, self.is_group(code))

    @staticmethod
    def is_postable_code(code: str) -> bool:
        return is_valid_code(code) and class_of(code) != UNKNOWN
