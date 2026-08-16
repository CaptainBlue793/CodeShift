"""Small text helpers."""
from __future__ import annotations

import re

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE_BLOCK = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)


def strip_think(text: str) -> str:
    """Remove <think>...</think> reasoning blocks emitted by some local models."""
    return _THINK_RE.sub("", text).strip()


def extract_code(text: str) -> str:
    """Extract source code from a chat reply, discarding surrounding prose.

    - Complete ```fenced``` block(s): return their concatenated contents.
    - Opening fence with no closing fence: drop the fence line(s), keep the body.
    - Code followed by a stray fence + prose: cut at the stray fence.
    - Otherwise: return the text unchanged.
    """
    text = text.strip()
    blocks = _FENCE_BLOCK.findall(text)
    if blocks:
        return "\n\n".join(b.strip() for b in blocks).strip()
    if text.startswith("```"):
        # Opening fence with no matching close: drop the ```lang line (and any
        # trailing fence), keep the body — never return empty here.
        lines = text.splitlines()[1:]
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    idx = text.find("```")
    if idx != -1:
        return text[:idx].strip()  # code first, then a stray fence + prose
    return text
