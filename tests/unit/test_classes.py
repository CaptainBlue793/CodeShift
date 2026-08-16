"""Tests for class support: which members are reachable, and how they are called.

Two halves. The first is the static question — can a receiver be built, and
which methods can be called on it. The second actually runs a class through the
differential harness, Python against Python, so "we support classes" means code
was executed and compared rather than merely parsed.
"""
import shutil
from pathlib import Path

from codeshift.adapters.base import CallOutcome
from codeshift.adapters.python.parser import PythonSourceAdapter
from codeshift.equivalence.diff import classify_divergence, render_call
from codeshift.equivalence.harness import check_equivalence, plan_inputs

FIXTURE = str(Path(__file__).resolve().parents[1] / "fixtures" / "class_app")


def _sigs(src: str):
    return {s.name: s for s in PythonSourceAdapter().signatures(src)}


def _skipped(src: str):
    return [(u.name, u.reason) for u in PythonSourceAdapter().untestable(src)]


# --- building a receiver ---

def test_explicit_init_gives_the_methods_their_constructor():
    src = (
        "class Cart:\n"
        "    def __init__(self, owner: str, limit: int) -> None:\n"
        "        self.owner = owner\n"
        "    def add(self, item: str) -> int:\n"
        "        return 1\n"
    )
    sig = _sigs(src)["Cart.add"]
    assert sig.kind == "method"
    assert sig.params == ["str"]              # `self` is not an argument
    assert sig.ctor_params == ["str", "int"]
    assert sig.owner == "Cart"


def test_dataclass_constructor_comes_from_its_fields():
    src = (
        "@dataclass\n"
        "class User:\n"
        "    user_id: int\n"
        "    name: str\n"
    )
    # No methods, so construction itself is what gets tested.
    sig = _sigs(src)["User.__init__"]
    assert sig.kind == "construction"
    assert sig.params == ["int", "str"]


def test_classvar_is_not_a_constructor_argument():
    src = (
        "@dataclass\n"
        "class Config:\n"
        "    VERSION: ClassVar[int] = 1\n"
        "    name: str\n"
    )
    assert _sigs(src)["Config.__init__"].params == ["str"]


def test_a_plain_class_takes_no_constructor_arguments():
    src = "class Counter:\n    def bump(self) -> int:\n        return 1\n"
    assert _sigs(src)["Counter.bump"].ctor_params == []


def test_construction_is_not_tested_twice():
    """Every method call builds one, so a separate construction test is noise."""
    src = "class Counter:\n    def bump(self) -> int:\n        return 1\n"
    assert "Counter.__init__" not in _sigs(src)


# --- constructors we refuse to guess at ---

def test_an_unbuildable_constructor_blocks_its_methods():
    """Rather than construct wrongly: Python raises on bad arguments where
    JavaScript binds `undefined`, so a guess would show up as fake drift."""
    for header, reason in [
        ("class A(Base):\n", "inherited_constructor"),
        ("class A(ABC):\n", "abstract_class"),
    ]:
        src = header + "    def go(self) -> int:\n        return 1\n"
        assert _sigs(src) == {}
        assert _skipped(src) == [("A.go", reason)]


def test_variadic_and_keyword_only_constructors_are_refused():
    variadic = (
        "class A:\n"
        "    def __init__(self, *args) -> None:\n"
        "        pass\n"
        "    def go(self) -> int:\n"
        "        return 1\n"
    )
    assert _skipped(variadic) == [("A.go", "variadic_constructor")]

    kwonly = (
        "class B:\n"
        "    def __init__(self, *, name: str) -> None:\n"
        "        pass\n"
        "    def go(self) -> int:\n"
        "        return 1\n"
    )
    assert _skipped(kwonly) == [("B.go", "keyword_only_constructor")]


def test_an_unbuildable_class_with_no_methods_is_still_named():
    """Nothing else would mention it, and silence reads as "fine"."""
    assert _skipped("class A(Base):\n    pass\n") == [("A", "inherited_constructor")]


def test_a_dataclass_subclass_is_refused_rather_than_undercounted():
    """A dataclass constructor is the base's fields *then* its own, and only
    this class's body is in view — claiming one argument for a constructor that
    takes three fails every call on the Python side alone."""
    src = (
        "@dataclass\n"
        "class Taxed(Item):\n"
        "    rate: float\n"
        "    def total(self) -> float:\n"
        "        return self.rate\n"
    )
    assert _sigs(src) == {}
    assert _skipped(src) == [("Taxed.total", "inherited_constructor")]


