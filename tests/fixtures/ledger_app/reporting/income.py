"""The income statement: revenue, cost, expenses and what is left."""
from __future__ import annotations

from core.money import abs_cents
from reporting.format import percent_label, row, total_row
from tax.vat import net_from_gross


def gross_profit(revenue: int, cost: int) -> int:
    return revenue - cost


def net_income(revenue: int, cost: int, expenses: int) -> int:
    return gross_profit(revenue, cost) - expenses


def margin_bps(revenue: int, cost: int) -> int:
    """Gross margin in basis points; zero revenue has no margin, not an error."""
    if revenue == 0:
        return 0
    return gross_profit(revenue, cost) * 10000 // abs_cents(revenue)


def margin_label(revenue: int, cost: int) -> str:
    return percent_label(margin_bps(revenue, cost))


def revenue_ex_vat(gross_revenue: int, kind: str) -> int:
    """Revenue reported net of the VAT collected on it."""
    return net_from_gross(gross_revenue, kind)


def income_line(label: str, cents: int, width: int) -> str:
    return row(label, cents, width)


def bottom_line(revenue: int, cost: int, expenses: int, width: int) -> str:
    return total_row("net income", net_income(revenue, cost, expenses), width)


def is_profitable(revenue: int, cost: int, expenses: int) -> bool:
    return net_income(revenue, cost, expenses) > 0
