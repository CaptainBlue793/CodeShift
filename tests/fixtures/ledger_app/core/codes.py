"""Account codes: `1000-CASH`, and what the leading digit means.

The first digit fixes an account's class, and its class fixes which side of a
posting increases it. That rule lives here rather than on the account object,
because the reports need it for codes they have never seen.
"""
from __future__ import annotations

from core.text import normalize_space, slugify

ASSET = "asset"
LIABILITY = "liability"
EQUITY = "equity"
INCOME = "income"
EXPENSE = "expense"
UNKNOWN = "unknown"

DEBIT = "debit"
CREDIT = "credit"


def code_number(code: str) -> int:
    """The numeric head of a code (`1000-CASH` -> 1000), or -1 if absent."""
    head = code.split("-")[0].strip()
    if not head.isdigit():
        return -1
    return int(head)


def is_valid_code(code: str) -> bool:
    """A valid code is four digits, optionally followed by `-MNEMONIC`."""
    parts = normalize_space(code).split("-")
    if not parts[0].isdigit() or len(parts[0]) != 4:
        return False
    if len(parts) == 1:
        return True
    if len(parts) != 2:
        return False
    return len(parts[1]) > 0 and parts[1].isalnum()


def class_of(code: str) -> str:
    """The account class implied by the leading digit."""
    number = code_number(code)
    if number < 1000 or number > 9999:
        return UNKNOWN
    lead = number // 1000
    if lead == 1:
        return ASSET
    if lead == 2:
        return LIABILITY
    if lead == 3:
        return EQUITY
    if lead == 4:
        return INCOME
    if lead >= 5 and lead <= 8:
        return EXPENSE
    return UNKNOWN


def normal_side(code: str) -> str:
    """The side that increases this account."""
    kind = class_of(code)
    if kind == ASSET or kind == EXPENSE:
        return DEBIT
    if kind == UNKNOWN:
        return UNKNOWN
    return CREDIT


def is_balance_sheet(code: str) -> bool:
    kind = class_of(code)
    return kind == ASSET or kind == LIABILITY or kind == EQUITY


def format_code(number: int, mnemonic: str) -> str:
    """Build a canonical code from its parts."""
    if number < 0 or number > 9999:
        raise ValueError("account number out of range")
    head = str(number).rjust(4, "0")
    tail = slugify(mnemonic).replace("-", "").upper()
    if not tail:
        return head
    return head + "-" + tail
