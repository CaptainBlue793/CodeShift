"""Withholding tax deducted at the point of payment."""
from __future__ import annotations

from core.ids import party_code
from core.money import apply_bps, format_cents
from tax.rates import WITHHOLDING, require_rate


def withheld(gross_cents: int, kind: str) -> int:
    """The amount to withhold from a payment."""
    return apply_bps(gross_cents, require_rate(kind))


def payable(gross_cents: int, kind: str) -> int:
    """What actually leaves the bank once the withholding is deducted."""
    return gross_cents - withheld(gross_cents, kind)


def default_withheld(gross_cents: int) -> int:
    return apply_bps(gross_cents, WITHHOLDING)


def certificate_ref(supplier: str, period: str) -> str:
    """The reference on the certificate handed to the supplier."""
    return "WHT-" + party_code(supplier) + "-" + period.strip().upper()


def certificate_line(supplier: str, gross_cents: int, kind: str) -> str:
    return (
        certificate_ref(supplier, "")
        + " "
        + format_cents(withheld(gross_cents, kind))
        + " withheld from "
        + format_cents(gross_cents)
    )
