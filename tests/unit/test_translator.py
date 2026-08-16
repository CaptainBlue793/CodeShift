"""Translator tests — LLM is mocked, so these cost nothing and are deterministic.

Verifies the wiring: prompt assembly, code-fence stripping, target-file emission,
and FileUnit updates.
"""
import pytest

import codeshift.llm.client as client
from codeshift.agents import translator
from codeshift.state import FileUnit

SOURCE = "def make_user(user_id, name):\n    return {'id': user_id, 'name': name}\n"
CANNED = (
    "```typescript\n"
    "export function makeUser(userId: number, name: string) {\n"
    "  return { id: userId, name };\n"
    "}\n"
    "```"
)


def _state(out_dir):
    return {
        "source_lang": "python",
        "target_lang": "typescript",
        "output_root": str(out_dir),
        "current": "models",
        "max_retries": 3,
        "files": {
            "models": FileUnit(
                module="models",
                path="models.py",
                imports=[],
                source_code=SOURCE,
                translated_code=None,
                inferred_types=None,
                status="pending",
                attempts=0,
                divergences=[],
            )
        },
    }


def test_translator_updates_unit_and_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "complete", lambda **kwargs: CANNED)

    update = translator.run(_state(tmp_path))
    unit = update["files"]["models"]

    assert unit["status"] == "translated"
    assert unit["attempts"] == 1
    assert "export function makeUser" in unit["translated_code"]
    assert "```" not in unit["translated_code"]          # fences stripped

    out_file = tmp_path / "models.ts"
    assert out_file.exists()
    assert "makeUser" in out_file.read_text(encoding="utf-8")


def test_first_attempt_is_recorded_and_never_overwritten(tmp_path, monkeypatch):
    """The dashboard's retry diff compares first-vs-shipped, so the first
    emission has to survive every later attempt that overwrites `translated_code`."""
    monkeypatch.setattr(client, "complete", lambda **kwargs: CANNED)
    state = _state(tmp_path)

    first = translator.run(state)["files"]["models"]
    assert "makeUser" in first["first_code"]
    assert first["first_code"] == first["translated_code"]

    # Second attempt: a different output, driven back by a type error.
    revised = "export function makeUser(userId: number, name: string) {\n  return { id: userId, name, extra: 1 };\n}\n"
    monkeypatch.setattr(client, "complete", lambda **kwargs: revised)
    state["files"]["models"] = first
    first["type_errors"] = [{"line": 2, "code": "TS1", "message": "boom"}]

    second = translator.run(state)["files"]["models"]
    assert "extra: 1" in second["translated_code"]       # latest attempt moved on
    assert "extra: 1" not in second["first_code"]        # but the original is intact
    assert second["first_code"] == first["first_code"]


def test_rejected_output_does_not_become_the_first_attempt(tmp_path, monkeypatch):
    """"What the model first produced" means the first thing that survived the
    degenerate-output guard — not a 0-byte file that was never written."""
    monkeypatch.setattr(client, "complete", lambda **kwargs: "")
    state = _state(tmp_path)

    rejected = translator.run(state)["files"]["models"]
    assert rejected["rejected"]
    assert not rejected.get("first_code")

    monkeypatch.setattr(client, "complete", lambda **kwargs: CANNED)
    state["files"]["models"] = rejected
    recovered = translator.run(state)["files"]["models"]
    assert "makeUser" in recovered["first_code"]


