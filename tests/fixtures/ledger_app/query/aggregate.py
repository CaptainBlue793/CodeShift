"""Totals over selected lines, all in integer cents."""
from __future__ import annotations

from core.money import abs_cents, format_cents
from query.filters import amount_in_range


def net_movement(debits: int, credits: int) -> int:
    return debits - credits


def running_total(previous: int, delta: int) -> int:
    return previous + delta


def average_cents(total: int, count: int) -> int:
    """The mean, rounded half away from zero. Zero lines average to zero."""
    if count == 0:
        return 0
    if count < 0:
        raise ValueError("count must not be negative")
    magnitude = abs_cents(total)
    rounded = (magnitude * 2 + count) // (count * 2)
    return -rounded if total < 0 else rounded


def share_bps(part: int, whole: int) -> int:
    """`part` as basis points of `whole`; zero when there is no whole."""
    if whole == 0:
        return 0
    return part * 10000 // whole


def total_in_band(cents: int, low: int, high: int) -> int:
    """The amount, counted only if it falls inside the band."""
    if amount_in_range(cents, low, high):
        return cents
    return 0


def summary_line(label: str, total: int, count: int) -> str:
    return (
        label
        + ": "
        + format_cents(total)
        + " over "
        + str(count)
        + " line(s), avg "
        + format_cents(average_cents(total, count))
    )