def test_field_init_false_is_not_a_constructor_argument():
    """`dataclasses` leaves it out of `__init__`, so passing it is a TypeError
    in Python while the target language would bind the extra harmlessly."""
    src = (
        "@dataclass\n"
        "class Counter:\n"
        "    start: int\n"
        "    seen: int = field(init=False, default=0)\n"
        "    def bump(self, n: int) -> int:\n"
        "        return n\n"
    )
    assert _sigs(src)["Counter.bump"].ctor_params == ["int"]


def test_required_keyword_only_arguments_are_refused():
    """The harness passes positional arguments only, so these can never be
    supplied: Python raises, the target binds `undefined` and runs on."""
    method = (
        "class A:\n"
        "    def render(self, text: str, *, upper: bool) -> str:\n"
        "        return text\n"
    )
    assert "A.render" not in _sigs(method)
    assert ("A.render", "keyword_only_method") in _skipped(method)

    function = "def render(text: str, *, upper: bool) -> str:\n    return text\n"
    assert _sigs(function) == {}
    assert _skipped(function) == [("render", "keyword_only_function")]

    # A keyword-only argument that *has* a default needs nothing supplied.
    defaulted = "def render(text: str, *, upper: bool = False) -> str:\n    return text\n"
    assert list(_sigs(defaulted)) == ["render"]


# --- members that need no receiver, and members that are out of reach ---

def test_static_and_class_methods_need_no_receiver():
    src = (
        "class A(Base):\n"                      # deliberately unbuildable...
        "    @staticmethod\n"
        "    def norm(item: str) -> str:\n"
        "        return item\n"
        "    @classmethod\n"
        "    def of(cls, n: int) -> int:\n"
        "        return n\n"
    )
    sigs = _sigs(src)                           # ...yet both are still testable
    assert sigs["A.norm"].kind == "static_method"
    assert sigs["A.norm"].ctor_params is None
    assert sigs["A.norm"].params == ["str"]
    assert sigs["A.of"].params == ["int"]        # `cls` dropped, `item` kept


def test_properties_private_and_async_methods_are_named_not_tested():
    src = (
        "class A:\n"
        "    @property\n"
        "    def size(self) -> int:\n"
        "        return 0\n"
        "    def _helper(self) -> int:\n"
        "        return 0\n"
        "    async def fetch(self) -> int:\n"
        "        return 0\n"
    )
    # Not one method is reachable — but the class can still be built, and
    # building it is the one thing left that can be compared.
    assert list(_sigs(src)) == ["A.__init__"]
    assert _skipped(src) == [
        ("A.size", "property"),
        ("A._helper", "private_method"),
        ("A.fetch", "async_method"),
    ]


# --- declared types ---

def test_method_types_drop_the_receiver_parameter():
    src = (
        "class Cart:\n"
        "    def add(self, item: str) -> int:\n"
        "        return 1\n"
    )
    types = PythonSourceAdapter().infer_types(src)
    assert types["Cart.add"] == {"params": {"item": "str"}, "returns": "int"}


# --- input planning ---

def test_every_call_gets_its_own_receiver():
    src = "class Cart:\n    def __init__(self, o: str) -> None:\n        pass\n" \
          "    def add(self, item: str) -> int:\n        return 1\n"
    plan = plan_inputs(_sigs(src)["Cart.add"], n=8)
    assert len(plan["args"]) == len(plan["ctor"]) == 8


def test_a_no_argument_method_still_varies_its_receiver():
    """`generate_inputs([])` is a single empty call; the receiver still varies."""
    src = "class Cart:\n    def __init__(self, o: str) -> None:\n        pass\n" \
          "    def size(self) -> int:\n        return 0\n"
    plan = plan_inputs(_sigs(src)["Cart.size"], n=6)
    assert plan["args"] == [[]] * 6
    assert len(plan["ctor"]) == 6


def test_a_plain_function_plans_no_constructor():
    sig = _sigs("def f(a: int) -> int:\n    return a\n")["f"]
    assert plan_inputs(sig, n=3)["ctor"] is None


# --- comparing what the object holds afterwards ---

def test_matching_state_is_not_drift():
    src = CallOutcome(ok=True, value=None, state={"items": ["a"]})
    tgt = CallOutcome(ok=True, value=None, state={"items": ["a"]})
    assert classify_divergence("Cart.add", ["a"], src, tgt) is None


def test_a_renamed_field_is_not_drift():
    """The idiom pass is *expected* to rename fields to target conventions."""
    src = CallOutcome(ok=True, value=1, state={"total_items": 2})
    tgt = CallOutcome(ok=True, value=1, state={"totalItems": 2})
    assert classify_divergence("Cart.add", ["a"], src, tgt) is None


