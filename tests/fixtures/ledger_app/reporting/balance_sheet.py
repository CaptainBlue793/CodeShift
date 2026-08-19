"""The balance sheet, and the equation it has to satisfy."""
from __future__ import annotations

from core.codes import ASSET, EQUITY, LIABILITY, class_of, is_balance_sheet
from core.money import abs_cents, format_cents
from reporting.format import row, total_row


def section_for(code: str) -> str:
    """Which section of the sheet a code belongs to, or empty when none."""
    if not is_balance_sheet(code):
        return ""
    return class_of(code)


def section_rank(code: str) -> int:
    """Assets first, then liabilities, then equity; everything else last."""
    section = section_for(code)
    if section == ASSET:
        return 1
    if section == LIABILITY:
        return 2
    if section == EQUITY:
        return 3
    return 4


def sheet_line(code: str, name: str, cents: int, width: int) -> str:
    return row(code + "  " + name, cents, width)


def equation_delta(assets: int, liabilities: int, equity: int) -> int:
    """Assets less liabilities and equity: zero when the sheet balances."""
    return assets - liabilities - equity


def is_balanced(assets: int, liabilities: int, equity: int) -> bool:
    return equation_delta(assets, liabilities, equity) == 0


def equation_note(assets: int, liabilities: int, equity: int) -> str:
    gap = equation_delta(assets, liabilities, equity)
    if gap == 0:
        return "assets = liabilities + equity"
    return "out of balance by " + format_cents(abs_cents(gap))


def net_assets(assets: int, liabilities: int, width: int) -> str:
    return total_row("net assets", assets - liabilities, width)
