"""Render Python annotations as source text.

Its own module because both the module-level parser and the class analyzer need
it, and importing either from the other would close a cycle.
"""
from __future__ import annotations

import ast
from typing import Optional


def annotation_name(ann: Optional[ast.expr]) -> str:
    """Render an annotation as source text, generics and all.

    Kept verbatim (`list[int]`, not a bare `list`) so the target adapter can map
    the element type; unrecognized spellings degrade to "unknown" there.
    """
    if ann is None:
        return "Any"  # missing annotation -> dynamic
    if isinstance(ann, ast.Constant):
        if ann.value is None:
            return "None"  # `-> None`
        if isinstance(ann.value, str):
            return ann.value.strip()  # forward reference: "User"
    try:
        return ast.unparse(ann).strip()
    except (AttributeError, ValueError):
        return "unknown"
