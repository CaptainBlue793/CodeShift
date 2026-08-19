"""Money as integer cents. No internal dependencies.

Everything here is exact integer arithmetic: floating point cannot represent
most decimal amounts, and an accounting engine that loses a cent to rounding is
worse than useless. Amounts are signed; which direction that means is the
caller's business.
"""
from __future__ import annotations

CENTS_PER_UNIT = 100


def abs_cents(cents: int) -> int:
    return -cents if cents < 0 else cents


def negate(cents: int) -> int:
    return -cents


def is_zero(cents: int) -> bool:
    return cents == 0


def parse_amount(text: str) -> int:
    """Parse a written amount such as `-1,234.56` into cents.

    Raises `ValueError` on anything that is not a well-formed amount, rather
    than guessing: a misread figure is worse than a rejected one.
    """
    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned:
        raise ValueError("empty amount")
    negative = cleaned.startswith("-")
    if negative or cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError("sign with no digits")
    whole, sep, frac = cleaned.partition(".")
    if sep and len(frac) > 2:
        raise ValueError("more than two decimal places")
    if whole and not whole.isdigit():
        raise ValueError("bad whole part")
    if frac and not frac.isdigit():
        raise ValueError("bad fractional part")
    if not whole and not frac:
        raise ValueError("no digits")
    units = int(whole) if whole else 0
    cents = int((frac + "00")[:2]) if frac else 0
    total = units * CENTS_PER_UNIT + cents
    return -total if negative else total


def format_cents(cents: int) -> str:
    """Render cents as a fixed two-decimal string, e.g. `-1234.56`."""
    sign = "-" if cents < 0 else ""
    magnitude = abs_cents(cents)
    units = magnitude // CENTS_PER_UNIT
    rest = magnitude % CENTS_PER_UNIT
    return sign + str(units) + "." + str(rest).rjust(2, "0")


def apply_bps(cents: int, basis_points: int) -> int:
    """`cents` x `basis_points`/10000, rounded half away from zero.

    Rounding the magnitude keeps the result symmetric about zero, so reversing
    a posting reverses its tax to the cent.
    """
    product = abs_cents(cents) * abs_cents(basis_points)
    rounded = (product + 5000) // 10000
    negative = (cents < 0) != (basis_points < 0)
    return -rounded if negative else rounded


def allocate(cents: int, parts: int) -> list[int]:
    """Split `cents` into `parts` shares summing back to `cents` exactly.

    The remainder is spread one cent at a time over the leading shares, which
    is how an invoice is split without inventing or losing money.
    """
    if parts <= 0:
        raise ValueError("parts must be positive")
    negative = cents < 0
    magnitude = abs_cents(cents)
    base = magnitude // parts
    remainder = magnitude % parts
    shares = []
    for index in range(parts):
        share = base + 1 if index < remainder else base
        shares.append(-share if negative else share)
    return shares
