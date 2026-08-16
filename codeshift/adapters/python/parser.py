"""Python source adapter — ast-based parsing, signature extraction, execution.

Discovers modules under a root, maps file paths to dotted module names, resolves
each module's imports down to the set of **internal** modules it depends on, and
supports signature extraction + sandboxed execution for differential testing.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from codeshift.adapters.base import (
    CallOutcome,
    FuncSig,
    ParsedModule,
    ParsedProject,
    SourceAdapter,
    Untestable,
)
from codeshift.adapters.python.annotations import annotation_name
from codeshift.adapters.python.classes import class_plan, method_types, requires_keyword_only
from codeshift.config import settings


def _module_name(root: Path, file: Path) -> tuple[str, bool]:
    """Return (dotted module name, is_package) for a file under root."""
    rel = file.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    is_package = bool(parts) and parts[-1] == "__init__"
    if is_package:
        parts = parts[:-1]
    return ".".join(parts), is_package


def _longest_internal_prefix(dotted: str, internal: set[str]) -> Optional[str]:
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in internal:
            return candidate
    return None


def _resolve_from_base(node: ast.ImportFrom, current: str, is_package: bool) -> Optional[str]:
    if node.level == 0:
        return node.module
    parts = current.split(".") if current else []
    anchor = parts[:] if is_package else parts[:-1]
    up = node.level - 1
    if up > len(anchor):
        return None
    anchor = anchor[: len(anchor) - up]
    if node.module:
        anchor = anchor + node.module.split(".")
    return ".".join(anchor)


def _resolve_imports(tree: ast.AST, current: str, is_package: bool, internal: set[str]) -> set[str]:
    deps: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                dep = _longest_internal_prefix(alias.name, internal)
                if dep and dep != current:
                    deps.add(dep)
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_base(node, current, is_package)
            if base is None:
                continue
            matched = False
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                dep = _longest_internal_prefix(candidate, internal)
                if dep and dep != current:
                    deps.add(dep)
                    matched = True
            if not matched and base:
                dep = _longest_internal_prefix(base, internal)
                if dep and dep != current:
                    deps.add(dep)
    return deps


def _parse(source_code: str) -> Optional[ast.Module]:
    try:
        return ast.parse(source_code)
    except SyntaxError:
        return None


class PythonSourceAdapter(SourceAdapter):
    def parse(self, root: str) -> ParsedProject:
        root_path = Path(root)
        files = sorted(root_path.rglob("*.py"))

        parsed: list[tuple[str, bool, Path, str, Optional[ast.AST]]] = []
        for f in files:
            name, is_package = _module_name(root_path, f)
            if not name:
                continue
            source = f.read_text(encoding="utf-8")
            try:
                tree: Optional[ast.AST] = ast.parse(source, filename=str(f))
            except SyntaxError:
                tree = None  # TODO: surface parse errors to the run's error list
            parsed.append((name, is_package, f, source, tree))

        internal = {name for name, *_ in parsed}

        project = ParsedProject()
        for name, is_package, f, source, tree in parsed:
            imports = _resolve_imports(tree, name, is_package, internal) if tree else set()
            rel_path = str(f.relative_to(root_path)).replace("\\", "/")
            project.modules.append(
                ParsedModule(module=name, path=rel_path, source_code=source, imports=sorted(imports))
            )
        return project

    def signatures(self, source_code: str) -> list[FuncSig]:
        """Top-level functions, plus every method the harness can reach.

        Methods arrive qualified (`Cart.add_item`) and carry their class's
        constructor types, so the harness can build a receiver; see
        `codeshift.adapters.python.classes` for which ones qualify.
        """
        tree = _parse(source_code)
        if tree is None:
            return []
        sigs: list[FuncSig] = []
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                if requires_keyword_only(node):
                    continue   # cannot be called positionally; named in `untestable`
                params = [annotation_name(a.annotation) for a in node.args.args]
                sigs.append(FuncSig(name=node.name, params=params, returns=annotation_name(node.returns)))
            elif isinstance(node, ast.ClassDef):
                sigs.extend(class_plan(node).signatures)
        return sigs

    def untestable(self, source_code: str) -> list[Untestable]:
        """Everything `signatures` skips: async defs, and unreachable members.

        Classes are no longer skipped wholesale — only the parts of them that
        cannot be built or called, each named individually so the report says
        *which* method went unchecked rather than shrugging at the class.
        """
        tree = _parse(source_code)
        if tree is None:
            return []
        out: list[Untestable] = []
        for node in tree.body:
            if isinstance(node, ast.AsyncFunctionDef):
                out.append(Untestable(name=node.name, reason="async_function"))
            elif isinstance(node, ast.FunctionDef) and requires_keyword_only(node):
                out.append(Untestable(name=node.name, reason="keyword_only_function"))
            elif isinstance(node, ast.ClassDef):
                out.extend(class_plan(node).skipped)
        return out

    def run(
        self,
        root: str,
        module: str,
        func: str,
        inputs: list[list],
        ctor_inputs: Optional[list[list]] = None,
    ) -> list[CallOutcome]:
        from codeshift.adapters.python.runner import run_functions
        return run_functions(root, module, func, inputs, ctor_inputs=ctor_inputs)

    def _declared_types(self, source_code: str) -> dict:
        """Types as written in the source (missing annotation -> "Any")."""
        tree = _parse(source_code)
        if tree is None:
            return {}
        out: dict[str, dict] = {}
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                params = {a.arg: annotation_name(a.annotation) for a in node.args.args}
                out[node.name] = {"params": params, "returns": annotation_name(node.returns)}
            elif isinstance(node, ast.ClassDef):
                out.update(method_types(node))
        return out

    def infer_types(
        self, source_code: str, *, root: str | None = None, module: str | None = None
    ) -> dict:
        """Declared annotations, refined by mypy where it has something to say.

        mypy is an overlay rather than a replacement: it resolves generics and
        infers unannotated returns, but it reports nothing for functions it
        cannot analyze, and those keep their declared types.
        """
        declared = self._declared_types(source_code)
        if not (settings.use_mypy_oracle and root and module):
            return declared

        from codeshift.adapters.python.type_extraction import extract_types
        inferred = extract_types(root, module, source_code, timeout=settings.oracle_timeout)
        for func, info in inferred.items():
            if func in declared:
                declared[func] = info
        return declared
