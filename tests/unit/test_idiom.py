"""Tests for the idiom/style agent (formatter backstop; LLM gated off)."""
import shutil

import pytest

from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
from codeshift.agents import idiom

UGLY = "export function add(a:number,b:number){return a+b}"


def _state(out_dir, code=UGLY):
    return {
        "target_lang": "typescript",
        "output_root": str(out_dir),
        "current": "calc",
        "files": {
            "calc": {
                "module": "calc", "path": "calc.py", "imports": [],
                "source_code": "def add(a, b):\n    return a + b\n",
                "translated_code": code, "symbol_map": {}, "inferred_types": None,
                "status": "verified", "attempts": 1, "divergences": [], "unverified": [],
            }
        },
    }


def test_idiom_marks_idiomatic_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(TypeScriptTargetAdapter, "format", lambda self, path: None)
    update = idiom.run(_state(tmp_path))
    unit = update["files"]["calc"]
    assert unit["status"] == "idiomatic"
    assert (tmp_path / "calc.ts").exists()
    assert unit["translated_code"] == UGLY  # format is a no-op here -> unchanged


def test_idiom_handles_missing_code(tmp_path, monkeypatch):
    monkeypatch.setattr(TypeScriptTargetAdapter, "format", lambda self, path: None)
    update = idiom.run(_state(tmp_path, code=None))
    assert update["files"]["calc"]["status"] == "idiomatic"


@pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npx") is None,
    reason="Node toolchain (node/npx) not available",
)
def test_idiom_prettifies_live(tmp_path):
    update = idiom.run(_state(tmp_path))
    code = update["files"]["calc"]["translated_code"]
    assert code != UGLY
    assert "a + b" in code          # prettier added spacing
    assert code.endswith("\n")
