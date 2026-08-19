"""Field-level validators.

Every validator returns a diagnostic string, empty when the value is fine.
Returning a message rather than raising lets a caller collect every problem
with a document in one pass instead of stopping at the first.
"""
from __future__ import annotations

from core.dates import is_valid_date
from core.errors import format_error
from core.money import parse_amount
from core.text import normalize_space

MAX_MEMO = 120


def require_nonempty(value: str, field: str) -> str:
    if not normalize_space(value):
        return format_error("E101", field + " must not be empty")
    return ""


def max_length(value: str, field: str, limit: int) -> str:
    if len(value) > limit:
        return format_error(
            "E102", field + " is longer than " + str(limit) + " characters"
        )
    return ""


def require_date(value: str, field: str) -> str:
    if not is_valid_date(value):
        return format_error("E103", field + " is not a valid ISO date")
    return ""


def require_amount(value: str, field: str) -> str:
    try:
        parse_amount(value)
    except ValueError:
        return format_error("E104", field + " is not a valid amount")
    return ""


def validate_memo(memo: str) -> str:
    problem = max_length(memo, "memo", MAX_MEMO)
    if problem:
        return problem
    return ""


def first_problem(first: str, second: str) -> str:
    """The first non-empty diagnostic of the two."""
    if first:
        return first
    return second
