"""Source <-> target symbol naming helpers."""
from __future__ import annotations


def snake_to_camel(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:] if p)


def _map_name(name: str, exports: set[str]) -> str:
    """Match one name against the target's exports, or guess camelCase."""
    camel = snake_to_camel(name)
    if camel in exports:
        return camel
    if name in exports:
        return name
    return camel


def build_symbol_map(source_names: list[str], target_exports: list[str]) -> dict[str, str]:
    """Map each source callable name to the target's name for it.

    Prefers a camelCase match, then an exact match, else a best-effort camelCase
    guess (so a genuinely-missing export surfaces as a run error, not silence).

    Qualified names (`Cart.add_item`) are mapped one segment at a time: the class
    is matched against the exports, where it appears, and the method is only ever
    guessed — a method name is not an export, so there is nothing to match it
    against. The runtime drivers therefore accept either spelling of a method
    rather than trusting this guess. Dunder names (`__init__`, the harness's
    "construct only" marker) are passed through untouched, since camelCasing one
    would produce a name nothing answers to.
    """
    exports = set(target_exports)
    mapping: dict[str, str] = {}
    for name in source_names:
        owner, dot, member = name.rpartition(".")
        if not dot:
            mapping[name] = _map_name(name, exports)
            continue
        target_member = member if member.startswith("__") else snake_to_camel(member)
        mapping[name] = f"{_map_name(owner, exports)}.{target_member}"
    return mapping
