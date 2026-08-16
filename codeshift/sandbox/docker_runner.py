"""Run code inside throwaway, hardened Docker containers via the docker CLI.

Using the CLI (not the docker Python SDK) keeps the dependency surface free of
extra packages.

The container is the only thing between the host and code an LLM wrote, so the
flags in `_HARDENING` are the substance of this module, not decoration:

    --network none            no exfiltration and no downloads at run time
    --read-only + --tmpfs     nothing survives the call; /tmp is the sole writable path
    --user 1000:1000          not root, even inside the container
    --cap-drop ALL            no capabilities to escalate with
    --security-opt no-new-privileges
    --memory/--cpus/--pids-limit   a runaway loop costs one container, not the box

Mounts are read-only without exception: the differential run only ever needs to
*read* code, and a writable mount would hand the sandboxed process the host tree
it was isolated from.

Images are tagged by a hash of their Dockerfile, so editing a Dockerfile builds
a new image instead of silently reusing a stale one.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from codeshift.adapters.base import RunResult
from codeshift.utils.logging import get_logger

log = get_logger(__name__)

#: `run_in_container` exit codes that mean "the sandbox itself did not run",
#: as distinct from "the code inside it failed". Callers must not read the
#: latter into the former: a missing Docker daemon is not a failing test.
EXIT_TIMEOUT = 124
EXIT_UNAVAILABLE = 125

_IMAGES_DIR = Path(__file__).parent / "images"

#: Logical image key -> Dockerfile under `images/`.
IMAGE_FILES = {
    "python": "python.Dockerfile",
    "node": "node.Dockerfile",
}

_HARDENING = [
    "--network", "none",
    "--read-only",
    "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
    "--user", "1000:1000",
    "--cap-drop", "ALL",
    "--security-opt", "no-new-privileges",
    "--pids-limit", "128",
]


@dataclass(frozen=True)
class Mount:
    """A host directory to expose in the container. Always read-only."""
    host: str
    container: str

    def as_arg(self) -> str:
        # POSIX form ("C:/Users/...") is what Docker Desktop expects on Windows,
        # and is already correct everywhere else.
        return f"{Path(self.host).resolve().as_posix()}:{self.container}:ro"


def _docker() -> str | None:
    return shutil.which("docker")


@lru_cache(maxsize=1)
def docker_available() -> bool:
    """True only if the CLI exists *and* a daemon answers.

    An installed `docker.exe` with Docker Desktop stopped is the common case on
    Windows, and it fails at `run` time rather than at `which` time — so probe
    the daemon, not the binary.
    """
    exe = _docker()
    if exe is None:
        return False
    try:
        proc = subprocess.run(
            [exe, "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return proc.returncode == 0


def image_tag(key: str) -> str:
    """`codeshift-sandbox-<key>:<hash of the Dockerfile>`.

    Content-addressed on purpose: a hand-edited Dockerfile that kept a fixed tag
    would leave the old, less-hardened image in place forever.
    """
    text = (_IMAGES_DIR / IMAGE_FILES[key]).read_bytes()
    return f"codeshift-sandbox-{key}:{hashlib.sha256(text).hexdigest()[:12]}"


@lru_cache(maxsize=None)
def ensure_image(key: str, *, build_timeout: int = 900) -> bool:
    """Build the sandbox image if it is not already present. True if usable.

    The build needs the network (it installs a runtime); the *run* never does.
    """
    exe = _docker()
    if exe is None:
        return False
    tag = image_tag(key)
    try:
        present = subprocess.run(
            [exe, "image", "inspect", tag], capture_output=True, text=True, timeout=60
        )
        if present.returncode == 0:
            return True
        log.info("sandbox: building image %s (first run only)", tag)
        built = subprocess.run(
            [exe, "build", "-f", str(_IMAGES_DIR / IMAGE_FILES[key]), "-t", tag, str(_IMAGES_DIR)],
            capture_output=True, text=True, timeout=build_timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("sandbox: image build for %s failed: %s", tag, exc)
        return False
    if built.returncode != 0:
        log.warning("sandbox: image build for %s failed: %s", tag, built.stderr.strip()[:500])
        return False
    return True


@lru_cache(maxsize=None)
def stage_driver(driver_path: str) -> str:
    """Copy one driver file into an otherwise-empty directory, and return it.

    The drivers live beside the adapters' own modules. Mounting that directory
    would put CodeShift's source inside the sandbox for no reason, so the driver
    travels alone.
    """
    staged = Path(tempfile.mkdtemp(prefix="codeshift-driver-"))
    shutil.copy2(driver_path, staged / Path(driver_path).name)
    return str(staged)


def container_argv(
    image: str,
    cmd: list[str],
    *,
    mounts: list[Mount],
    env: dict[str, str] | None = None,
    memory: str = "512m",
    cpus: str = "1",
) -> list[str]:
    """The full `docker run` argv. Split out so tests can assert the hardening."""
    argv = ["docker", "run", "--rm", "-i", *_HARDENING, "--memory", memory, "--cpus", cpus]
    for mount in mounts:
        argv += ["-v", mount.as_arg()]
    for key, value in (env or {}).items():
        argv += ["-e", f"{key}={value}"]
    return [*argv, "-w", "/work", image, *cmd]


def run_in_container(
    image_key: str,
    cmd: list[str],
    *,
    mounts: list[Mount],
    stdin: str = "",
    timeout: int = 60,
    env: dict[str, str] | None = None,
    memory: str = "512m",
    cpus: str = "1",
) -> RunResult:
    """Run `cmd` in the sandbox image for `image_key`.

    Returns `EXIT_UNAVAILABLE` when the sandbox could not be established at all.
    Callers must surface that as "not executed" rather than as a test failure.
    """
    exe = _docker()
    if exe is None or not docker_available() or not ensure_image(image_key):
        return RunResult(stderr="sandbox unavailable", exit_code=EXIT_UNAVAILABLE)

    argv = container_argv(image_tag(image_key), cmd, mounts=mounts, env=env, memory=memory, cpus=cpus)
    argv[0] = exe
    try:
        proc = subprocess.run(
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return RunResult(stderr="timeout", exit_code=EXIT_TIMEOUT)
    except OSError as exc:
        return RunResult(stderr=str(exc), exit_code=EXIT_UNAVAILABLE)
    return RunResult(stdout=proc.stdout, stderr=proc.stderr, exit_code=proc.returncode)


def reset_caches() -> None:
    """Forget daemon/image probes (tests, and after starting Docker mid-session)."""
    docker_available.cache_clear()
    ensure_image.cache_clear()
