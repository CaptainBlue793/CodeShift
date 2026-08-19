"""Tax rates, held in basis points so no rate is ever a float."""
from __future__ import annotations

from core.text import slugify

STANDARD = 2000
REDUCED = 500
ZERO = 0
WITHHOLDING = 1000

_UNKNOWN_RATE = -1


def rate_for(kind: str) -> int:
    """The rate in basis points for a supply kind, or -1 when unrecognized."""
    key = slugify(kind)
    if key == "standard":
        return STANDARD
    if key == "reduced":
        return REDUCED
    if key == "zero" or key == "exempt":
        return ZERO
    if key == "withholding":
        return WITHHOLDING
    return _UNKNOWN_RATE


def is_known(kind: str) -> bool:
    return rate_for(kind) != _UNKNOWN_RATE


def is_zero_rated(kind: str) -> bool:
    return rate_for(kind) == ZERO


def rate_label(kind: str) -> str:
    """`standard` -> `20.00%`; unknown kinds render as `n/a`."""
    points = rate_for(kind)
    if points == _UNKNOWN_RATE:
        return "n/a"
    whole = points // 100
    rest = points % 100
    return str(whole) + "." + str(rest).rjust(2, "0") + "%"


def require_rate(kind: str) -> int:
    """The rate, raising rather than returning a sentinel."""
    points = rate_for(kind)
    if points == _UNKNOWN_RATE:
        raise ValueError("unknown tax kind: " + kind)
    return points
