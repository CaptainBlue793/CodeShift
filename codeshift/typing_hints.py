"""Build target-language type hints from source types.

Neutral helper shared by the translator (to type the first-pass translation) and
the type-inference agent (to record inferred types). Stays language-agnostic by
going through the source/target adapter interfaces.
"""
from __future__ import annotations

from codeshift.adapters.base import SourceAdapter, TargetAdapter


def build_type_hints(
    source_adapter: SourceAdapter,
    target_adapter: TargetAdapter,
    source_code: str,
    *,
    root: str | None = None,
    module: str | None = None,
) -> dict:
    """Return {func: {"params": {name: target_type}, "returns": target_type}}.

    `root`/`module` are passed through to the source type oracle; omit them to
    map declared annotations only.
    """
    source_types = source_adapter.infer_types(source_code, root=root, module=module)
    return map_types(target_adapter, source_types)


def map_types(target_adapter: TargetAdapter, source_types: dict) -> dict:
    """Map already-extracted source types into the target type system.

    Separate from `build_type_hints` so a caller that already ran the source
    oracle does not pay for a second run.
    """
    hints: dict[str, dict] = {}
    for func, info in source_types.items():
        hints[func] = {
            "params": {n: target_adapter.map_type(t) for n, t in info["params"].items()},
            "returns": target_adapter.map_type(info["returns"]),
        }
    return hints


def render_hints(hints: dict) -> str:
    """Render hints as a readable signature list for a prompt."""
    lines = []
    for func, info in hints.items():
        params = ", ".join(f"{n}: {t}" for n, t in info["params"].items())
        lines.append(f"- {func}({params}) -> {info['returns']}")
    return "\n".join(lines)
