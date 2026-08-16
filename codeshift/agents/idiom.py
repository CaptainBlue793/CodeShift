"""Idiom/style agent — turns literal translations into idiomatic target code.

Runs after a module is verified equivalent, or after its retry budget is spent.
First adopts the best-scoring attempt (see `codeshift.candidates` — the retry
loop is not monotonic, so the last attempt is often not the best one), then
optionally rewrites the literal translation into idiomatic target code with the
LLM (gated behind `settings.use_llm_idiom` to avoid token cost), then always
applies the deterministic formatter backstop and marks the module final
(status="idiomatic").
"""
from __future__ import annotations

from codeshift.adapters import registry
from codeshift.candidates import adopt_best
from codeshift.config import settings
from codeshift.llm import client
from codeshift.state import MigrationState, copy_unit, get_files
from codeshift.utils.fs import read_text
from codeshift.utils.logging import get_logger
from codeshift.utils.text import extract_code

log = get_logger(__name__)


def run(state: MigrationState) -> dict:
    module = state.get("current")
    files = get_files(state)
    if not module or module not in files:
        return {}

    unit = copy_unit(files[module])

    # Last stop before the module is final, so this is where the retry loop's
    # winner replaces its last attempt — the two are often not the same.
    adopted = adopt_best(unit)
    if adopted:
        log.info(
            "idiom: %s adopting attempt %s (score %s) over the final one",
            module,
            adopted.get("attempt"),
            adopted.get("score"),
        )

    code = unit.get("translated_code")
    if not code:
        unit["status"] = "idiomatic"
        files[module] = unit
        return {"files": files}

    tgt_lang = state.get("target_lang", "typescript")
    target = registry.target(tgt_lang, output_root=state.get("output_root", "data/output"))

    if settings.use_llm_idiom:
        system = client.load_prompt("idiom").replace("{target_lang}", tgt_lang)
        code = extract_code(client.complete(agent="idiom", system=system, user=code))

    path = target.emit(module, code)
    target.format(path)                 # deterministic backstop (no-op if unavailable)
    unit["translated_code"] = read_text(path)
    unit["status"] = "idiomatic"
    files[module] = unit

    log.info("idiom: %s formatted -> %s", module, path)
    return {"files": files}
