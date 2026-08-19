"""Calendar arithmetic on ISO `YYYY-MM-DD` strings. No internal dependencies.

Dates are plain strings and the arithmetic is done by hand rather than through
a date library, so the engine has no timezone surface at all: the same posting
always lands in the same period, wherever it is run.
"""
from __future__ import annotations

_MONTH_LENGTHS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
_DAYS_BEFORE_MONTH = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]


def is_leap(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year: int, month: int) -> int:
    if month < 1 or month > 12:
        raise ValueError("month out of range")
    if month == 2 and is_leap(year):
        return 29
    return _MONTH_LENGTHS[month - 1]


def is_valid_date(date: str) -> bool:
    parts = date.split("-")
    if len(parts) != 3:
        return False
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        return False
    for part in parts:
        if not part.isdigit():
            return False
    year = int(parts[0])
    month = int(parts[1])
    day = int(parts[2])
    if month < 1 or month > 12 or day < 1 or year < 1:
        return False
    return day <= days_in_month(year, month)


def to_ordinal(date: str) -> int:
    """Days since 0001-01-01, so two dates can simply be subtracted."""
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    year = int(date[0:4])
    month = int(date[5:7])
    day = int(date[8:10])
    prior = year - 1
    days = prior * 365 + prior // 4 - prior // 100 + prior // 400
    days = days + _DAYS_BEFORE_MONTH[month - 1]
    if month > 2 and is_leap(year):
        days = days + 1
    return days + day


def from_ordinal(ordinal: int) -> str:
    """The inverse of `to_ordinal`, back to `YYYY-MM-DD`."""
    if ordinal < 1:
        raise ValueError("ordinal out of range")
    year = 1
    remaining = ordinal
    while True:
        length = 366 if is_leap(year) else 365
        if remaining <= length:
            break
        remaining = remaining - length
        year = year + 1
    month = 1
    while remaining > days_in_month(year, month):
        remaining = remaining - days_in_month(year, month)
        month = month + 1
    return (
        str(year).rjust(4, "0")
        + "-"
        + str(month).rjust(2, "0")
        + "-"
        + str(remaining).rjust(2, "0")
    )


def days_between(start: str, end: str) -> int:
    """Signed day count from `start` to `end`."""
    return to_ordinal(end) - to_ordinal(start)


def add_days(date: str, count: int) -> str:
    return from_ordinal(to_ordinal(date) + count)


def month_end(date: str) -> str:
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    last = days_in_month(int(date[0:4]), int(date[5:7]))
    return date[0:8] + str(last).rjust(2, "0")


def quarter_of(date: str) -> int:
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    return (int(date[5:7]) - 1) // 3 + 1
