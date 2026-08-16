"""tsc oracle helpers used by the TypeScript target adapter.

Runs `tsc --noEmit` over the emitted modules and parses the diagnostics into
plain dicts. Two deliberate choices:

* **`npx --package typescript tsc`**, never bare `npx tsc` — the `tsc` package on
  npm is an unrelated squatter that prints a warning and exits non-zero.
* **Ambient-only diagnostics are dropped** (see `_AMBIENT_CODES`). The check runs
  without `@types/node`, so `require`/`module`/`process` resolve to "cannot find
  name". Those describe our sandbox, not the translation — feeding them back to
  the translator would send it chasing phantom errors.

Like the runner, this degrades honestly: no Node toolchain means an empty
diagnostic list, never a crash and never a false "clean" claim (callers
distinguish the two via `tsc_available`).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

# `file.ts(12,5): error TS2304: Cannot find name 'foo'.`
_DIAG_RE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s+"
    r"(?P<severity>error|warning)\s+TS(?P<code>\d+):\s+(?P<message>.*)$"
)

# Diagnostics that only mean "no ambient Node/DOM declarations here".
_AMBIENT_CODES = {
    2318,  # cannot find global type
    2580,  # cannot find name 'require' (needs @types/node)
    2584,  # cannot find name 'console' (needs lib.dom)
    2591,  # cannot find name 'module'/'require' (needs @types/node)
    2592,  # cannot find name '$' (needs @types/jquery)
    2593,  # cannot find name 'describe' (needs @types/jest)
    2688,  # cannot find type definition file
}

# Bare/`node:`-prefixed builtins a translation may legitimately import; the
# resulting TS2307 is a missing @types/node, not a broken relative import.
_NODE_BUILTINS = {
    "assert", "buffer", "child_process", "crypto", "events", "fs", "http",
    "https", "os", "path", "process", "readline", "stream", "string_decoder",
    "timers", "url", "util", "worker_threads", "zlib",
}

_QUOTED = re.compile(r"['\"]([^'\"]+)['\"]")


def tsc_available() -> bool:
    """True if the Node toolchain needed to run the oracle is present."""
    return shutil.which("node") is not None and shutil.which("npx") is not None


def _is_ambient(code: int, message: str) -> bool:
    """True if a diagnostic reflects missing ambient types rather than a defect."""
    if code in _AMBIENT_CODES:
        return True
    if code == 2307:  # "Cannot find module 'x'" — only ignore node builtins
        match = _QUOTED.search(message)
        if match:
            spec = match.group(1)
            base = spec[5:] if spec.startswith("node:") else spec
            return spec.startswith("node:") or base.split("/")[0] in _NODE_BUILTINS
    return False


def parse_diagnostics(output: str, root: str | None = None) -> list[dict]:
    """Parse raw `tsc --pretty false` output into diagnostic dicts.

    Split out from the subprocess call so it is testable without a toolchain.
    """
    root_path = Path(root).resolve() if root else None
    diagnostics: list[dict] = []
    for line in output.splitlines():
        match = _DIAG_RE.match(line.strip())
        if not match:
            continue  # summary lines, blank lines, npm chatter
        code = int(match.group("code"))
        message = match.group("message").strip()
        if _is_ambient(code, message):
            continue
        file = match.group("file").strip()
        if root_path:
            try:
                file = str(Path(file).resolve().relative_to(root_path)).replace("\\", "/")
            except (ValueError, OSError):
                pass  # outside root — keep as reported
        diagnostics.append(
            {
                "file": file,
                "line": int(match.group("line")),
                "column": int(match.group("col")),
                "code": f"TS{code}",
                "severity": match.group("severity"),
                "message": message,
            }
        )
    return diagnostics


def run_tsc(root: str, *, strict: bool = False, timeout: int = 300) -> list[dict]:
    """Type-check every `.ts` file under `root`; return parsed diagnostics.

    Returns `[]` when the toolchain is unavailable or there is nothing to check;
    call `tsc_available()` first if you need to tell "clean" from "not run".
    """
    npx = shutil.which("npx")
    if not tsc_available() or npx is None:
        return []

    root_path = Path(root)
    files = [
        str(p) for p in sorted(root_path.rglob("*.ts"))
        if "node_modules" not in p.parts
    ]
    if not files:
        return []

    # Passing files explicitly makes tsc ignore any tsconfig.json it would
    # otherwise discover by walking up out of the output directory.
    cmd = [
        npx, "--yes", "--package", "typescript", "tsc",
        "--noEmit",
        "--pretty", "false",
        "--target", "es2020",
        "--lib", "es2020,dom",          # console/JSON without @types/node
        "--module", "esnext",
        "--moduleResolution", "bundler",  # extensionless relative imports
        "--skipLibCheck",
        "--strict", "true" if strict else "false",
        *files,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []

    return parse_diagnostics(f"{proc.stdout}\n{proc.stderr}", root=root)
