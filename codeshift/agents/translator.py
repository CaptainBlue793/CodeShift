"""Translator — emits target-language code for the current module.

Renders prompts/translator.md plus, when one exists for the language pair,
prompts/pitfalls/<source>-<target>.md — operations that look equivalent across
the two languages and are not. Feeds in source code, dependency interfaces, and
target-language type hints, calls the model through the `llm.client` boundary,
strips code fences, writes the target file, records a source->target symbol map,
and updates the FileUnit. On a retry the prompt carries the previous attempt's
code (line-numbered, so the diagnostics resolve against it) followed by what it
failed: type-oracle diagnostics (from the type-inference node) first, then any
behavioral divergences (from the test-equivalence loop), deduped to distinct
failure modes.
"""
from __future__ import annotations

from pathlib import Path

from codeshift.adapters import registry
from codeshift.equivalence.diff import distinct_divergences, render_call
from codeshift.llm import client
from codeshift.state import FileUnit, MigrationState, copy_unit, get_files
from codeshift.typing_hints import build_type_hints, render_hints
from codeshift.utils.logging import get_logger
from codeshift.utils.naming import build_symbol_map
from codeshift.utils.text import extract_code

log = get_logger(__name__)


def _relative_to_root(path: str, output_root: str) -> str:
    """Emitted path relative to the output root, so type-oracle diagnostics
    (which are reported relative to that root) can be matched against it."""
    try:
        return str(Path(path).resolve().relative_to(Path(output_root).resolve())).replace("\\", "/")
    except (ValueError, OSError):
        return Path(path).name


def _number_lines(code: str) -> str:
    """Prefix each line with its 1-based number.

    The oracle diagnostics are line-numbered, so the code they refer to has to
    carry the same numbers for the model to locate the fault.
    """
    return "\n".join(
        f"{i:>4} | {line}" for i, line in enumerate(code.splitlines(), 1)
    )


def _render_args(args: list | None) -> str:
    """Render a divergence's input args, truncated so one pathological input
    cannot crowd out the rest of the prompt."""
    text = ", ".join(repr(a) for a in (args or []))
    return text if len(text) <= 120 else f"{text[:117]}..."


def _format_divergences(divergences: list[dict], limit: int = 6) -> list[str]:
    """Collapse divergences to distinct failure modes, keeping one example each.

    The harness reports one record per failing input, so a single bug arrives as
    dozens of near-identical lines (25 of them in practice). Feeding all of them
    in buries the signal and crowds out the code under repair, so dedupe on
    (function, category, detail) — none of which include the args — and keep the
    first example's args as the concrete repro.
    """
    lines = [
        f"- {render_call(d, _render_args)} [{d.get('category')}]: {d.get('detail')}"
        for d in distinct_divergences(divergences)
    ]
    distinct = len(lines)
    shown = lines[:limit]
    if distinct > limit:
        shown.append(f"  (+{distinct - limit} more distinct failure mode(s))")
    if len(divergences) > distinct:
        shown.append(
            f"  ({len(divergences)} failing input(s) collapsed to {distinct} "
            "distinct failure(s); one example input shown per failure.)"
        )
    return shown


def _degenerate_reason(code: str, source_names: list[str], exports: list[str]) -> str | None:
    """Why this emission is unusable, or None if it looks like a real module.

    Judged on *top-level* names only: a method lives inside its class and never
    appears in the export list, so counting methods here would condemn every
    class-shaped module as export-less.
    """
    if not code.strip():
        return "the model returned no code at all"
    if source_names and not exports:
        names = ", ".join(source_names)
        return (
            f"the source module defines {len(source_names)} top-level symbol(s) "
            f"({names}) but the output exports none"
        )
    return None


def _dependency_context(state: MigrationState, unit: FileUnit) -> str:
    """Assemble already-translated interfaces of this module's dependencies."""
    files = get_files(state)
    blocks = []
    for dep in unit.get("imports", []):
        dep_unit = files.get(dep)
        if dep_unit and dep_unit.get("translated_code"):
            blocks.append(
                f"// ---- dependency: {dep} ({dep_unit['path']}) ----\n"
                f"{dep_unit['translated_code']}"
            )
    return "\n\n".join(blocks)


