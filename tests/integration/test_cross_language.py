"""Live cross-language equivalence tests (Python source vs real TypeScript).

Executes the TypeScript side via `npx tsx`, so these are skipped automatically
when a Node toolchain is unavailable. They spend no API tokens — the "translated"
TypeScript is hand-written here to drive the equivalence engine directly.
"""
import shutil

import pytest

from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.adapters.typescript.emitter import TypeScriptTargetAdapter
from codeshift.equivalence.harness import check_equivalence
from codeshift.utils.naming import build_symbol_map

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or shutil.which("npx") is None,
    reason="Node toolchain (node/npx) not available",
)

ADD_PY = "def add(a: int, b: int) -> int:\n    return a + b\n"


def _dirs(tmp_path, ts_body):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "calc.py").write_text(ADD_PY, encoding="utf-8")
    (out / "calc.ts").write_text(ts_body, encoding="utf-8")
    return str(src), str(out)


def _check(src, out, module="calc", src_code=ADD_PY, target_names=None, inputs_by_func=None):
    sa = PythonSourceAdapter()
    ta = TypeScriptTargetAdapter(output_root=out)
    sigs = sa.signatures(src_code)
    divergences, unverifiable, _ = check_equivalence(
        source_adapter=sa,
        source_root=src,
        target_adapter=ta,
        target_root=out,
        module=module,
        signatures=sigs,
        target_names=target_names,
        inputs_by_func=inputs_by_func,
        n=12,
    )
    return divergences, unverifiable


def test_correct_translation_has_no_divergence(tmp_path):
    src, out = _dirs(tmp_path, "export function add(a: number, b: number): number { return a + b; }\n")
    divergences, unverifiable = _check(src, out)
    assert unverifiable == []
    assert divergences == []


def test_buggy_translation_is_detected(tmp_path):
    src, out = _dirs(tmp_path, "export function add(a: number, b: number): number { return a - b; }\n")
    divergences, unverifiable = _check(src, out)
    assert unverifiable == []
    assert divergences
    assert all(d["category"] == "value_mismatch" for d in divergences)


CART_PY = (
    "class Cart:\n"
    "    def __init__(self, owner: str) -> None:\n"
    "        self.owner = owner\n"
    "        self.items: list[str] = []\n"
    "\n"
    "    def add(self, item: str) -> int:\n"
    "        self.items.append(item.strip().lower())\n"
    "        return len(self.items)\n"
)


def _cart_dirs(tmp_path, ts_body):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "cart.py").write_text(CART_PY, encoding="utf-8")
    (out / "cart.ts").write_text(ts_body, encoding="utf-8")
    return str(src), str(out)


#: Fixed inputs, so "the sabotaged version diverges" cannot depend on a random
#: string happening to survive `strip().lower()` unchanged.
CART_INPUTS = {
    "Cart.add": {"args": [["  Widget "], ["MIXED Case"]], "ctor": [["ada"], ["ada"]]},
}


def test_a_class_is_constructed_and_called_across_languages(tmp_path):
    """Real `new Cart(...)` in Node, compared against real Python."""
    src, out = _cart_dirs(
        tmp_path,
        "export class Cart {\n"
        "  owner: string;\n"
        "  items: string[] = [];\n"
        "  constructor(owner: string) { this.owner = owner; }\n"
        "  add(item: string): number {\n"
        "    this.items.push(item.trim().toLowerCase());\n"
        "    return this.items.length;\n"
        "  }\n"
        "}\n",
    )
    divergences, unverifiable = _check(
        src, out, module="cart", src_code=CART_PY,
        target_names={"Cart.add": "Cart.add"}, inputs_by_func=CART_INPUTS,
    )
    assert unverifiable == []
    assert divergences == []


def test_a_class_that_stores_the_wrong_thing_diverges_across_languages(tmp_path):
    """`add` returns the right count either way; only the stored value differs,
    so nothing but the receiver's state can catch it."""
    src, out = _cart_dirs(
        tmp_path,
        "export class Cart {\n"
        "  owner: string;\n"
        "  items: string[] = [];\n"
        "  constructor(owner: string) { this.owner = owner; }\n"
        "  add(item: string): number {\n"
        "    this.items.push(item);\n"          # forgot trim().toLowerCase()
        "    return this.items.length;\n"
        "  }\n"
        "}\n",
    )
    divergences, _ = _check(
        src, out, module="cart", src_code=CART_PY,
        target_names={"Cart.add": "Cart.add"}, inputs_by_func=CART_INPUTS,
    )
    assert divergences
    assert all(d["category"] == "state_mismatch" for d in divergences)


# --- values JSON cannot round-trip on its own -----------------------------
# A Python `set` has no JSON encoding and used to fall back to `str()`, giving
# a repr like "{'a', 'b'}". `JSON.stringify(new Set())` gives `{}` — the
# contents disappear entirely, so a *wrong* set compared equal to a right one.
# Both drivers now emit a tagged, sorted array.

