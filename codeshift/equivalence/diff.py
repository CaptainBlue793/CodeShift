"""Compare original vs translated call outcomes and classify divergences."""
from __future__ import annotations

from typing import Any, Callable, Optional

from codeshift.adapters.base import CallOutcome


def _equal(a: Any, b: Any) -> bool:
    # TODO: float tolerance and structural normalization for nested containers.
    return a == b


def _fields(state: dict) -> dict:
    """An object's attributes, keyed so that only *values* can differ.

    `total_items`, `totalItems` and `_totalItems` are the same field wearing the
    target language's naming conventions, and the idiom pass is expected to
    change that spelling. Renaming a field is a translation choice; changing
    what it holds is drift, and only the second one belongs in a report.

    Attributes that collapse onto the *same* normalized key are kept verbatim
    instead. `self._celsius` beside `self.celsius` — a property and its backing
    field, which is ordinary Python — would otherwise merge into one entry and
    one of the two values would vanish, taking any difference in it along. A
    spelling change wrongly reported beats a value change silently dropped.

    Return values are compared verbatim — a dict returned from a function is
    data, and its keys are part of the answer.
    """
    by_slug: dict[str, list[str]] = {}
    for key in state:
        by_slug.setdefault(key.replace("_", "").lower(), []).append(key)

    out: dict = {}
    for slug, keys in by_slug.items():
        if len(keys) == 1:
            out[slug] = state[keys[0]]
        else:
            out.update({key: state[key] for key in keys})
    return out


# A value that fits on one line is printed whole; past this it is described
# instead. 120 characters is the same budget `_render_args` gives an input.
_INLINE_LIMIT = 120

# Characters of context kept either side of the first disagreement.
_WINDOW = 24


def _first_difference(a: str, b: str) -> int:
    """Index of the first differing character, or the length of the shorter
    string when one is a prefix of the other."""
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))


def _clip(text: str) -> str:
    return text if len(text) <= _INLINE_LIMIT else text[: _INLINE_LIMIT - 3] + "..."


def _window(text: str, at: int) -> str:
    """`text` around index `at`, marked where it was cut."""
    start, end = max(0, at - _WINDOW), min(len(text), at + _WINDOW)
    return (
        ("..." if start > 0 else "")
        + repr(text[start:end])
        + ("..." if end < len(text) else "")
    )


def describe_values(source: Any, target: Any) -> str:
    """Spell the difference between two values as briefly as it can be spelled.

    Two 600-character strings differing by one trailing space are, printed in
    full, 1,200 characters that say nothing: the reader has to diff them by eye,
    and the model reading them back in a retry prompt does not. That is why the
    modules whose bug was padding never converged on the 31-module run - the
    feedback contained the answer and buried it.

    Long values are therefore reduced to the three facts that locate the fault:
    each side's length, the index they first disagree at, and a window of text
    around that index. Short values are still printed whole, because for those
    the value *is* the diagnosis - `source=24 target=28` is how the `len()`
    trip-wire announces itself, and describing it would destroy it.
    """
    source_repr, target_repr = repr(source), repr(target)
    if len(source_repr) <= _INLINE_LIMIT and len(target_repr) <= _INLINE_LIMIT:
        return f"source={source_repr} target={target_repr}"

    if isinstance(source, str) and isinstance(target, str):
        at = _first_difference(source, target)
        head = f"source len={len(source)} target len={len(target)}"

        # One string is a prefix of the other: the difference is not *at* an
        # index, it is everything past the shorter one's end, and windowing
        # both sides would show two near-identical runs of the same padding
        # character. Name the extra text instead - it is the whole finding.
        if at == min(len(source), len(target)):
            longer, side = (
                (target, "target") if len(target) > len(source) else (source, "source")
            )
            extra = longer[at:]
            return f"{head}; identical up to index {at}, then {side} has {_clip(repr(extra))}"

        return (
            f"{head}, first differs at index {at}: "
            f"source={_window(source, at)} target={_window(target, at)}"
        )

    return f"source={_clip(source_repr)} target={_clip(target_repr)}"


def render_call(record: dict, format_args: Callable[[Optional[list]], str]) -> str:
    """Spell a divergence as the call that produced it.

    A method's arguments do not identify the call on their own — the receiver
    does too — so a record carrying constructor args renders as
    `new Cart(2).add_item(x)`. Lives here, next to the record shape, because the
    retry prompt and the report both have to describe the same failing call;
    they differ only in how much of the arguments they can afford to print,
    which is what `format_args` decides.
    """
    func = record.get("function") or "?"
    args = format_args(record.get("args"))
    owner, _, member = func.rpartition(".")
    ctor = record.get("ctor")

    if ctor is not None:
        return f"new {owner}({format_args(ctor)}).{member}({args})"
    if member == "__init__" and owner:
        return f"new {owner}({args})"
    return f"{func}({args})"


def divergence_key(record: dict) -> tuple:
    """Identity of a *failure mode*, deliberately excluding the inputs.

    The harness emits one record per failing input, so a single bug arrives as
    dozens of records differing only in `args`. Everything that reasons about
    "how many things are wrong" — prompt feedback, attempt scoring — has to
    agree on this, or a module looks worse simply for being tested harder.
    """
    return (record.get("function"), record.get("category"), record.get("detail"))


def distinct_divergences(divergences: list[dict]) -> list[dict]:
    """First record per distinct failure mode, input order preserved."""
    seen: set[tuple] = set()
    out: list[dict] = []
    for record in divergences:
        key = divergence_key(record)
        if key in seen:
            continue
        seen.add(key)
        out.append(record)
    return out


def classify_divergence(
    func: str,
    args: list,
    source: CallOutcome,
    target: CallOutcome,
    ctor: Optional[list] = None,
) -> Optional[dict]:
    """Return a divergence record, or None if the two outcomes are equivalent.

    `ctor` is the receiver's constructor arguments, carried into the record so a
    method failure is reproducible: the args alone do not identify the call.
    """
    def record(category: str, detail: str) -> dict:
        entry = {"function": func, "args": args, "category": category, "detail": detail}
        if ctor is not None:
            entry["ctor"] = ctor
        return entry

    if source.ok != target.ok:
        return record(
            "exception_behavior",
            f"source ok={source.ok}, target ok={target.ok} "
            f"(source_error={source.error}, target_error={target.error})",
        )

    if not source.ok:  # both raised
        if source.error != target.error:
            return record(
                "exception_behavior",
                f"source raised {source.error}, target raised {target.error}",
            )
        return None

    if not _equal(source.value, target.value):  # both returned
        return record("value_mismatch", describe_values(source.value, target.value))

    # A method that mutates its receiver and returns nothing has no other
    # evidence: without this, `None == undefined` would pass it unexamined.
    if source.state is None and target.state is None:
        return None
    if source.state is None or target.state is None:
        return record(
            "state_mismatch",
            f"one side exposed no object state (source={source.state!r} "
            f"target={target.state!r})",
        )
    if not _equal(_fields(source.state), _fields(target.state)):
        return record(
            "state_mismatch",
            "object state after the call: "
            + describe_values(source.state, target.state),
        )
    return None
