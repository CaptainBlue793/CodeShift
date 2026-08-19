"""VAT on a net or gross amount, in integer cents throughout."""
from __future__ import annotations

from core.money import apply_bps, format_cents
from tax.rates import rate_label, require_rate


def vat_on_net(net_cents: int, kind: str) -> int:
    """The tax due on a net amount."""
    return apply_bps(net_cents, require_rate(kind))


def gross_from_net(net_cents: int, kind: str) -> int:
    return net_cents + vat_on_net(net_cents, kind)


def net_from_gross(gross_cents: int, kind: str) -> int:
    """Strip the tax back out of a gross amount.

    Dividing by `1 + rate` is done as one integer expression: computing the tax
    first and subtracting it would round twice and lose a cent on some totals.
    """
    points = require_rate(kind)
    magnitude = -gross_cents if gross_cents < 0 else gross_cents
    net = (magnitude * 10000 + (10000 + points) // 2) // (10000 + points)
    return -net if gross_cents < 0 else net


def vat_on_gross(gross_cents: int, kind: str) -> int:
    return gross_cents - net_from_gross(gross_cents, kind)


def vat_line(net_cents: int, kind: str) -> str:
    """`VAT standard 20.00% on 100.00 = 20.00`."""
    return (
        "VAT "
        + kind.strip().lower()
        + " "
        + rate_label(kind)
        + " on "
        + format_cents(net_cents)
        + " = "
        + format_cents(vat_on_net(net_cents, kind))
    )
