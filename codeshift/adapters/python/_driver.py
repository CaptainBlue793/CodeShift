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
import importlib
import json
import os
import sys


def _state(obj):
    """The receiver's attributes after a call, as a plain dict.

    Callable attributes are dropped: the target language stores methods on the
    instance in some styles and on the prototype in others, and neither is
    behavior worth comparing.
    """
    try:
        attrs = dict(vars(obj))
    except TypeError:
        # __slots__ (and builtins) have no __dict__; read the declared names.
        slots = getattr(type(obj), "__slots__", ()) or ()
        if isinstance(slots, str):
            slots = (slots,)
        attrs = {name: getattr(obj, name) for name in slots if hasattr(obj, name)}
    return {name: value for name, value in attrs.items() if not callable(value)}


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
        row = {"ok": True, "value": value}
        if state is not None:
            row["state"] = state
        results.append(row)

    json.dump(results, sys.stdout, default=str)


if __name__ == "__main__":
    main()
