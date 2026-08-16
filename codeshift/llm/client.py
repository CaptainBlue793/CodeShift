"""The single LLM boundary — local Ollama backend (free, no API key).

Every model call funnels through here, so switching backends is a one-file
change. `ollama` is imported lazily so importing this module needs neither the
package nor a running Ollama server (keeps the graph importable/tests offline).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from codeshift.config import settings
from codeshift.utils.text import strip_think


@lru_cache(maxsize=1)
def get_client():
    import ollama
    return ollama.Client(host=settings.ollama_host)


def load_prompt(name: str, *, optional: bool = False) -> str:
    """Load a prompt template by base name (without extension).

    `name` may include a subdirectory (`"pitfalls/python-typescript"`). Pass
    `optional=True` for templates that only exist for some language pairs — a
    missing file yields "" instead of raising, so an unsupported pair degrades
    to the base prompt rather than failing the run.
    """
    path = Path(settings.prompts_dir, f"{name}.md")
    if optional and not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def complete(*, agent: str, system: str, user: str, max_tokens: Optional[int] = None) -> str:
    """One-shot chat completion via local Ollama.

    `agent` is accepted for a stable interface (per-agent tuning can hook here);
    thinking-model `<think>` blocks are stripped from the reply.
    """
    client = get_client()
    response = client.chat(
        model=settings.model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        options={
            "temperature": settings.temperature,
            "num_predict": max_tokens or settings.max_tokens,
        },
    )
    return strip_think(response["message"]["content"])
