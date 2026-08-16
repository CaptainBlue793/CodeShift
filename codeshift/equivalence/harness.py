"""Orchestrate original-vs-translated runs for one module.

For each signature: generate inputs — plus constructor arguments, when the
callable is a method and needs a receiver — run both implementations on the
identical inputs, and classify any divergences. If either side could not be
executed at all, the function is reported as *unverifiable* rather than passing —
and, just as importantly, rather than diverging.

That second point is the whole reason `_INFRASTRUCTURE` exists. A runner that
cannot start returns a failure per input, and to `classify_divergence` a side
that failed against a side that returned is textbook `exception_behavior`. So a
stopped Docker daemon would otherwise arrive as a wall of behavioral findings
about code that was never run. Infrastructure failures are not evidence.

Inputs are returned so the caller can cache and reuse them across retries — that
keeps the divergence feedback consistent with what the next attempt is tested on.
"""
from __future__ import annotations

from typing import Optional

from codeshift.adapters.base import CallOutcome, FuncSig, SourceAdapter, TargetAdapter, Untestable
from codeshift.equivalence.diff import classify_divergence
from codeshift.equivalence.inputs import generate_inputs

#: Runner sentinels that mean "this never executed". Distinct from `*_run_error`
#: and `source_timeout`, which are things the code itself did.
_INFRASTRUCTURE = {"runtime_unavailable", "sandbox_unavailable"}


def _not_executed(outcomes: list[CallOutcome]) -> Optional[str]:
    """The sentinel, if *every* outcome is the same infrastructure failure."""
    if not outcomes:
        return None
    first = outcomes[0].error
    if first not in _INFRASTRUCTURE:
        return None
    return first if all(not o.ok and o.error == first for o in outcomes) else None


def plan_inputs(sig: FuncSig, n: int) -> dict:
    """Inputs for one signature: call args, plus constructor args if it needs a
    receiver.

    Every call gets its *own* constructor arguments, so an instance method is
    exercised on a freshly built object on both sides. That keeps each
    comparison a function of its own inputs — with a shared receiver, one
    diverging call would poison every call after it and the report would blame
    the wrong method.

    The two lists are cycled to a common length so a no-argument method still
    gets tested against `n` different receivers, and a method with arguments on
    a no-argument class still gets its `n` inputs.
    """
    args = generate_inputs(sig.params, n=n)
    if sig.ctor_params is None:
        return {"args": args, "ctor": None}

    ctor = generate_inputs(sig.ctor_params, n=n)
    rows = max(len(args), len(ctor))
    return {"args": (args * rows)[:rows], "ctor": (ctor * rows)[:rows]}


def check_equivalence(
    *,
    source_adapter: SourceAdapter,
    source_root: str,
    target_adapter: TargetAdapter,
    target_root: str,
    module: str,
    signatures: list[FuncSig],
    target_names: Optional[dict[str, str]] = None,
    n: int = 25,
    inputs_by_func: Optional[dict[str, dict]] = None,
) -> tuple[list[dict], list[Untestable], dict[str, dict]]:
    """Return (divergences, unverifiable, inputs_used_by_func).

    Each `Untestable` carries the reason its function was never compared, so the
    report can say which — a missing Node install and an unavailable sandbox are
    both "no evidence", but only one of them is fixed by installing Node.

    Pass `inputs_by_func` from a previous call to reuse the same inputs (so a
    retry is tested on exactly the inputs whose failures were fed back). Each
    entry is a `plan_inputs` result: `{"args": [...], "ctor": [...] | None}`.
    """
    target_names = target_names or {}
    inputs_by_func = inputs_by_func or {}
    divergences: list[dict] = []
    unverifiable: list[Untestable] = []
    used_inputs: dict[str, dict] = {}

    for sig in signatures:
        plan = inputs_by_func.get(sig.name) or plan_inputs(sig, n)
        used_inputs[sig.name] = plan
        inputs, ctor = plan["args"], plan.get("ctor")

        src_out = source_adapter.run(source_root, module, sig.name, inputs, ctor_inputs=ctor)
        # Check the source side before spending a target run on a comparison
        # that cannot happen.
        reason = _not_executed(src_out)
        if reason:
            unverifiable.append(Untestable(name=sig.name, reason=reason))
            continue

        tgt_func = target_names.get(sig.name, sig.name)
        tgt_out = target_adapter.run(target_root, module, tgt_func, inputs, ctor_inputs=ctor)
        reason = _not_executed(tgt_out)
        if reason:
            unverifiable.append(Untestable(name=sig.name, reason=reason))
            continue

        for i, (args, s, t) in enumerate(zip(inputs, src_out, tgt_out)):
            record = classify_divergence(
                sig.name, args, s, t, ctor=ctor[i] if ctor is not None else None
            )
            if record:
                divergences.append(record)

    return divergences, unverifiable, used_inputs
