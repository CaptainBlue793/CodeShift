"""Subprocess driver: import a module and exercise one callable over many inputs.

Invoked as:  python _driver.py <root> <module> <target>   (payload as JSON on stdin)

`<target>` is a module-level function (`slugify`), a qualified method
(`Cart.add_item`), or `Cart.__init__`, which means "construct only" — for
classes whose observable behavior is the constructor.

Payload: `{"inputs": [[...], ...], "ctor": [[...], ...] | null}`. `ctor` holds
one constructor arg-list per input, so every call gets a *fresh* receiver and no
state leaks from one input to the next. A bare list is accepted as `inputs` with
no constructor.

Emits a JSON list of `{"ok": bool, "value"|"error": ..., "state": {...}}`.
`state` is the receiver's attributes after the call: a mutating method that
returns nothing has no other evidence to compare, and comparing its `None`
against JavaScript's `undefined` would pass without testing anything.
"""
import datetime
import importlib
import json
import os
import sys


def _canon(value):
    """A total order for values that are not mutually comparable.

    Compact separators on purpose: the TypeScript driver sorts by
    `JSON.stringify`, which emits no spaces, and the two orderings have to agree
    or the same set comes out differently on each side.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _attributes(obj):
    """`obj`'s instance attributes, or None if it is not that kind of value.

    None and `{}` mean different things to the caller: `{}` is an object that
    happens to hold nothing, None is "read this some other way". Three kinds of
    value are deliberately refused:

    * **Classes themselves.** `vars(SomeClass)` is the class body -- methods,
      `__module__`, the lot -- and none of it is the value that was passed.
    * **Empty `__slots__`.** `pathlib.Path` declares `__slots__ = ()`, so
      treating "declares slots" as "is an inspectable object" would render a
      path as `{}` and lose it. Nothing to read means nothing to read.
    * **Anything with neither.** `Decimal`, `bytes` and the builtins land here
      and keep the `str()` fallback they have always had.
    """
    if isinstance(obj, type):
        return None
    try:
        return dict(vars(obj))
    except TypeError:
        # __slots__ (and builtins) have no __dict__; read the declared names.
        slots = getattr(type(obj), "__slots__", None) or ()
        if isinstance(slots, str):
            slots = (slots,)
        if not slots:
            return None
        return {name: getattr(obj, name) for name in slots if hasattr(obj, name)}


def _entered(value, seen):
    """`seen` plus `value`, or None if `value` is already being normalized.

    Everything that recurses can loop: a ledger holding a book that points back
    at the ledger is ordinary object graph, and a list containing itself is
    legal Python. Following either forever raises RecursionError from *outside*
    the per-input try in `main()`, which loses the whole module's results rather
    than one call's.

    The returned set is a copy, never a mutation. The same object appearing
    twice side by side in one container is not a cycle, and tagging the second
    one would report drift against a translation that merely held two of them.
    """
    seen = frozenset() if seen is None else seen
    if id(value) in seen:
        return None
    return seen | {id(value)}


def _normalize(value, _seen=None):
    """Put a value into a form the other language can produce exactly.

    `json.dumps` has no encoding for a `set` and falls back to `str()`, which
    yields `"{'a', 'b'}"` — a repr whose element order is not even stable
    between runs. JavaScript's `JSON.stringify` renders a `Set` as `{}`, which
    is worse: the contents disappear, so a *wrong* set compares equal to a
    right one. Both sides therefore emit a tagged, sorted array instead.

    The tag matters. Untagged, a Python `set` and a plain array would compare
    equal, and they are not the same thing — an array keeps duplicates and an
    order. Reporting that as drift is the safe direction to be wrong in.

    Datetimes become epoch milliseconds, which is the one representation both
    languages can produce without argument. **A naive datetime is read as
    UTC** — Python's carries no zone and JavaScript's `Date` is always an
    instant, so some assumption is unavoidable; this one is at least stated.

    An ordinary object becomes its attributes. JavaScript has no choice about
    this — a class instance *is* a bag of properties, and `Object.entries`
    walks into it — so the TypeScript driver was already comparing a nested
    object field by field while this side handed `json.dumps` something it had
    no encoding for and got `<posting.ledger.Ledger object at 0x7f...>` back.
    That can never match: not a wrong answer the translator could fix, and not
    even the same string twice, since the address moves every run. On the
    31-module scale run every divergence reported for `app.engine` was this.

    Untagged, matching the TypeScript side: a translation that turns a Python
    object into a plain object is doing its job, and the two must compare equal.
    """
    # datetime is a subclass of date, so it has to be tested first.
    if isinstance(value, datetime.datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
        return {"__datetime__": int(moment.timestamp() * 1000)}
    if isinstance(value, datetime.date):
        moment = datetime.datetime(
            value.year, value.month, value.day, tzinfo=datetime.timezone.utc
        )
        return {"__datetime__": int(moment.timestamp() * 1000)}

    if not isinstance(value, (set, frozenset, dict, list, tuple)):
        attributes = _attributes(value)
        if attributes is None:
            return value
        seen = _entered(value, _seen)
        if seen is None:
            return {"__cycle__": True}
        return {
            name: _normalize(attribute, seen)
            for name, attribute in attributes.items()
            if not callable(attribute)
        }

    seen = _entered(value, _seen)
    if seen is None:
        return {"__cycle__": True}
    if isinstance(value, (set, frozenset)):
        return {"__set__": sorted((_normalize(v, seen) for v in value), key=_canon)}
    if isinstance(value, dict):
        return {key: _normalize(v, seen) for key, v in value.items()}
    return [_normalize(v, seen) for v in value]


def _state(obj):
    """The receiver's attributes after a call, as a plain dict.

    Callable attributes are dropped: the target language stores methods on the
    instance in some styles and on the prototype in others, and neither is
    behavior worth comparing.
    """
    # The receiver is known to be an object, so "nothing readable" is an empty
    # state rather than a value to render some other way.
    attrs = _attributes(obj) or {}
    return {
        name: _normalize(value)
        for name, value in attrs.items()
        if not callable(value)
    }


def _resolver(module, target):
    """Resolve `target` to a callable f(args, ctor_args) -> (value, state).

    Resolution happens once, before the loop, so a symbol the translation never
    emitted fails the whole run as one honest error rather than arriving as N
    identical AttributeErrors that read like behavioral drift.
    """
    owner, _, member = target.rpartition(".")
    if not owner:
        fn = getattr(module, member)
        return lambda args, ctor_args: (fn(*args), None)

    cls = getattr(module, owner)
    if member == "__init__":                     # construction is the behavior
        return lambda args, ctor_args: (None, _state(cls(*args)))

    getattr(cls, member)                         # fail now, not once per input

    def call(args, ctor_args):
        if ctor_args is None:                    # static/class method: no receiver
            return getattr(cls, member)(*args), None
        obj = cls(*ctor_args)
        return getattr(obj, member)(*args), _state(obj)

    return call


def main() -> None:
    root, module_name, target = sys.argv[1], sys.argv[2], sys.argv[3]
    sys.path.insert(0, os.path.abspath(root))

    payload = json.load(sys.stdin)
    if isinstance(payload, list):
        payload = {"inputs": payload, "ctor": None}
    inputs = payload.get("inputs") or []
    ctor = payload.get("ctor")

    module = importlib.import_module(module_name)
    call = _resolver(module, target)

    results = []
    for i, args in enumerate(inputs):
        ctor_args = ctor[i] if ctor is not None and i < len(ctor) else None
        try:
            value, state = call(args, ctor_args)
        except Exception as exc:  # report any error type, don't crash the driver
            results.append({"ok": False, "error": type(exc).__name__})
            continue
        # Return values need the same treatment as state: a function that
        # returns a set hits the identical encoding gap.
        row = {"ok": True, "value": _normalize(value)}
        if state is not None:
            row["state"] = state
        results.append(row)

    json.dump(results, sys.stdout, default=str)


if __name__ == "__main__":
    main()
