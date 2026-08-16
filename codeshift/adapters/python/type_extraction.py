"""Python type extraction via the mypy oracle, used by the source adapter.

Named `type_extraction` (not `types`) so this file can never shadow the stdlib
`types` module when the package directory ends up on sys.path.

How it works: mypy has no "dump me the signatures" mode, so we append one
`reveal_type(<target>)` line per callable — functions and methods alike, since
`Cart.add_item` is a perfectly ordinary expression — and read the notes back. The
augmented copy is fed to mypy with **`--shadow-file`**, which type-checks the
*real* path while reading our contents — so internal imports still resolve
against the actual source tree and we never write into the user's project.

What this buys over reading annotations off the AST: bare containers gain their
type arguments (`dict` -> `dict[Any, Any]`), and aliases and forward references
resolve to concrete types.

What it does **not** buy: mypy never infers a function's return type, so an
unannotated return stays `Any`. Inferring those — the thing a dynamic->static
migration most wants — needs pyright, whose `reveal_type` output this module's
`parse_callable` is already shaped to accept.

Missing/broken mypy returns `{}` and the adapter falls back to annotations.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from codeshift.utils.typestr import split_top_level

# `file.py:12: note: Revealed type is "def (text: builtins.str) -> builtins.str"`
_REVEAL_RE = re.compile(
    r'^.*?:(?P<line>\d+):(?:\d+:)?\s*note:\s*Revealed type is\s+"(?P<type>.*)"\s*$'
)


def module_file(root: str, module: str) -> Optional[Path]:
    """Resolve a dotted module name to its file under `root`."""
    rel = module.replace(".", "/")
    for candidate in (Path(root) / f"{rel}.py", Path(root) / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def normalize_type(raw: str) -> str:
    """Turn a mypy type string into source-language spelling.

    `builtins.list[builtins.int]` -> `list[int]`; `Union[builtins.str, None]`
    -> `Optional[str]`. Qualified names from other modules are left alone —
    the target adapter maps what it recognizes and shrugs at the rest.
    """
    text = raw.strip()
    text = re.sub(r"\bbuiltins\.", "", text)
    text = re.sub(r"\btyping\.", "", text)
    text = text.replace("*", "")  # tuple-ish fallbacks like `tuple[Any, ...]`
    match = re.fullmatch(r"Union\[(.+),\s*None\]", text)
    if match and "," not in _strip_brackets(match.group(1)):
        return f"Optional[{match.group(1).strip()}]"
    return text


def _strip_brackets(text: str) -> str:
    """Remove bracketed sections, so top-level commas can be counted."""
    out, depth = [], 0
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return "".join(out)


def parse_callable(revealed: str) -> Optional[dict]:
    """Parse mypy's callable syntax into {"params": {...}, "returns": ...}.

    Input looks like `def (a: builtins.int, b: builtins.str =) -> builtins.str`.
    Returns None if `revealed` is not a callable (e.g. the name was shadowed).
    """
    text = revealed.strip()
    if not text.startswith("def "):
        return None
    open_idx = text.find("(")
    if open_idx == -1:
        return None

    depth, close_idx = 0, -1
    for i in range(open_idx, len(text)):
        if text[i] in "([":
            depth += 1
        elif text[i] in ")]":
            depth -= 1
            if depth == 0:
                close_idx = i
                break
    if close_idx == -1:
        return None

    arrow = text.find("->", close_idx)
    returns = normalize_type(text[arrow + 2:]) if arrow != -1 else "Any"

    params: dict[str, str] = {}
    for i, chunk in enumerate(split_top_level(text[open_idx + 1:close_idx])):
        chunk = chunk.rstrip("=").strip()   # trailing `=` marks a default
        if chunk.startswith("*"):
            continue                        # *args/**kwargs are not positionally testable
        if ":" in chunk:
            name, _, type_text = chunk.partition(":")
            params[name.strip()] = normalize_type(type_text)
        elif chunk:
            params[f"arg{i}"] = normalize_type(chunk)  # positional-only, unnamed
    return {"params": params, "returns": returns}


def _augment(source_code: str, targets: list[str]) -> tuple[str, dict[int, str]]:
    """Append `reveal_type(f)` per target; return (code, line -> target name)."""
    lines = source_code.splitlines()
    if lines and lines[-1].strip():
        lines.append("")
    probe_map: dict[int, str] = {}
    for name in targets:
        lines.append(f"reveal_type({name})")
        probe_map[len(lines)] = name   # 1-indexed, matching mypy's report
    return "\n".join(lines) + "\n", probe_map


def probe_targets(source_code: str) -> list[str]:
    """Names worth asking mypy about: top-level functions, and methods.

    `reveal_type(Cart.add_item)` is an ordinary module-level expression, so a
    method needs no special handling on the way in — only the implicit first
    parameter has to come back off, in `_drop_receiver`. Probing a dataclass's
    synthesized `__init__` is the one way to learn its constructor types, since
    there is no `def __init__` in the source to read them from.
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    from codeshift.adapters.python.classes import method_types

    targets: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            targets.append(node.name)
        elif isinstance(node, ast.ClassDef):
            targets.extend(method_types(node))
    return targets


def _drop_receiver(parsed: dict) -> dict:
    """Remove a method's implicit first parameter.

    mypy reveals a method as its *unbound* signature (`def (self: Cart, ...)`),
    but the harness calls it on an instance and the target language declares no
    such parameter, so `self`/`cls` would show up as one argument too many.
    """
    params = {name: t for name, t in parsed["params"].items() if name not in ("self", "cls")}
    return {"params": params, "returns": parsed["returns"]}


def extract_types(root: str, module: str, source_code: str, *, timeout: int = 180) -> dict:
    """Run mypy over `module` and return inferred types per callable.

    Keyed as `signatures()` names things, so methods appear as `Cart.add_item`.
    Returns `{}` on any failure — missing mypy, an unresolvable module, a
    timeout — leaving the caller to fall back to declared annotations.
    """
    found = module_file(root, module)
    if found is None:
        return {}
    # Absolute: the subprocess runs with cwd=root, so a relative path here would
    # be resolved against root a second time.
    real = found.resolve()
    cwd = Path(root).resolve()
    targets = probe_targets(source_code)
    if not targets:
        return {}

    augmented, probe_map = _augment(source_code, targets)

    shadow_fd, shadow_path = tempfile.mkstemp(suffix=".py", prefix="codeshift_mypy_")
    try:
        with os.fdopen(shadow_fd, "w", encoding="utf-8") as fh:
            fh.write(augmented)

        cmd = [
            sys.executable, "-m", "mypy",
            "--shadow-file", str(real), shadow_path,
            "--no-error-summary",
            "--no-color-output",
            "--no-pretty",
            "--hide-error-context",
            "--no-incremental",        # shadow files and the cache do not mix
            "--ignore-missing-imports",
            "--follow-imports", "silent",
            str(real),
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
                cwd=str(cwd),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return {}

        out: dict[str, dict] = {}
        for line in f"{proc.stdout}\n{proc.stderr}".splitlines():
            match = _REVEAL_RE.match(line.strip())
            if not match:
                continue
            name = probe_map.get(int(match.group("line")))
            if name is None:
                continue
            parsed = parse_callable(match.group("type"))
            if parsed is not None:
                out[name] = _drop_receiver(parsed) if "." in name else parsed
        return out
    finally:
        try:
            os.unlink(shadow_path)
        except OSError:
            pass
