"""Execute Python functions for differential testing, isolated where possible.

Two execution paths, one decoder. Which path runs is `sandbox.policy`'s call,
not this module's — see there for why the choice is made loudly.

The source side is sandboxed too, not just the translated side. It is the user's
own code rather than the model's, but the harness compares the two runs, so an
asymmetry in *how* they run is an asymmetry in what a divergence means.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from codeshift.adapters.base import CallOutcome, RunResult
from codeshift.sandbox import docker_runner, policy
from codeshift.sandbox.docker_runner import EXIT_TIMEOUT, EXIT_UNAVAILABLE, Mount

_DRIVER = str(Path(__file__).with_name("_driver.py"))
_DRIVER_NAME = Path(_DRIVER).name


def _sentinel(inputs: list[list], error: str) -> list[CallOutcome]:
    return [CallOutcome(ok=False, error=error) for _ in inputs]


def _run_host(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
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


def _run_docker(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
    from codeshift.config import settings

    return docker_runner.run_in_container(
        "python",
        ["python", "-P", f"/driver/{_DRIVER_NAME}", "/work", module, func],
        mounts=[
            Mount(host=root, container="/work"),
            Mount(host=docker_runner.stage_driver(_DRIVER), container="/driver"),
        ],
        stdin=payload,
        timeout=timeout,
        # No writable HOME under --read-only; keep the interpreter out of it.
        env={"PYTHONDONTWRITEBYTECODE": "1", "HOME": "/tmp"},
        memory=settings.sandbox_memory,
        cpus=settings.sandbox_cpus,
    )


def _decode(result: RunResult, inputs: list[list]) -> list[CallOutcome]:
    """Turn one process result into per-input outcomes.

    `sandbox_unavailable` is kept distinct from `source_run_error` on purpose:
    the harness treats the first as "never checked" and the second as evidence
    about the code. Collapsing them would let a stopped Docker daemon read as a
    behavioral finding.
    """
    if result.exit_code == EXIT_UNAVAILABLE:
        return _sentinel(inputs, "sandbox_unavailable")
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

    timeout = settings.sandbox_timeout if timeout is None else timeout
    mode = policy.effective()
    if mode == "unavailable":
        return _sentinel(inputs, "sandbox_unavailable")

    payload = json.dumps({"inputs": inputs, "ctor": ctor_inputs})
    runner = _run_docker if mode == "docker" else _run_host
    return _decode(runner(root, module, func, payload, timeout), inputs)