def run(state: MigrationState) -> dict:
    module = state.get("current")
    files = get_files(state)
    if not module or module not in files:
        return {}

    unit = copy_unit(files[module])
    src_lang = state.get("source_lang", "python")
    tgt_lang = state.get("target_lang", "typescript")

    source = registry.source(src_lang)
    target = registry.target(tgt_lang, output_root=state.get("output_root", "data/output"))

    system = (
        client.load_prompt("translator")
        .replace("{source_lang}", src_lang)
        .replace("{target_lang}", tgt_lang)
    )

    # Semantic trip-wires for this specific language pair, when a sheet exists.
    # Kept out of translator.md so the base prompt stays language-agnostic, and
    # supplied up front rather than as retry feedback: these produce code that
    # compiles and passes review, so the model has no way to infer them from an
    # example — it only learns of them by burning the whole retry budget.
    pitfalls = client.load_prompt(f"pitfalls/{src_lang}-{tgt_lang}", optional=True)
    if pitfalls:
        system = f"{system}\n\n{pitfalls}"

    parts = [
        f"Module: {module}",
        f"Path: {unit['path']}",
        "",
        f"Source ({src_lang}):",
        unit["source_code"],
    ]

    hints = build_type_hints(
        source, target, unit["source_code"], root=state.get("source_root"), module=module
    )
    if hints:
        parts += ["", f"Target-language type hints (use these for {tgt_lang} types):", render_hints(hints)]

    deps = _dependency_context(state, unit)
    if deps:
        parts += ["", "Already-translated dependency interfaces:", deps]
    # On a retry the model MUST see the code that produced the failures below.
    # Without it the line-numbered diagnostics point into a file it was never
    # shown, so its only option is to regenerate from the same source — which at
    # a low temperature reproduces the same output and the same failures. (Before
    # this was fixed, every module burned all 3 attempts with byte-identical
    # error counts.)
    previous = unit.get("translated_code")
    if previous and (unit.get("type_errors") or unit.get("divergences")):
        parts += [
            "",
            f"Your previous attempt ({tgt_lang}), with line numbers matching the "
            "diagnostics below. REVISE this code — do not start over, and keep "
            "everything that is not implicated below:",
            _number_lines(previous),
        ]
    # Type errors first: code that does not compile is the more basic failure,
    # and the divergence list from such a run is usually noise anyway.
    if unit.get("type_errors"):
        parts += [
            "",
            f"The previous attempt did not type-check ({tgt_lang}); fix these first:",
            *[
                f"- line {e.get('line')}: {e.get('code')} {e.get('message')}"
                for e in unit["type_errors"]
            ],
        ]
    if unit.get("divergences"):
        parts += [
            "",
            "The previous attempt ran but did not match the source's behavior on "
            "these inputs. The source's result is correct; fix the target:",
            *_format_divergences(unit["divergences"]),
        ]
    user = "\n".join(parts)

    raw = client.complete(agent="translator", system=system, user=user)
    code = extract_code(raw)

    source_names = [s.name for s in source.signatures(unit["source_code"])]
    # `Cart.add_item` is exported as `Cart`; the export list only ever holds the
    # outermost name, so that is what the guard and the symbol map compare.
    top_level = list(dict.fromkeys(name.partition(".")[0] for name in source_names))
    exports = target.exports(code)

    # Reject degenerate output *before* writing it. An empty or export-less
    # module passes the type gate trivially — there is nothing in it to check —
    # so the damage only surfaces later as total drift here plus unresolvable
    # imports in every dependent module. Keeping the previous attempt on disk
    # and feeding the rejection back is strictly better than emitting nothing.
    reason = _degenerate_reason(code, top_level, exports)
    if reason:
        unit["attempts"] = unit.get("attempts", 0) + 1
        unit["rejected"] = reason
        unit["type_errors"] = [
            {
                "line": 1,
                "code": "CODESHIFT_EMPTY",
                "message": f"Output rejected: {reason}. Emit the complete module.",
            }
        ]
        files[module] = unit
        log.warning("translator: %s -> output rejected (%s)", module, reason)
        return {"files": files}

    unit["rejected"] = None
    out_path = target.emit(module, code)

    # Record the source-function -> target-export name map so the equivalence
    # agent can call the right symbol across the language boundary.
    symbol_map = build_symbol_map(source_names, exports)

    unit["translated_code"] = code
    # Keep the first accepted emission for the dashboard's retry diff. Rejected
    # output is deliberately not recorded: "what the model first produced" means
    # the first thing that survived the degenerate-output guard, not a 0-byte file.
    if not unit.get("first_code"):
        unit["first_code"] = code
    unit["target_path"] = _relative_to_root(out_path, state.get("output_root", "data/output"))
    unit["symbol_map"] = symbol_map
    unit["attempts"] = unit.get("attempts", 0) + 1
    unit["status"] = "translated"
    files[module] = unit
    log.info("translator: %s -> %s", module, out_path)
    return {"files": files}
