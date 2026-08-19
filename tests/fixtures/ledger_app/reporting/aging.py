"""Aged receivables: how overdue each invoice is, bucketed."""
from __future__ import annotations

from core.dates import days_between
from posting.periods import period_of
from reporting.format import row

CURRENT = "current"
BUCKET_30 = "1-30"
BUCKET_60 = "31-60"
BUCKET_90 = "61-90"
BUCKET_OVER = "90+"


def age_days(invoice_date: str, as_of: str) -> int:
    """Days elapsed since the invoice date; negative when post-dated."""
    return days_between(invoice_date, as_of)


def bucket_for(days: int) -> str:
    if days <= 0:
        return CURRENT
    if days <= 30:
        return BUCKET_30
    if days <= 60:
        return BUCKET_60
    if days <= 90:
        return BUCKET_90
    return BUCKET_OVER


def bucket_of(invoice_date: str, as_of: str) -> str:
    return bucket_for(age_days(invoice_date, as_of))


def is_overdue(invoice_date: str, as_of: str, terms_days: int) -> bool:
    return age_days(invoice_date, as_of) > terms_days


def due_period(invoice_date: str, as_of: str) -> str:
    """The period the invoice is chased in."""
    if is_overdue(invoice_date, as_of, 0):
        return period_of(as_of)
    return period_of(invoice_date)


def aging_line(ref: str, days: int, cents: int, width: int) -> str:
    return row(ref + "  " + bucket_for(days), cents, width)
