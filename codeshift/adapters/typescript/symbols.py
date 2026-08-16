"""Extract exported symbol names from TypeScript source."""
from __future__ import annotations

import re

_EXPORT_RE = re.compile(
    r"^\s*export\s+(?:default\s+)?(?:async\s+)?(?:function|const|let|var|class)\s+"
    r"([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


def extract_exports(code: str) -> list[str]:
    """Return names of top-level exported functions/consts/classes."""
    return _EXPORT_RE.findall(code)
