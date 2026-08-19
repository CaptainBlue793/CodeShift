"""Fixed-width report furniture: rules, headings, money columns."""
from __future__ import annotations

from core.money import format_cents
from core.text import pad_left, pad_right, truncate

MONEY_WIDTH = 14


def rule(width: int, char: str) -> str:
    """A horizontal rule `width` characters wide."""
    if width <= 0 or not char:
        return ""
    return char[0] * width


def heading(title: str, width: int) -> str:
    """A centred, underlined section heading."""
    text = truncate(title.strip(), width)
    left = (width - len(text)) // 2
    if left < 0:
        left = 0
    return pad_right(pad_left(text, left + len(text)), width)


def money_column(cents: int) -> str:
    """An amount right-aligned in the standard money column."""
    return pad_left(format_cents(cents), MONEY_WIDTH)


def row(label: str, cents: int, width: int) -> str:
    """One report line: label on the left, amount on the right."""
    room = width - MONEY_WIDTH
    if room < 1:
        room = 1
    return pad_right(truncate(label, room), room) + money_column(cents)


def total_row(label: str, cents: int, width: int) -> str:
    return row(label.upper(), cents, width)


def percent_label(basis_points: int) -> str:
    """Basis points as a percentage, e.g. 1250 -> `12.50%`."""
    sign = "-" if basis_points < 0 else ""
    magnitude = -basis_points if basis_points < 0 else basis_points
    return sign + str(magnitude // 100) + "." + str(magnitude % 100).rjust(2, "0") + "%"
