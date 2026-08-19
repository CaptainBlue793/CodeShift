"""The `Account` object: a code, a name, and the rules that follow from them."""
from __future__ import annotations

from core.codes import UNKNOWN, class_of, normal_side
from core.text import slugify, title_case, truncate


class Account:
    """One line of the chart of accounts.

    The class and normal side are derived from the code at construction time,
    so an account cannot drift out of agreement with its own number.
    """

    def __init__(self, code: str, name: str, is_group: bool) -> None:
        self.code = code.strip().upper()
        self.name = title_case(name)
        self.is_group = is_group
        self.kind = class_of(self.code)
        self.side = normal_side(self.code)
        self.slug = slugify(name)
        self.balance = 0

    def label(self, width: int) -> str:
        """`1000-CASH  Cash At Bank`, clipped to `width`."""
        return truncate(self.code + "  " + self.name, width)

    def accepts(self, side: str) -> bool:
        """Postings are refused on group headings and unclassified codes."""
        if self.is_group or self.kind == UNKNOWN:
            return False
        cleaned = side.strip().lower()
        return cleaned == "debit" or cleaned == "credit"

    def apply(self, side: str, cents: int) -> int:
        """Move the balance and return the new one."""
        if not self.accepts(side):
            raise ValueError("cannot post " + side + " to " + self.code)
        if side.strip().lower() == self.side:
            self.balance = self.balance + cents
        else:
            self.balance = self.balance - cents
        return self.balance

    def is_empty(self) -> bool:
        return self.balance == 0

    @staticmethod
    def group_of(code: str) -> str:
        """The parent heading a code rolls up into (`1210` -> `1200`)."""
        head = code.split("-")[0]
        if not head.isdigit() or len(head) != 4:
            return ""
        return head[0:2] + "00"
