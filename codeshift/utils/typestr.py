"""Bracket-aware helpers for parsing type strings.

Type annotations nest (`dict[str, list[int]]`), so naive `split(",")` corrupts
them. Both the Python source adapter (reading mypy output) and the TypeScript
target adapter (mapping types across languages) need the same two operations,
and neither owns them — so they live here, language-neutral.
"""
from __future__ import annotations

from typing import Optional

_OPEN, _CLOSE = "[(", "])"


def split_top_level(text: str, sep: str = ",") -> list[str]:
    """Split on `sep` only where it is not nested inside brackets or parens."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip() for p in parts if p.strip()]


def parse_generic(text: str) -> tuple[str, Optional[list[str]]]:
    """Split `list[int]` into `("list", ["int"])`; `int` into `("int", None)`.

    The base is returned unqualified (`typing.List` -> `List`) so callers can
    match on a single spelling.
    """
    text = text.strip()
    if not text.endswith("]") or "[" not in text:
        return _unqualify(text), None
    base, _, rest = text.partition("[")
    return _unqualify(base), split_top_level(rest[:-1])


def _unqualify(name: str) -> str:
    """Drop a leading module path: `typing.List` -> `List`."""
    return name.strip().rsplit(".", 1)[-1] if "." in name else name.strip()
