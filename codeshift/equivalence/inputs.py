"""Generate test inputs for differential testing using Hypothesis strategies.

Given a function's parameter type names, produce a list of arg-lists to run
through both the original and translated implementations.

TODO: adopt a proper `@given`-based comparison harness so Hypothesis can shrink
failing inputs; for now we sample fixed-size example sets.
"""
from __future__ import annotations

import warnings
from typing import Any

from hypothesis import strategies as st
from hypothesis.errors import NonInteractiveExampleWarning

_STRATEGIES = {
    "int": lambda: st.integers(min_value=-1000, max_value=1000),
    "str": lambda: st.text(min_size=0, max_size=20),
    "float": lambda: st.floats(allow_nan=False, allow_infinity=False, width=32),
    "bool": lambda: st.booleans(),
}


def _strategy_for(type_name: str):
    factory = _STRATEGIES.get(type_name)
    if factory is not None:
        return factory()
    # Unknown/complex types: fall back to small integers as a placeholder.
    return st.integers(min_value=-100, max_value=100)


def generate_inputs(param_types: list[str], n: int = 25) -> list[list[Any]]:
    """Return `n` arg-lists matching `param_types` (a single empty call if no params)."""
    if not param_types:
        return [[]]
    strategy = st.tuples(*[_strategy_for(t) for t in param_types])
    rows: list[list[Any]] = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", NonInteractiveExampleWarning)
        for _ in range(n):
            rows.append(list(strategy.example()))
    return rows
