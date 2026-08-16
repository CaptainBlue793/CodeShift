"""Assemble the Markdown migration report from final state.

Deterministic and free — surfaces per-module status, retry counts, type-oracle
failures, unresolved behavioral drift, and what was never checked at all.
Type errors are reported before drift because a module that does not compile
will usually also "diverge", and the compiler message is the actionable one. An
optional LLM-authored narrative is left as a gated enhancement (see reviewer).

"Verified equivalent" is claimed only via `verification.is_trustworthy`, so a
module the harness could not execute is never counted as a success — see
`codeshift.verification` for why that needs saying.
"""
from __future__ import annotations

from codeshift.equivalence.diff import render_call
from codeshift.sandbox.policy import describe
from codeshift.state import MigrationState
from codeshift.verification import (
    LABEL,
    REASON_LABEL,
    is_trustworthy,
    unverified_by_reason,
    unverified_names,
    verdict,
)


def _ordered_modules(state: MigrationState) -> list[str]:
    order = state.get("translation_order") or []
    files = state.get("files", {})
    seen = set(order)
    return [m for m in order if m in files] + [m for m in files if m not in seen]


def build_report(state: MigrationState) -> str:
    files = state.get("files", {})
    order = _ordered_modules(state)
    total = len(files)

    verdicts = {m: verdict(files[m]) for m in order}
    unresolved = [m for m in order if files[m].get("divergences")]
    uncompiled = [m for m in order if files[m].get("type_errors")]
    fully_ok = [m for m in order if is_trustworthy(files[m])]
    partial = [m for m in order if verdicts[m] == "partial"]
    never_ran = [m for m in order if verdicts[m] == "unverified"]
    nothing_to_run = [m for m in order if verdicts[m] == "empty"]

    # --- outcome-first summary ---
    summary = (
        f"Migrated {total} module(s) from {state.get('source_lang')} "
        f"(`{state.get('source_root')}`) to {state.get('target_lang')} "
        f"(`{state.get('output_root')}`): {len(fully_ok)} verified equivalent"
    )
    if uncompiled:
        summary += f", {len(uncompiled)} that do not type-check"
    if unresolved:
        summary += f", {len(unresolved)} with unresolved drift"
    if partial:
        summary += f", {len(partial)} only partially verified"
    if never_ran:
        summary += f", {len(never_ran)} never verified"
    if nothing_to_run:
        summary += f", {len(nothing_to_run)} with nothing to run"
    summary += "."

    lines = ["# CodeShift Migration Report", "", summary, ""]

    # How the code was executed belongs next to the claim that it was verified:
    # "verified equivalent" on the host means generated code ran with the
    # reader's privileges, and that is not a detail to bury in a log.
    isolation = state.get("isolation")
    if isolation:
        lines += [f"> {describe(isolation)}", ""]

    # Same reasoning as isolation: this changes what the table below means. Every
    # other module is translated with its dependencies already in hand; the
    # module a cycle is broken at is not, so it had less to work with.
    cycles = state.get("cycles") or []
    if cycles:
        lines += [
            "> **Circular imports.** Translation order puts a module's dependencies "
            "first, which is impossible inside a cycle. Each cycle below was broken "
            "at its first module, and that module was translated before its own "
            "dependencies existed - with less context than every other module got.",
            ">",
        ]
        for cycle in cycles:
            chain = " -> ".join(f"`{m}`" for m in cycle)
            lines.append(f"> - {chain} -> back to `{cycle[0]}`, broken at **`{cycle[0]}`**")
        lines.append("")

    # --- per-module table ---
    if total:
        lines += [
            "## Modules (translation order)",
            "",
            "| # | Module | Verified | Attempts | Checked | Type errors | Divergences | Notes |",
            "|---|--------|----------|----------|---------|-------------|-------------|-------|",
        ]
        for i, m in enumerate(order, 1):
            u = files[m]
            notes = []
            if u.get("type_errors"):
                notes.append("does not type-check")
            if u.get("divergences"):
                notes.append("unresolved drift")
            if u.get("unverified"):
                notes.append(f"not checked: {', '.join(unverified_names(u))}")
            lines.append(
                f"| {i} | {m} | {LABEL[verdicts[m]]} | {u.get('attempts', 0)} "
                f"| {len(u.get('verified_functions') or [])} "
                f"| {len(u.get('type_errors') or [])} "
                f"| {len(u.get('divergences') or [])} | {'; '.join(notes)} |"
            )
        lines.append("")

    # --- type-oracle failures (listed first: they explain any drift below) ---
    if uncompiled:
        lines += ["## Needs attention - does not type-check", ""]
        for m in uncompiled:
            errs = files[m]["type_errors"]
            lines.append(f"### {m} ({len(errs)} error(s))")
            for e in errs[:10]:
                lines.append(
                    f"- `{e.get('file')}:{e.get('line')}:{e.get('column')}` "
                    f"**{e.get('code')}** - {e.get('message')}"
                )
            if len(errs) > 10:
                lines.append(f"- … and {len(errs) - 10} more")
            lines.append("")

    # --- unresolved drift detail ---
    if unresolved:
        lines += ["## Needs attention - unresolved behavioral drift", ""]
        for m in unresolved:
            divs = files[m]["divergences"]
            lines.append(f"### {m} ({len(divs)} divergence(s))")
            for d in divs[:10]:
                lines.append(
                    f"- `{render_call(d, lambda a: repr(a or []))}` "
                    f"**{d.get('category')}** - {d.get('detail')}"
                )
            if len(divs) > 10:
                lines.append(f"- … and {len(divs) - 10} more")
            lines.append("")

    # --- what was never checked ---
    #
    # Deliberately its own section rather than a footnote: these carry no
    # behavioral evidence at all, and a reader skimming for red flags would
    # otherwise take their empty divergence count as a pass.
    if partial or never_ran:
        lines += [
            "## Not verified - no behavioral evidence",
            "",
            "These were translated but never executed against the original, so a "
            "clean type-check is the only thing vouching for them.",
            "",
        ]
        for m in order:
            grouped = unverified_by_reason(files[m])
            if not grouped:
                continue
            lines.append(f"### {m} ({LABEL[verdicts[m]]})")
            for reason, names in grouped.items():
                lines.append(
                    f"- {', '.join(f'`{n}`' for n in names)} - "
                    f"{REASON_LABEL.get(reason, reason)}"
                )
            lines.append("")

    if nothing_to_run:
        lines += [
            "## Nothing to run",
            "",
            "No executable top-level construct was found in: "
            + ", ".join(f"`{m}`" for m in nothing_to_run),
            "",
        ]

    errors = state.get("errors") or []
    if errors:
        lines += ["## Run errors", "", *[f"- {e}" for e in errors], ""]

    # TODO(reviewer): optional LLM-authored narrative (prompts/reviewer.md),
    # gated behind config to avoid token cost.
    return "\n".join(lines).rstrip() + "\n"
