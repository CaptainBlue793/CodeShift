"""Diagnostic codes and message formatting. No internal dependencies.

Codes are short strings rather than an enum so they survive serialization and
compare cheaply; severity is derived from the code's leading letter.
"""
from __future__ import annotations

FATAL_PREFIX = "E"
WARNING_PREFIX = "W"
INFO_PREFIX = "I"


def format_error(code: str, detail: str) -> str:
    """Render one diagnostic as `CODE: detail`, or just the code when bare."""
    code = code.strip().upper()
    detail = detail.strip()
    if not code:
        return detail
    if not detail:
        return code
    return code + ": " + detail


def severity(code: str) -> int:
    """3 for fatal, 2 for warning, 1 for info, 0 for anything unrecognized."""
    code = code.strip().upper()
    if not code:
        return 0
    head = code[0]
    if head == FATAL_PREFIX:
        return 3
    if head == WARNING_PREFIX:
        return 2
    if head == INFO_PREFIX:
        return 1
    return 0


def is_fatal(code: str) -> bool:
    return severity(code) == 3


def worst(first: str, second: str) -> str:
    """The more severe of two codes; a tie keeps the first."""
    if severity(second) > severity(first):
        return second
    return first


def code_number(code: str) -> int:
    """The numeric part of a code (`E204` -> 204), or -1 when there is none."""
    digits = "".join(c for c in code if c.isdigit())
    if not digits:
        return -1
    return int(digits)
