"""Test-equivalence agent — catches semantic drift.

Runs the original and translated code against identical inputs, diffs the
outputs, and records any divergences on the FileUnit. The graph routes back to
the translator when divergences remain and retries are left.

Classes are exercised the same way as functions: the harness builds an instance
and calls the method on it, comparing what comes back *and* what the object
holds afterwards. What it cannot reach — an abstract class, an async method, a
constructor whose arguments cannot be generated — is recorded by name, as are
callables whose target side could not be executed at all (e.g. no Node
toolchain). Without that, a module the harness never touched is stored exactly
like one that passed; see `codeshift.verification`.

Neither kind of gap routes back to the translator: retrying cannot make an
abstract class testable or conjure a Node install, so the module proceeds and
carries the gap into the report.
"""
from __future__ import annotations

from codeshift.adapters import registry
from codeshift.candidates import record_candidate
from codeshift.equivalence.harness import check_equivalence
from codeshift.sandbox import policy
from codeshift.state import MigrationState, copy_unit, get_files, unchanged
from codeshift.utils.logging import get_logger

log = get_logger(__name__)


def run(state: MigrationState) -> dict:
    module = state.get("current")
    files = get_files(state)
    if not module or module not in files:
        return unchanged(state)

    unit = copy_unit(files[module])
    src_lang = state.get("source_lang", "python")
    tgt_lang = state.get("target_lang", "typescript")
    output_root = state.get("output_root", "data/output")

    source = registry.source(src_lang)
    target = registry.target(tgt_lang, output_root=output_root)
    signatures = source.signatures(unit["source_code"])

    divergences, unrunnable, used_inputs = check_equivalence(
        source_adapter=source,
        source_root=state["source_root"],
        target_adapter=target,
        target_root=output_root,
        module=module,
        signatures=signatures,
        target_names=unit.get("symbol_map") or None,
        inputs_by_func=unit.get("test_inputs") or None,  # reuse across retries
    )

    # Two ways to end up unchecked: never extractable as a signature, or
    # extractable but unrunnable. The report needs to tell them apart.
    unverified = [
        {"name": item.name, "reason": item.reason}
        for item in source.untestable(unit["source_code"])
    ]
    unverified += [{"name": item.name, "reason": item.reason} for item in unrunnable]
    unrunnable_names = {item.name for item in unrunnable}

    unit["test_inputs"] = used_inputs
    unit["divergences"] = divergences
    unit["verified_functions"] = [s.name for s in signatures if s.name not in unrunnable_names]
    unit["unverified"] = unverified
    unit["status"] = "translated" if divergences else "verified"

    # Both metrics are real only here, past the differential run — so this is
    # the one place an attempt can be scored against its predecessors.
    candidate = record_candidate(unit)
    files[module] = unit

    if unverified:
        log.warning(
            "test_equivalence: %s not verified: %s",
            module,
            ", ".join(f"{e['name']} ({e['reason']})" for e in unverified),
        )
    log.info(
        "test_equivalence: %s -> %d divergence(s), %d checked, %d unverified "
        "(attempt %d score=%s)",
        module,
        len(divergences),
        len(unit["verified_functions"]),
        len(unverified),
        unit.get("attempts", 0),
        candidate,
    )
    # Recorded from the one node that actually executes code, so the report
    # states the isolation the run *had*, not the isolation it was configured for.
    return {"files": files, "isolation": policy.effective()}
