"""TypeScript target adapter — emit files, tsc typecheck, eslint/prettier, run."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from codeshift.adapters.base import CallOutcome, TargetAdapter
from codeshift.utils.typestr import parse_generic, split_top_level

# Scalar Python type name -> TypeScript type. Unknown -> "unknown".
_SCALARS = {
    "int": "number", "float": "number", "bool": "boolean", "str": "string",
    "bytes": "Uint8Array", "None": "null", "NoneType": "null",
    "Any": "any", "object": "unknown", "unknown": "unknown",
}

# Bare (unparameterized) containers, when no element type is available.
_BARE_CONTAINERS = {
    "list": "unknown[]", "List": "unknown[]", "Sequence": "unknown[]",
    "Iterable": "unknown[]", "tuple": "unknown[]", "Tuple": "unknown[]",
    "dict": "Record<string, unknown>", "Dict": "Record<string, unknown>",
    "Mapping": "Record<string, unknown>", "set": "Set<unknown>",
    "Set": "Set<unknown>", "frozenset": "ReadonlySet<unknown>",
}

_SEQUENCES = {"list", "List", "Sequence", "Iterable", "Collection"}
_MAPPINGS = {"dict", "Dict", "Mapping", "MutableMapping"}
_SETS = {"set", "Set", "MutableSet"}


def _map_type(source_type: str) -> str:
    """Map a Python type expression to TypeScript, recursing through generics."""
    text = (source_type or "").strip()
    if not text:
        return "unknown"

    # PEP 604 unions: `str | None` -> `string | null`
    if "|" in text and (members := split_top_level(text, "|")) and len(members) > 1:
        return " | ".join(dict.fromkeys(_map_type(m) for m in members))

    base, args = parse_generic(text)

    if args is None:
        return _SCALARS.get(base) or _BARE_CONTAINERS.get(base) or "unknown"

    if base in ("Optional",) and len(args) == 1:
        return f"{_map_type(args[0])} | null"
    if base in ("Union",):
        return " | ".join(dict.fromkeys(_map_type(a) for a in args))
    if base in _SEQUENCES and len(args) == 1:
        return f"{_map_type(args[0])}[]"
    if base in _SETS and len(args) == 1:
        return f"Set<{_map_type(args[0])}>"
    if base == "frozenset" and len(args) == 1:
        return f"ReadonlySet<{_map_type(args[0])}>"
    if base in _MAPPINGS and len(args) == 2:
        key = _map_type(args[0])
        # An untyped key means "a plain dict"; JS object keys are strings anyway.
        if key in ("any", "unknown"):
            key = "string"
        # TS index keys must be string/number/symbol; anything else needs a Map.
        if key in ("string", "number"):
            return f"Record<{key}, {_map_type(args[1])}>"
        return f"Map<{key}, {_map_type(args[1])}>"
    if base in ("tuple", "Tuple"):
        if len(args) == 2 and args[1] == "...":
            return f"{_map_type(args[0])}[]"     # tuple[X, ...] is a variadic list
        return f"[{', '.join(_map_type(a) for a in args)}]"

    return _BARE_CONTAINERS.get(base, "unknown")


class TypeScriptTargetAdapter(TargetAdapter):
    def __init__(self, output_root: str = "data/output") -> None:
        self.output_root = output_root

    def emit(self, module: str, code: str) -> str:
        rel = module.replace(".", "/") + ".ts"
        path = Path(self.output_root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(code, encoding="utf-8")
        return str(path)

    def exports(self, code: str) -> list[str]:
        from codeshift.adapters.typescript.symbols import extract_exports
        return extract_exports(code)

    def map_type(self, source_type: str) -> str:
        return _map_type(source_type)

    def typecheck(self, root: str) -> list[dict]:
        """Run the tsc oracle over `root`. Empty when tsc could not run — see
        `typecheck.tsc_available()` to distinguish that from a clean check."""
        from codeshift.adapters.typescript.typecheck import run_tsc
        from codeshift.config import settings
        return run_tsc(root, strict=settings.tsc_strict, timeout=settings.oracle_timeout)

    def format(self, path: str) -> None:
        """Format `path` in place with prettier. No-op if the toolchain is
        unavailable (an idiomatic backstop, never fatal). TODO: eslint --fix."""
        npx = shutil.which("npx")
        if npx is None:
            return
        try:
            subprocess.run(
                [npx, "--yes", "prettier", "--write", path],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return

    def run(
        self,
        root: str,
        module: str,
        func: str,
        inputs: list[list],
        ctor_inputs: Optional[list[list]] = None,
    ) -> list[CallOutcome]:
        from codeshift.adapters.typescript.runner import run_functions_node
        return run_functions_node(root, module, func, inputs, ctor_inputs=ctor_inputs)