def test_translator_passes_source_and_deps_to_llm(tmp_path, monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return CANNED

    monkeypatch.setattr(client, "complete", fake_complete)
    translator.run(_state(tmp_path))

    assert captured["agent"] == "translator"
    assert "make_user" in captured["user"]                # source code included
    assert "typescript" in captured["system"].lower()     # template rendered
    assert "type hints" in captured["user"].lower()       # inferred types passed in
    assert "-> " in captured["user"]                       # rendered signature hint


# ------------------------------------------------- dependency context

def _state_with_dep(out_dir, *, dep_translated: bool):
    """`models` importing `helpers`, which may or may not be translated yet."""
    state = _state(out_dir)
    state["files"]["models"]["imports"] = ["helpers"]
    state["files"]["helpers"] = FileUnit(
        module="helpers",
        path="helpers.py",
        imports=["models"],                       # mutual: this is a cycle
        source_code="def slug(text):\n    return text.strip().lower()\n",
        translated_code="export function slug(t: string) { return t.trim(); }"
        if dep_translated
        else None,
        inferred_types=None,
        status="idiomatic" if dep_translated else "pending",
        attempts=0,
        divergences=[],
    )
    return state


def _captured_prompt(state, monkeypatch) -> str:
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return CANNED

    monkeypatch.setattr(client, "complete", fake_complete)
    translator.run(state)
    return captured["user"]


def test_translated_dependency_is_passed_as_target_code(tmp_path, monkeypatch):
    prompt = _captured_prompt(_state_with_dep(tmp_path, dep_translated=True), monkeypatch)
    assert "Already-translated dependency interfaces:" in prompt
    assert "export function slug" in prompt
    assert "not yet translated" not in prompt


def test_a_cycle_dependency_falls_back_to_its_source(tmp_path, monkeypatch):
    """The whole point: a module translated before its dependency exists used
    to be told nothing about it, and would call a function it never imported."""
    prompt = _captured_prompt(_state_with_dep(tmp_path, dep_translated=False), monkeypatch)
    assert "Circular imports:" in prompt
    assert "not yet translated" in prompt
    assert "def slug(text):" in prompt                 # the source, so names are known
    assert "do not call into it without an import" in prompt
    # It must not be presented as already-translated target code.
    assert "Already-translated dependency interfaces:" not in prompt


def test_no_dependency_sections_when_there_are_no_dependencies(tmp_path, monkeypatch):
    prompt = _captured_prompt(_state(tmp_path), monkeypatch)
    assert "Already-translated dependency interfaces:" not in prompt
    assert "Circular imports:" not in prompt


# ------------------------------------------------- language-pair trip-wires

def test_pitfalls_sheet_is_appended_to_the_system_prompt(tmp_path, monkeypatch):
    """Supplied up front, not as retry feedback: these bugs compile cleanly, so
    the model cannot infer them from a diagnostic it has not been given yet."""
    captured = _capture(monkeypatch)
    translator.run(_state(tmp_path))

    system = captured["system"]
    assert "trip-wires" in system
    assert "Math.floor(a / b)" in system          # floor division, not trunc
    assert "(a, b) => a - b" in system            # JS sorts lexicographically


def test_pitfalls_sheet_covers_the_split_divergence_seen_in_practice(tmp_path, monkeypatch):
    """The regression this sheet was written for: `text.lower().split()` became
    `split(/\\s+/)`, which misses \\x1c-\\x1f and \\x85 and burned all 3 retries."""
    captured = _capture(monkeypatch)
    translator.run(_state(tmp_path))

    system = captured["system"]
    assert "\\x1c-\\x1f" in system
    assert ".filter(Boolean)" in system


def test_missing_pitfalls_sheet_degrades_to_the_base_prompt():
    """A pair with no sheet must yield "" rather than raise, so the translator
    falls back to the base prompt instead of failing the run."""
    assert client.load_prompt("pitfalls/python-rust", optional=True) == ""
    assert client.load_prompt("pitfalls/python-typescript", optional=True) != ""

    with pytest.raises(FileNotFoundError):
        client.load_prompt("pitfalls/python-rust")      # still strict by default


def test_pitfalls_file_is_plain_ascii():
    """It documents whitespace characters. If they are stored *as* those
    characters the sheet is unreadable and the model may not reproduce them."""
    from pathlib import Path

    import codeshift.llm.client as c
    from codeshift.config import settings

    text = Path(settings.prompts_dir, "pitfalls", "python-typescript.md").read_text(
        encoding="utf-8"
    )
    assert text == c.load_prompt("pitfalls/python-typescript")
    assert all(ord(ch) <= 126 for ch in text), "prompt contains literal non-ASCII"


def test_translator_builds_symbol_map(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "complete", lambda **kwargs: CANNED)
    update = translator.run(_state(tmp_path))
    # source make_user -> TS export makeUser
    assert update["files"]["models"]["symbol_map"] == {"make_user": "makeUser"}


# ------------------------------------------------------------------- retries

BAD_ATTEMPT = 'export function slugify(text: string): string {\n    return text.split().join("-");\n}'


def _retry_state(out_dir, **overrides):
    state = _state(out_dir)
    unit = state["files"]["models"]
    unit["translated_code"] = BAD_ATTEMPT
    unit["attempts"] = 1
    unit.update(overrides)
    return state


def _capture(monkeypatch):
    captured = {}

    def fake_complete(**kwargs):
        captured.update(kwargs)
        return CANNED

    monkeypatch.setattr(client, "complete", fake_complete)
    return captured


def test_retry_prompt_includes_previous_attempt_with_line_numbers(tmp_path, monkeypatch):
    """The regression guard for the convergence bug.

    Feeding back line-numbered diagnostics without the code they refer to left
    the model regenerating from the same source, so every module burned its
    whole retry budget with identical error counts.
    """
    captured = _capture(monkeypatch)
    type_errors = [{"line": 2, "code": "TS2554", "message": "Expected 1-2 arguments, but got 0."}]
    translator.run(_retry_state(tmp_path, type_errors=type_errors))

    user = captured["user"]
    assert 'text.split().join("-")' in user      # the failing code itself
    assert "2 |" in user                          # numbered, so `line 2` resolves
    assert "TS2554" in user


def test_first_attempt_has_no_previous_code_section(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    translator.run(_state(tmp_path))
    assert "previous attempt" not in captured["user"].lower()


def test_divergences_are_deduped_to_distinct_failures(tmp_path, monkeypatch):
    """One bug yields one record per failing input; sending all of them buries
    the signal and crowds out the code under repair."""
    captured = _capture(monkeypatch)
    divergences = [
        {
            "function": "slugify",
            "args": [f"input-{i}"],
            "category": "value_mismatch",
            "detail": "source='a-b' target='a b'",
        }
        for i in range(25)
    ]
    translator.run(_retry_state(tmp_path, divergences=divergences))

    user = captured["user"]
    assert user.count("[value_mismatch]") == 1        # 25 records -> 1 failure mode
    assert "25 failing input(s) collapsed to 1" in user
    assert "'input-0'" in user                         # one concrete repro kept


def test_empty_output_is_rejected_and_not_written(tmp_path, monkeypatch):
    """An empty module passes the type gate trivially, so it has to be caught
    here — downstream it looks like a clean file with total drift."""
    monkeypatch.setattr(client, "complete", lambda **kwargs: "")

    state = _retry_state(tmp_path)
    state["files"]["models"]["translated_code"] = "export function makeUser() {}"
    update = translator.run(state)
    unit = update["files"]["models"]

    assert unit["rejected"]
    assert unit["type_errors"][0]["code"] == "CODESHIFT_EMPTY"
    assert unit["attempts"] == 2                                  # still consumes budget
    assert unit["translated_code"] == "export function makeUser() {}"  # prior kept
    assert not (tmp_path / "models.ts").exists()                  # nothing written


def test_exportless_output_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "complete", lambda **kwargs: "const helper = 1;")

    update = translator.run(_state(tmp_path))
    unit = update["files"]["models"]

    assert unit["rejected"]
    assert "exports none" in unit["rejected"]
    assert not (tmp_path / "models.ts").exists()


def test_valid_output_clears_rejection(tmp_path, monkeypatch):
    monkeypatch.setattr(client, "complete", lambda **kwargs: CANNED)

    update = translator.run(_retry_state(tmp_path, rejected="stale reason"))

    assert update["files"]["models"]["rejected"] is None


def test_distinct_divergences_are_capped(tmp_path, monkeypatch):
    captured = _capture(monkeypatch)
    divergences = [
        {
            "function": f"f{i}",
            "args": [i],
            "category": "value_mismatch",
            "detail": f"detail {i}",
        }
        for i in range(10)
    ]
    translator.run(_retry_state(tmp_path, divergences=divergences))

    user = captured["user"]
    assert user.count("[value_mismatch]") == 6         # default limit
    assert "+4 more distinct failure mode(s)" in user
