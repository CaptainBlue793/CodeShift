"""Language -> adapter lookup. Imports are lazy so importing the registry does
not pull in every adapter's dependencies (tree-sitter, etc.).
"""
from __future__ import annotations

from codeshift.adapters.base import SourceAdapter, TargetAdapter


def source(lang: str) -> SourceAdapter:
    if lang == "python":
        from codeshift.adapters.python.parser import PythonSourceAdapter
        return PythonSourceAdapter()
    raise ValueError(f"No source adapter registered for language: {lang!r}")


def target(lang: str, output_root: str = "data/output") -> TargetAdapter:
    if lang == "typescript":
        from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
        return TypeScriptTargetAdapter(output_root=output_root)
    raise ValueError(f"No target adapter registered for language: {lang!r}")
