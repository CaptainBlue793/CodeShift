"""Central configuration: the local LLM model, generation params, paths.

The LLM is local Ollama — free, no API key. The whole stack is now free/OSS.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # --- LLM: local Ollama (free) ---
    model: str = "qwen3:14b"         # alt: "qwen2.5:7b" (faster) or "phi4"
    # num_predict cap. 8192 was enough for the 5-line fixtures and is not
    # enough for real modules: on a 31-module run, two of the first four
    # emissions came back empty because a reasoning model spent the whole
    # budget thinking and had nothing left to write the code with. Each one
    # burned a retry attempt. The cap costs nothing when it is not reached.
    max_tokens: int = 16384
    temperature: float = 0.2         # low -> more deterministic code
    ollama_host: str | None = None   # None -> ollama default (localhost:11434)

    # --- pipeline ---
    max_retries: int = 3             # translate<->verify loop cap, per file
    use_llm_idiom: bool = False      # LLM idiomatic rewrite (free now; off by default for speed)
    recursion_limit: int = 500       # LangGraph superstep cap (real work is bounded by max_retries)

    run_timeout: int = 60            # seconds per differential call batch (Python side)

    # --- type oracles (free: local tsc via npx, local mypy) ---
    use_tsc_oracle: bool = True      # typecheck emitted code before the differential run
    tsc_strict: bool = False         # strict floods LLM output with implicit-any noise
    use_mypy_oracle: bool = True     # infer source types with mypy (ast annotations if absent)
    oracle_timeout: int = 300        # seconds; the first npx run downloads the compiler

    # --- paths (relative to project root) ---
    prompts_dir: str = "codeshift/llm/prompts"
    cache_dir: str = "data/cache"


settings = Settings()
