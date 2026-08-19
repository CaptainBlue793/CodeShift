"""Accounting periods: `2024-Q1`, and when one is open."""
from __future__ import annotations

from core.dates import add_days, days_between, is_valid_date, month_end, quarter_of


def period_of(date: str) -> str:
    if not is_valid_date(date):
        raise ValueError("bad date: " + date)
    return date[0:4] + "-Q" + str(quarter_of(date))


def is_valid_period(period: str) -> bool:
    parts = period.split("-Q")
    if len(parts) != 2:
        return False
    if len(parts[0]) != 4 or not parts[0].isdigit():
        return False
    if len(parts[1]) != 1 or not parts[1].isdigit():
        return False
    quarter = int(parts[1])
    return quarter >= 1 and quarter <= 4


def period_start(period: str) -> str:
    if not is_valid_period(period):
        raise ValueError("bad period: " + period)
    month = (int(period[6]) - 1) * 3 + 1
    return period[0:4] + "-" + str(month).rjust(2, "0") + "-01"


def period_end(period: str) -> str:
    if not is_valid_period(period):
        raise ValueError("bad period: " + period)
    month = int(period[6]) * 3
    return month_end(period[0:4] + "-" + str(month).rjust(2, "0") + "-01")


def period_days(period: str) -> int:
    return days_between(period_start(period), period_end(period)) + 1


def contains(period: str, date: str) -> bool:
    return period_of(date) == period


def is_closed(period: str, closed_through: str) -> bool:
    """True when `period` ends on or before the last closed period."""
    if not is_valid_period(period) or not is_valid_period(closed_through):
        raise ValueError("bad period")
    return period <= closed_through


def next_open_date(period: str) -> str:
    """The first date after a closed period, where late postings land."""
    return add_days(period_end(period), 1)