def test_a_backing_field_does_not_swallow_its_public_twin():
    """`self._celsius` beside `self.celsius` normalizes to one key. Collapsing
    them would drop a value — and with it any drift hiding in it."""
    src = CallOutcome(ok=True, value=None, state={"_celsius": 10.0, "celsius": 50.0})
    tgt = CallOutcome(ok=True, value=None, state={"_celsius": 999.0, "celsius": 50.0})
    record = classify_divergence("Temp.set", [10.0], src, tgt)
    assert record is not None and record["category"] == "state_mismatch"

    # ...and the same pair agreeing is still not drift.
    same = CallOutcome(ok=True, value=None, state={"_celsius": 10.0, "celsius": 50.0})
    assert classify_divergence("Temp.set", [10.0], src, same) is None


def test_a_mutation_that_returns_the_right_value_is_still_caught():
    """The whole reason state is compared: the return value agrees, the object
    does not, and value comparison alone would call this verified."""
    src = CallOutcome(ok=True, value=1, state={"items": ["widget"]})
    tgt = CallOutcome(ok=True, value=1, state={"items": ["WIDGET"]})
    record = classify_divergence("Cart.add", ["Widget"], src, tgt)
    assert record is not None
    assert record["category"] == "state_mismatch"


def test_one_sided_state_is_reported_rather_than_ignored():
    src = CallOutcome(ok=True, value=None, state={"items": []})
    tgt = CallOutcome(ok=True, value=None, state=None)
    record = classify_divergence("Cart.add", ["a"], src, tgt)
    assert record is not None and record["category"] == "state_mismatch"


def test_a_method_failure_is_rendered_with_its_receiver():
    record = classify_divergence(
        "Cart.add",
        ["x"],
        CallOutcome(ok=True, value=1),
        CallOutcome(ok=True, value=2),
        ctor=["ada"],
    )
    assert record is not None
    assert render_call(record, lambda a: ", ".join(repr(x) for x in (a or []))) == (
        "new Cart('ada').add('x')"
    )


def test_construction_is_rendered_as_construction():
    record = {"function": "User.__init__", "args": [1, "ada"]}
    assert render_call(record, lambda a: ", ".join(repr(x) for x in (a or []))) == (
        "new User(1, 'ada')"
    )


# --- the harness, executing a real class ---

def _run_against(tmp_path, patched_cart: str, inputs=None):
    """Run the class fixture against a copy of itself, optionally sabotaged."""
    target = tmp_path / "target"
    shutil.copytree(FIXTURE, target)
    (target / "cart.py").write_text(patched_cart, encoding="utf-8")

    adapter = PythonSourceAdapter()
    source_code = (Path(FIXTURE) / "cart.py").read_text(encoding="utf-8")
    return check_equivalence(
        source_adapter=adapter,
        source_root=FIXTURE,
        target_adapter=adapter,     # the copy stands in for the "target"
        target_root=str(target),
        module="cart",
        signatures=adapter.signatures(source_code),
        inputs_by_func=inputs,
        n=10,
    )


def test_a_faithful_class_copy_has_no_divergence(tmp_path):
    original = (Path(FIXTURE) / "cart.py").read_text(encoding="utf-8")
    divergences, unverifiable, used = _run_against(tmp_path, original)

    assert unverifiable == []
    assert divergences == []
    # Methods really were called, not skipped into a vacuous pass.
    assert set(used) == {"Cart.add", "Cart.label", "Cart.normalize"}


def test_a_class_that_stores_the_wrong_thing_is_caught(tmp_path):
    """`add` still returns the right count; only the stored item differs."""
    sabotaged = (Path(FIXTURE) / "cart.py").read_text(encoding="utf-8").replace(
        "self.items.append(self.normalize(item))", "self.items.append(item)"
    )
    # Fixed inputs: a random string that survives `strip().lower()` unchanged
    # would hide the bug, and a flaky test about drift is worse than none.
    divergences, unverifiable, _ = _run_against(
        tmp_path,
        sabotaged,
        inputs={"Cart.add": {"args": [["  Widget "], ["MIXED Case"]], "ctor": [["ada"], ["ada"]]}},
    )

    assert unverifiable == []
    assert divergences, "a mutation that stores the wrong value must be caught"
    assert {d["category"] for d in divergences} == {"state_mismatch"}
    assert all(d["function"] == "Cart.add" for d in divergences)
    assert all("ctor" in d for d in divergences)   # reproducible: receiver included
