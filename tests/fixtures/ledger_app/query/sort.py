"""Ordering keys for report rows."""
from __future__ import annotations

from core.dates import is_valid_date
from core.text import pad_left
from query.filters import code_in_class


def date_ref_key(date: str, ref: str) -> str:
    """A sortable key putting lines in date order, ties broken by reference."""
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    return date + "|" + ref.strip().upper()


def compare(first: str, second: str) -> int:
    """-1, 0 or 1, so the caller does not depend on either language's sort."""
    if first < second:
        return -1
    if first > second:
        return 1
    return 0


def amount_key(cents: int, width: int) -> str:
    """A fixed-width, sign-aware key so amounts sort as numbers, not text."""
    sign = "0" if cents < 0 else "1"
    magnitude = -cents if cents < 0 else cents
    return sign + pad_left(str(magnitude), width).replace(" ", "0")


def rank_of(cents: int, threshold: int) -> int:
    """2 for large, 1 for non-zero, 0 for empty: the report's row weight."""
    magnitude = -cents if cents < 0 else cents
    if magnitude >= threshold:
        return 2
    if magnitude > 0:
        return 1
    return 0


def class_rank(code: str, kind: str) -> int:
    """Rows in the requested class sort ahead of everything else."""
    if code_in_class(code, kind):
        return 0
    return 1
