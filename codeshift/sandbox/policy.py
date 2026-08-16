"""Which isolation the differential run actually gets — decided once, out loud.

`docker_runner` knows *how* to isolate. This decides *whether* it is used, and
insists the answer be visible.

That matters because the fallback is not harmless. The differential harness
executes code a language model wrote, and the honest description of the
unsandboxed path is "runs arbitrary generated code on the host as you". A
fallback nobody notices is worse than no sandbox at all, because it looks like
one. So each mode below either isolates, or states plainly that it did not:

    "docker"  require isolation. No Docker -> nothing runs, and the modules are
              reported unverified. Never quietly downgraded; this is the setting
              for code you did not write.
    "auto"    isolate when Docker is there, else run on the host and say so —
              once in the log, and again in the migration report.
    "host"    no isolation, chosen deliberately. Fast, and fine for a fixture
              you wrote yourself.

`effective()` is cached because the warning belongs in the log once per run, not
once per function call.
"""
from __future__ import annotations

from typing import Literal

from codeshift.sandbox import docker_runner
from codeshift.utils.logging import get_logger

log = get_logger(__name__)

#: What a run *got*, which is not always what it asked for. "unavailable" means
#: isolation was required and could not be had, so nothing should be executed.
Isolation = Literal["docker", "host", "unavailable"]

DESCRIPTION: dict[str, str] = {
    "docker": (
        "Differential runs executed in Docker: no network, read-only mounts, "
        "non-root, memory- and PID-capped."
    ),
    "host": (
        "Differential runs executed **directly on the host, without isolation** "
        "- translated code ran with your privileges. Set `sandbox=\"docker\"` in "
        "`codeshift/config.py` before pointing CodeShift at code you did not write."
    ),
    "unavailable": (
        "Isolation was required (`sandbox=\"docker\"`) but Docker was unavailable, "
        "so no code was executed and nothing could be verified behaviorally."
    ),
}

_cached: Isolation | None = None


def effective() -> Isolation:
    """Resolve the configured mode against what this machine can actually do."""
    global _cached
    if _cached is not None:
        return _cached

    from codeshift.config import settings

    mode = settings.sandbox
    if mode == "host":
        log.warning(
            "sandbox: disabled by config - generated code will run on the host "
            "with no isolation"
        )
        _cached = "host"
    elif mode == "docker":
        if docker_runner.docker_available():
            _cached = "docker"
        else:
            log.error(
                "sandbox: isolation is required but Docker is unavailable - "
                "no code will be executed; modules will be reported unverified"
            )
            _cached = "unavailable"
    else:  # "auto"
        if docker_runner.docker_available():
            _cached = "docker"
        else:
            log.warning(
                "sandbox: Docker unavailable - falling back to running generated "
                "code on the host WITHOUT isolation (sandbox=\"auto\"). Set "
                'sandbox="docker" to require isolation instead.'
            )
            _cached = "host"
    return _cached


def describe(mode: str | None = None) -> str:
    """One line for the migration report."""
    return DESCRIPTION.get(mode or effective(), "Isolation status unknown.")


def reset() -> None:
    """Forget the resolved mode (tests, and config changes mid-session)."""
    global _cached
    _cached = None
    docker_runner.reset_caches()
