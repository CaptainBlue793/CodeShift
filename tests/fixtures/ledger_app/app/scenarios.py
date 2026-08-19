"""Canned scenarios: the smallest books that exercise the whole engine."""
from __future__ import annotations

from app.engine import Engine
from core.dates import add_days
from core.ids import make_ref
from reporting.aging import bucket_of
from tax.vat import gross_from_net


def opening_ref(period: str, sequence: int) -> str:
    return make_ref("OPEN-" + period, sequence)


def sale_gross(net_cents: int, kind: str) -> int:
    """What a sale is invoiced at once VAT is added."""
    return gross_from_net(net_cents, kind)


def invoice_bucket(invoice_date: str, terms_days: int, as_of: str) -> str:
    """Which aging bucket an invoice on these terms falls into."""
    return bucket_of(add_days(invoice_date, terms_days), as_of)


def scenario_label(name: str, period: str) -> str:
    return name.strip().upper() + " / " + period.strip().upper()


def demo_book(name: str, cents: int, date: str) -> int:
    """Open a book, post one balanced sale, and return the cash balance."""
    engine = Engine(name)
    engine.open_account("1000-CASH", "Cash At Bank", False)
    engine.open_account("4000-SALES", "Sales", False)
    engine.post("1000-CASH", "debit", cents, date)
    engine.post("4000-SALES", "credit", cents, date)
    return engine.balance("1000-CASH")
