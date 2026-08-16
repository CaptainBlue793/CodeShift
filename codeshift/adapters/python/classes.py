"""Turn a Python class into calls the differential harness can actually make.

A method cannot be called without a *receiver*, so most of the work here is
about constructors: can this class be built from generated arguments, and with
which parameter types? Three shapes are recognized — an explicit `__init__`, a
dataclass (whose constructor is its annotated fields), and a plain class with
neither, which takes no arguments.

Where the answer is "no", the class is **reported unverified rather than
guessed at**. That is the whole reason this analysis is conservative: Python
raises `TypeError` when a constructor is called with the wrong arguments, while
JavaScript quietly binds the missing ones to `undefined`. A constructor we
cannot build faithfully therefore fails on one side and succeeds on the other,
and arrives as behavioral drift in a translation that is perfectly correct. A
named gap is worth more than a false accusation.

Methods are treated more leniently than constructors — `*args` is tolerated,
and the extra arguments simply go unexercised — because that is already how
top-level functions behave here, and an unexercised argument produces no
finding either way.

Everything skipped is named with a reason; see `codeshift.verification`.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Optional, Union

from codeshift.adapters.base import FuncSig, Untestable
from codeshift.adapters.python.annotations import annotation_name

#: Method decorators that put a method out of reach, and the reason slug each
#: earns. A property takes no arguments to generate, and an abstract method has
#: no body to compare.
_METHOD_SKIPS: dict[str, str] = {
    "property": "property",
    "cached_property": "property",
    "abstractproperty": "property",
    "abstractmethod": "abstract_method",
}

#: Decorators marking a method that is called on the class, not an instance.
#: `classmethod` still receives an implicit first argument; `staticmethod` does not.
_NO_RECEIVER = {"staticmethod", "classmethod"}

#: Bases that mean "this class is not meant to be instantiated directly".
_ABSTRACT_BASES = {"ABC", "ABCMeta", "Protocol"}

_DATACLASS_DECORATORS = {"dataclass", "attrs", "define"}


@dataclass
class ClassPlan:
    """What a class contributes to a module: callable signatures, and gaps."""
    signatures: list[FuncSig] = field(default_factory=list)
    skipped: list[Untestable] = field(default_factory=list)


Method = Union[ast.FunctionDef, ast.AsyncFunctionDef]


def _decorator_names(node: ast.ClassDef | Method) -> set[str]:
    """Bare decorator names, `@dataclass` and `@dataclasses.dataclass` alike."""
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Attribute):
            names.add(target.attr)
        elif isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _base_names(cls: ast.ClassDef) -> set[str]:
    names: set[str] = set()
    for base in cls.bases:
        if isinstance(base, ast.Attribute):
            names.add(base.attr)
        elif isinstance(base, ast.Name):
            names.add(base.id)
    return names


def _positional(fn: Method, *, drop_first: bool) -> list[ast.arg]:
    args = list(fn.args.posonlyargs) + list(fn.args.args)
    return args[1:] if drop_first and args else args


def _is_classvar(ann: Optional[ast.expr]) -> bool:
    return annotation_name(ann).replace("typing.", "").startswith("ClassVar")


def _is_init_false(value: Optional[ast.expr]) -> bool:
    """True for `x: int = field(init=False)` — a field the constructor refuses.

    `dataclasses` leaves such a field out of `__init__` entirely, so passing one
    is a `TypeError` on the Python side while the target language would bind the
    extra argument harmlessly. Every call would then fail on one side only.
    """
    if not isinstance(value, ast.Call):
        return False
    func = value.func
    name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
    if name != "field":
        return False
    return any(
        kw.arg == "init" and isinstance(kw.value, ast.Constant) and kw.value.value is False
        for kw in value.keywords
    )


def _dataclass_fields(cls: ast.ClassDef) -> list[tuple[str, str]]:
    """Annotated class-level (name, type) fields — a dataclass's constructor.

    `ClassVar` is excluded because `dataclasses` excludes it too, and so is
    `field(init=False)`. Fields with ordinary defaults are kept and passed
    positionally: exercising a default is a job for the source's own tests, not
    for a translation check.
    """
    fields: list[tuple[str, str]] = []
    for node in cls.body:
        if not isinstance(node, ast.AnnAssign) or _is_classvar(node.annotation):
            continue
        if _is_init_false(node.value):
            continue
        if isinstance(node.target, ast.Name):
            fields.append((node.target.id, annotation_name(node.annotation)))
    return fields


def requires_keyword_only(fn: Method) -> bool:
    """True if `fn` has a keyword-only parameter with no default.

    The harness only ever passes positional arguments, so such a parameter can
    never be supplied: Python raises `TypeError` on every call while the target
    language binds the missing argument to `undefined` and runs. That asymmetry
    reads as behavioral drift in a translation that is perfectly correct, which
    is the same reason `constructor()` refuses the equivalent shape. `*args` is
    tolerated by contrast because unpassed extras simply go unexercised.
    """
    return any(default is None for default in fn.args.kw_defaults)


def constructor(cls: ast.ClassDef) -> tuple[list[str], Optional[str]]:
    """Return (constructor parameter types, reason it cannot be built).

    Exactly one side is meaningful: a reason means the parameter list is empty
    and unusable, not that the class takes no arguments.
    """
    if _ABSTRACT_BASES & (_base_names(cls) | _decorator_names(cls)):
        return [], "abstract_class"

    init = next(
        (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"),
        None,
    )
    if init is not None:
        if init.args.vararg or init.args.kwarg:
            return [], "variadic_constructor"
        # A keyword-only parameter without a default cannot be supplied
        # positionally, and omitting it would fail on one side only.
        if requires_keyword_only(init):
            return [], "keyword_only_constructor"
        return [annotation_name(a.annotation) for a in _positional(init, drop_first=True)], None

    if _decorator_names(cls) & _DATACLASS_DECORATORS:
        # A dataclass's constructor is its fields *and every base's fields,
        # first*. Only this class's own body is in view here, so a subclass
        # would claim too few arguments — `@dataclass class Taxed(Item)` looks
        # like a one-argument constructor when the real one takes three.
        if _base_names(cls) - {"object"}:
            return [], "inherited_constructor"
        return [type_name for _, type_name in _dataclass_fields(cls)], None

    # No constructor of its own. That means "takes no arguments" only if there is
    # no base class to have inherited one from.
    if _base_names(cls) - {"object"}:
        return [], "inherited_constructor"
    return [], None


def _method_signature(
    cls_name: str, fn: Method, ctor_params: list[str], blocked: Optional[str]
) -> Union[FuncSig, Untestable]:
    """One method's testable signature, or the reason it has none."""
    qualified = f"{cls_name}.{fn.name}"
    decorators = _decorator_names(fn)

    skip = next((_METHOD_SKIPS[d] for d in decorators if d in _METHOD_SKIPS), None)
    if skip:
        return Untestable(name=qualified, reason=skip)
    if isinstance(fn, ast.AsyncFunctionDef):
        return Untestable(name=qualified, reason="async_method")
    # Private and dunder methods are implementation detail: the translation is
    # free to spell them differently or inline them away, so comparing them
    # would report style as drift.
    if fn.name.startswith("_"):
        return Untestable(name=qualified, reason="private_method")
    if requires_keyword_only(fn):
        return Untestable(name=qualified, reason="keyword_only_method")

    returns = annotation_name(fn.returns)
    if decorators & _NO_RECEIVER:
        # `classmethod` is called on the class but still declares `cls`.
        drop_first = "classmethod" in decorators
        return FuncSig(
            name=qualified,
            params=[annotation_name(a.annotation) for a in _positional(fn, drop_first=drop_first)],
            returns=returns,
            kind="static_method",
        )

    if blocked is not None:
        return Untestable(name=qualified, reason=blocked)

    return FuncSig(
        name=qualified,
        params=[annotation_name(a.annotation) for a in _positional(fn, drop_first=True)],
        returns=returns,
        kind="method",
        ctor_params=ctor_params,
    )


