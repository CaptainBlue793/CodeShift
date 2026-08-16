"""Central configuration: the local LLM model, generation params, paths.

The LLM is local Ollama — free, no API key. The whole stack is now free/OSS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Settings:
    # --- LLM: local Ollama (free) ---
    model: str = "qwen3:14b"         # alt: "qwen2.5:7b" (faster) or "phi4"
    max_tokens: int = 8192           # Ollama num_predict cap
    temperature: float = 0.2         # low -> more deterministic code
    ollama_host: str | None = None   # None -> ollama default (localhost:11434)

    # --- pipeline ---
    max_retries: int = 3             # translate<->verify loop cap, per file
    use_llm_idiom: bool = False      # LLM idiomatic rewrite (free now; off by default for speed)
    recursion_limit: int = 500       # LangGraph superstep cap (real work is bounded by max_retries)

    # --- sandbox: how the differential run executes generated code ---
    #
    # "docker" requires isolation and refuses to execute without it (use this
    # for code you did not write); "auto" isolates when Docker is present and
    # otherwise runs on the host, saying so in the log and the report; "host"
    # is deliberate, unisolated execution. See codeshift/sandbox/policy.py.
    sandbox: Literal["auto", "docker", "host"] = "auto"
    sandbox_memory: str = "512m"     # per-container memory cap
    sandbox_cpus: str = "1"          # per-container CPU cap
    sandbox_timeout: int = 60        # seconds per differential call batch

    # --- type oracles (free: local tsc via npx, local mypy) ---
    use_tsc_oracle: bool = True      # typecheck emitted code before the differential run
    tsc_strict: bool = False         # strict floods LLM output with implicit-any noise
    use_mypy_oracle: bool = True     # infer source types with mypy (ast annotations if absent)
    oracle_timeout: int = 300        # seconds; the first npx run downloads the compiler

    # --- paths (relative to project root) ---
    prompts_dir: str = "codeshift/llm/prompts"
    cache_dir: str = "data/cache"


settings = Settings()
