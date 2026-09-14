"""Execute translated TypeScript for differential testing via `npx tsx`.

`npx` may download the runner on first use, so this path keeps a longer timeout
than the Python side.

If no Node toolchain can be found, every input gets an honest sentinel rather
than a crash or a silent pass, so the harness marks the module unverified.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from codeshift.adapters.base import EXIT_TIMEOUT, EXIT_UNAVAILABLE, CallOutcome, RunResult

_DRIVER = str(Path(__file__).with_name("_driver.ts"))

#: `npx` may have to fetch `tsx` before it can run anything.
_TIMEOUT = 120


def _sentinel(inputs: list[list], error: str) -> list[CallOutcome]:
    return [CallOutcome(ok=False, error=error) for _ in inputs]


def _run(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
    npx = shutil.which("npx")
    if shutil.which("node") is None or npx is None:
        return RunResult(stderr="no node toolchain", exit_code=EXIT_UNAVAILABLE)
    try:
        proc = subprocess.run(
            [npx, "--yes", "tsx", _DRIVER, str(root), module, func],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(stderr="timeout", exit_code=EXIT_TIMEOUT)
    except (OSError, FileNotFoundError):
        return RunResult(stderr="npx failed", exit_code=1)
    return RunResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def _decode(result: RunResult, inputs: list[list]) -> list[CallOutcome]:
    """Turn one process result into per-input outcomes.

    `runtime_unavailable` stays distinct from `target_run_error`, which is real
    evidence about the translation. A missing Node install must not read as a
    failing test.
    """
    if result.exit_code == EXIT_UNAVAILABLE:
        return _sentinel(inputs, "runtime_unavailable")
    if result.exit_code == EXIT_TIMEOUT:
        return _sentinel(inputs, "target_run_error")
    if result.exit_code != 0:
        return _sentinel(inputs, "target_run_error")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _sentinel(inputs, "target_run_error")
    return [
        CallOutcome(
            ok=d.get("ok", False),
            value=d.get("value"),
            error=d.get("error"),
            state=d.get("state"),
        )
        for d in data
    ]


def run_functions_node(
    root: str,
    module: str,
    func: str,
    inputs: list[list],
    timeout: int | None = None,
    ctor_inputs: list[list] | None = None,
) -> list[CallOutcome]:
    payload = json.dumps({"inputs": inputs, "ctor": ctor_inputs})
    limit = _TIMEOUT if timeout is None else timeout
    return _decode(_run(root, module, func, payload, limit), inputs)