def class_plan(cls: ast.ClassDef) -> ClassPlan:
    """Everything the harness can and cannot exercise on one class."""
    ctor_params, blocked = constructor(cls)
    plan = ClassPlan()

    methods = [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name != "__init__"
    ]
    for fn in methods:
        entry = _method_signature(cls.name, fn, ctor_params, blocked)
        if isinstance(entry, FuncSig):
            plan.signatures.append(entry)
        else:
            plan.skipped.append(entry)

    if any(sig.kind == "method" for sig in plan.signatures):
        return plan   # the constructor is already exercised by every method call

    if blocked is None:
        # Nothing else reaches the constructor, and building the object is
        # observable behavior in its own right — a dataclass is *only* its
        # constructor. Run it alone and compare the attributes it produces.
        plan.signatures.append(
            FuncSig(name=f"{cls.name}.__init__", params=ctor_params, kind="construction")
        )
    elif not any(entry.reason == blocked for entry in plan.skipped):
        # The class could not be built and no method has said so yet. Saying it
        # once, against the class, beats saying nothing.
        plan.skipped.append(Untestable(name=cls.name, reason=blocked))
    return plan


def method_types(cls: ast.ClassDef) -> dict[str, dict]:
    """Declared types per qualified method name, matching `class_plan` naming.

    Includes `__init__`, because `class_plan` may test construction on its own,
    and excludes the implicit first parameter, which has no counterpart in the
    target language.
    """
    out: dict[str, dict] = {}
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        drop_first = "staticmethod" not in _decorator_names(node)
        out[f"{cls.name}.{node.name}"] = {
            "params": {
                a.arg: annotation_name(a.annotation)
                for a in _positional(node, drop_first=drop_first)
            },
            "returns": annotation_name(node.returns),
        }

    # A dataclass has a constructor without declaring one, so describe it from
    # the fields — otherwise the one thing under test would go un-hinted.
    if f"{cls.name}.__init__" not in out and _decorator_names(cls) & _DATACLASS_DECORATORS:
        out[f"{cls.name}.__init__"] = {
            "params": dict(_dataclass_fields(cls)),
            "returns": "None",
        }
    return out
