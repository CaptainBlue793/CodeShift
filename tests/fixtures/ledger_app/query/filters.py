"""Predicates for selecting journal lines."""
from __future__ import annotations

from core.codes import class_of, is_valid_code
from core.dates import is_valid_date, to_ordinal
from core.text import normalize_space, slugify


def matches_text(haystack: str, needle: str) -> bool:
    """Case- and spacing-insensitive containment."""
    if not needle.strip():
        return True
    return slugify(needle) in slugify(haystack)


def in_range(date: str, start: str, end: str) -> bool:
    """Whether `date` falls in the inclusive window `start`..`end`."""
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    return to_ordinal(start) <= to_ordinal(date) <= to_ordinal(end)


def side_matches(side: str, wanted: str) -> bool:
    """An empty `wanted` matches either side."""
    if not wanted.strip():
        return True
    return side.strip().lower() == wanted.strip().lower()


def amount_in_range(cents: int, low: int, high: int) -> bool:
    return low <= cents <= high


def code_in_class(code: str, kind: str) -> bool:
    if not is_valid_code(code):
        return False
    return class_of(code) == normalize_space(kind).lower()


def matches_all(haystack: str, needle: str, side: str, wanted: str) -> bool:
    return matches_text(haystack, needle) and side_matches(side, wanted)
