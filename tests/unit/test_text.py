"""Tests for text helpers: code extraction and think-block stripping."""
from codeshift.utils.text import extract_code, strip_think


def test_extract_plain_code():
    assert extract_code("export function f() {}") == "export function f() {}"


def test_extract_fenced_block():
    assert extract_code("```typescript\nexport function f() {}\n```") == "export function f() {}"


def test_extract_strips_trailing_prose_and_stray_fence():
    raw = "export function f() {}\n```\n\n// NOTE: some prose explanation here\nmore prose"
    out = extract_code(raw)
    assert out == "export function f() {}"
    assert "NOTE" not in out
    assert "```" not in out


def test_extract_unclosed_opening_fence():
    # Model opened a fence but forgot to close it — must NOT return empty.
    out = extract_code("```typescript\nexport function f() {}")
    assert out == "export function f() {}"


def test_extract_multiple_blocks():
    raw = "```ts\nimport x;\n```\nsome prose\n```ts\nexport const y = 1;\n```"
    out = extract_code(raw)
    assert "import x;" in out and "export const y = 1;" in out
    assert "prose" not in out


def test_strip_think():
    assert strip_think("<think>reasoning here</think>the answer") == "the answer"
