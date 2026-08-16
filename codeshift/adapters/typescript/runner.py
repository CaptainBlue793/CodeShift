"""Execute translated TypeScript for differential testing, isolated where possible.

In the sandbox, `tsx` is baked into the image and run directly — the container
has no network (by design), so nothing can be fetched at run time. On the host
path it is `npx tsx`, which may download the runner on first use; that path
therefore keeps a longer timeout.

If no runtime can be reached at all, every input gets an honest sentinel rather
than a crash or a silent pass, so the harness marks the module unverified.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from codeshift.adapters.base import CallOutcome, RunResult
from codeshift.sandbox import docker_runner, policy
from codeshift.sandbox.docker_runner import EXIT_TIMEOUT, EXIT_UNAVAILABLE, Mount

_DRIVER = str(Path(__file__).with_name("_driver.ts"))
_DRIVER_NAME = Path(_DRIVER).name

#: The host path may have to fetch `tsx` through npx before it can run anything.
_HOST_TIMEOUT = 120


def _sentinel(inputs: list[list], error: str) -> list[CallOutcome]:
    return [CallOutcome(ok=False, error=error) for _ in inputs]


def _run_host(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
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


def _run_docker(root: str, module: str, func: str, payload: str, timeout: int) -> RunResult:
    from codeshift.config import settings

    return docker_runner.run_in_container(
        "node",
        ["tsx", f"/driver/{_DRIVER_NAME}", "/work", module, func],
        mounts=[
            Mount(host=root, container="/work"),
            Mount(host=docker_runner.stage_driver(_DRIVER), container="/driver"),
        ],
        stdin=payload,
        timeout=timeout,
        # --read-only leaves /tmp as the only writable path; point every cache there.
        env={"HOME": "/tmp", "XDG_CACHE_HOME": "/tmp", "TSX_DISABLE_CACHE": "1"},
        memory=settings.sandbox_memory,
        cpus=settings.sandbox_cpus,
    )


def _decode(result: RunResult, inputs: list[list]) -> list[CallOutcome]:
    """Turn one process result into per-input outcomes.

    The two "we never ran it" codes stay distinct from `target_run_error`, which
    is real evidence about the translation. A missing Node install must not read
    as a failing test.
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
    from codeshift.config import settings

    mode = policy.effective()
    if mode == "unavailable":
        return _sentinel(inputs, "sandbox_unavailable")

    payload = json.dumps({"inputs": inputs, "ctor": ctor_inputs})
    if mode == "docker":
        limit = settings.sandbox_timeout if timeout is None else timeout
        return _decode(_run_docker(root, module, func, payload, limit), inputs)
    limit = _HOST_TIMEOUT if timeout is None else timeout
    return _decode(_run_host(root, module, func, payload, limit), inputs)
