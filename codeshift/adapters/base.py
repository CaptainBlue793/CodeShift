"""Language adapter interfaces — the extensibility contract.

Every source language implements `SourceAdapter`; every target language
implements `TargetAdapter`. Agents and the graph depend only on these ABCs,
never on a concrete language, so adding Go/Rust later is a new adapter package
plus one line in `registry.py`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class ParsedModule:
    module: str                          # dotted module name
    path: str                            # relative source path
    source_code: str
    imports: list[str] = field(default_factory=list)  # dotted names it depends on


@dataclass
class ParsedProject:
    modules: list[ParsedModule] = field(default_factory=list)


#: How the harness reaches a callable. Anything other than "function" is
#: addressed by a qualified name (`Cart.add_item`) rather than a bare one.
CallKind = Literal["function", "method", "static_method", "construction"]


@dataclass
class FuncSig:
    """A callable the differential harness can exercise.

    A plain function needs nothing but its name. A method needs a *receiver*, so
    `ctor_params` carries the constructor's parameter types and the harness
    builds a fresh instance for every call — see `equivalence.harness`. Static
    and class methods need no receiver and leave `ctor_params` None.

    `kind="construction"` is the degenerate case worth keeping: a class whose
    methods are all untestable (or that has none, like a dataclass) still has
    observable behavior in its constructor, so `Cart.__init__` is exercised on
    its own and compared by the resulting attributes.
    """
    name: str                                         # "slugify" or "Cart.add_item"
    params: list[str] = field(default_factory=list)   # param type names ("unknown" if unannotated)
    returns: Optional[str] = None
    kind: CallKind = "function"
    ctor_params: Optional[list[str]] = None           # None when no receiver is built

    @property
    def owner(self) -> Optional[str]:
        """The declaring class, for anything addressed by a qualified name."""
        return self.name.rpartition(".")[0] or None


@dataclass
class Untestable:
    """A construct the differential runner cannot exercise.

    `signatures()` deliberately returns only what the harness can call. Anything
    it skips still gets translated, so it has to be named somewhere — otherwise
    an untested module is indistinguishable from a clean one.
    """
    name: str
    reason: str   # a slug; see codeshift.verification.REASON_LABEL


@dataclass
class CallOutcome:
    """The result of invoking one callable on one input."""
    ok: bool                      # True if it returned; False if it raised
    value: Any = None             # JSON-serializable return value (when ok)
    error: Optional[str] = None   # exception type name, or a runner sentinel (when not ok)
    #: The receiver's attributes after the call, for calls that had one. `None`
    #: means "no receiver", not "no attributes" — a mutating method that returns
    #: nothing is otherwise compared as `None == undefined` and passes vacuously.
    state: Optional[dict] = None


@dataclass
class RunResult:
    """Raw process result (used by the sandbox runner)."""
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class SourceAdapter(ABC):
    """Reads and executes code in the source language."""

    @abstractmethod
    def parse(self, root: str) -> ParsedProject:
        """Discover modules, imports, and symbols under `root`."""

    @abstractmethod
    def signatures(self, source_code: str) -> list[FuncSig]:
        """Extract the callable signatures a module exposes, functions and methods."""

    @abstractmethod
    def untestable(self, source_code: str) -> list[Untestable]:
        """Name the constructs `signatures()` cannot cover.

        Abstract rather than defaulting to `[]` on purpose: a new language
        adapter that says nothing here would silently report every module as
        verified, which is the exact failure this exists to prevent.
        """

    @abstractmethod
    def infer_types(
        self, source_code: str, *, root: str | None = None, module: str | None = None
    ) -> dict:
        """Return declared/inferred types per callable:
        {name: {"params": {name: type}, "returns": type}}, keyed exactly as
        `signatures()` names them (so methods appear as `Cart.add_item`).

        `root`/`module` locate the code within its real source tree so a type
        oracle can resolve internal imports. Without them (or without the
        oracle installed) adapters fall back to declared annotations only.
        """

    @abstractmethod
    def run(
        self,
        root: str,
        module: str,
        func: str,
        inputs: list[list],
        ctor_inputs: Optional[list[list]] = None,
    ) -> list[CallOutcome]:
        """Invoke `module.func` once per input arg-list inside a sandbox.

        `func` may be qualified (`Cart.add_item`). `ctor_inputs`, when given,
        holds one constructor arg-list per input: the receiver is rebuilt for
        every call so each comparison depends only on its own inputs.
        """


class TargetAdapter(ABC):
    """Emits, type-checks, formats, and executes code in the target language."""

    @abstractmethod
    def emit(self, module: str, code: str) -> str:
        """Write translated code to disk; return the written path."""

    @abstractmethod
    def exports(self, code: str) -> list[str]:
        """Return the names of top-level symbols exported by a target module."""

    @abstractmethod
    def map_type(self, source_type: str) -> str:
        """Map a source-language type name to a target-language type."""

    @abstractmethod
    def typecheck(self, root: str) -> list[dict]:
        """Run the target type oracle (e.g. tsc); return diagnostics."""

    @abstractmethod
    def format(self, path: str) -> None:
        """Apply the idiomatic-backstop formatter/linter in place."""

    @abstractmethod
    def run(
        self,
        root: str,
        module: str,
        func: str,
        inputs: list[list],
        ctor_inputs: Optional[list[list]] = None,
    ) -> list[CallOutcome]:
        """Invoke `module.func` once per input arg-list inside a sandbox.

        Mirrors `SourceAdapter.run`; `func` is the *target's* name for the
        callable (see `utils.naming.build_symbol_map`).
        """
