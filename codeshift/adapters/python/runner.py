"""Execute Python functions for differential testing, one subprocess per batch."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codeshift.adapters.base import EXIT_TIMEOUT, CallOutcome, RunResult

_DRIVER = str(Path(__file__).with_name("_driver.py"))


def _sentinel(inputs: list[list], error: str) -> list[CallOutcome]:
    return [CallOutcome(ok=False, error=error) for _ in inputs]


def _run(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
    try:
        proc = subprocess.run(
            # -P: don't prepend the driver's own dir to sys.path (avoids shadowing
            # stdlib modules with sibling files); the driver adds `root` itself.
            [sys.executable, "-P", _DRIVER, str(root), module, func],
            input=payload,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(stderr="timeout", exit_code=EXIT_TIMEOUT)
    return RunResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def _decode(result: RunResult, inputs: list[list]) -> list[CallOutcome]:
    """Turn one process result into per-input outcomes."""
    if result.exit_code == EXIT_TIMEOUT:
        return _sentinel(inputs, "source_timeout")
    if result.exit_code != 0:
        return _sentinel(inputs, "source_run_error")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return _sentinel(inputs, "source_run_error")
    return [
        CallOutcome(
            ok=d.get("ok", False),
            value=d.get("value"),
            error=d.get("error"),
            state=d.get("state"),
        )
        for d in data
    ]


def run_functions(
    root: str,
    module: str,
    func: str,
    inputs: list[list],
    timeout: int | None = None,
    ctor_inputs: list[list] | None = None,
) -> list[CallOutcome]:
    from codeshift.config import settings

    timeout = settings.run_timeout if timeout is None else timeout
    payload = json.dumps({"inputs": inputs, "ctor": ctor_inputs})
    return _decode(_run(root, module, func, payload, timeout), inputs)