TAGS_PY = (
    "class Tags:\n"
    "    def __init__(self, owner: str) -> None:\n"
    "        self.owner = owner\n"
    "        self.seen: set[str] = set()\n"
    "\n"
    "    def add(self, tag: str) -> int:\n"
    "        self.seen.add(tag.strip().lower())\n"
    "        return len(self.seen)\n"
)

TAGS_INPUTS = {
    "Tags.add": {"args": [["  Alpha "], ["BETA"], ["alpha"]],
                 "ctor": [["ada"], ["ada"], ["ada"]]},
}


def _tags_dirs(tmp_path, ts_body):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "tags.py").write_text(TAGS_PY, encoding="utf-8")
    (out / "tags.ts").write_text(ts_body, encoding="utf-8")
    return str(src), str(out)


_TAGS_TS = (
    "export class Tags {\n"
    "  owner: string;\n"
    "  seen: Set<string> = new Set();\n"
    "  constructor(owner: string) { this.owner = owner; }\n"
    "  add(tag: string): number {\n"
    "    this.seen.add(tag{MUTATION});\n"
    "    return this.seen.size;\n"
    "  }\n"
    "}\n"
)


def test_a_set_survives_the_round_trip_across_languages(tmp_path):
    """A faithful `Set` translation must compare equal to a Python `set`."""
    src, out = _tags_dirs(tmp_path, _TAGS_TS.replace("{MUTATION}", ".trim().toLowerCase()"))
    divergences, unverifiable = _check(
        src, out, module="tags", src_code=TAGS_PY,
        target_names={"Tags.add": "Tags.add"}, inputs_by_func=TAGS_INPUTS,
    )
    assert unverifiable == []
    assert divergences == []


def test_a_set_holding_the_wrong_contents_is_caught(tmp_path):
    """The regression that matters: `JSON.stringify(new Set())` is `{}`, so
    before normalization this passed while storing entirely wrong values."""
    src, out = _tags_dirs(tmp_path, _TAGS_TS.replace("{MUTATION}", ""))  # no trim/lower
    divergences, _ = _check(
        src, out, module="tags", src_code=TAGS_PY,
        target_names={"Tags.add": "Tags.add"}, inputs_by_func=TAGS_INPUTS,
    )
    assert divergences
    assert all(d["category"] == "state_mismatch" for d in divergences)


USER_PY = (
    "from dataclasses import dataclass\n"
    "\n"
    "\n"
    "@dataclass\n"
    "class User:\n"
    "    user_id: int\n"
    "    name: str\n"
)


def test_a_dataclass_is_verified_by_construction_alone(tmp_path):
    """No methods to call, so building it *is* the behavior — and the fields it
    ends up holding are the only evidence there is."""
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "models.py").write_text(USER_PY, encoding="utf-8")
    (out / "models.ts").write_text(
        "export class User {\n"
        "  userId: number;\n"                  # renamed to TS conventions: fine
        "  name: string;\n"
        "  constructor(userId: number, name: string) {\n"
        "    this.userId = userId;\n"
        "    this.name = name;\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    divergences, unverifiable = _check(
        str(src), str(out), module="models", src_code=USER_PY,
        target_names={"User.__init__": "User.__init__"},
    )
    assert unverifiable == []
    assert divergences == []


def test_a_dataclass_that_stores_the_wrong_field_is_caught(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    (src / "models.py").write_text(USER_PY, encoding="utf-8")
    (out / "models.ts").write_text(
        "export class User {\n"
        "  userId: number;\n"
        "  name: string;\n"
        "  constructor(userId: number, name: string) {\n"
        "    this.userId = userId;\n"
        "    this.name = name.trim();\n"       # the source stores it verbatim
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    divergences, _ = _check(
        str(src), str(out), module="models", src_code=USER_PY,
        target_names={"User.__init__": "User.__init__"},
        inputs_by_func={"User.__init__": {"args": [[1, "  Ada  "]], "ctor": None}},
    )
    assert divergences
    assert all(d["category"] == "state_mismatch" for d in divergences)


def test_symbol_map_bridges_camelcase_names(tmp_path):
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    out.mkdir()
    src_code = "def make_user(user_id: int, name: str) -> dict:\n    return {'id': user_id, 'name': name}\n"
    (src / "models.py").write_text(src_code, encoding="utf-8")
    (out / "models.ts").write_text(
        "export function makeUser(userId: number, name: string) "
        "{ return { id: userId, name }; }\n",
        encoding="utf-8",
    )

    ta = TypeScriptTargetAdapter(output_root=str(out))
    sa = PythonSourceAdapter()
    sigs = sa.signatures(src_code)
    symbol_map = build_symbol_map([s.name for s in sigs], ta.exports((out / "models.ts").read_text(encoding="utf-8")))
    assert symbol_map == {"make_user": "makeUser"}

    divergences, unverifiable = _check(
        str(src), str(out), module="models", src_code=src_code, target_names=symbol_map
    )
    assert unverifiable == []
    assert divergences == []
