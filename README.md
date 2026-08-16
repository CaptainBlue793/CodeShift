# CodeShift

A multi-agent code migration system that translates a codebase from one language
to another **while preserving behavior**. v1 targets **Python → TypeScript**;
the architecture is language-agnostic behind pluggable adapters.

## Agents

1. **Dependency/structure mapper** — builds the dependency DAG and translation order.
2. **Translator** — emits target code per module, in dependency order (with typed hints).
3. **Type-inference agent** — dynamic (Python) → static (TypeScript) typing, and
   runs `tsc` over the emitted code. Code that does not compile goes straight
   back to the translator, before the expensive differential run.
4. **Test-equivalence agent** — runs original vs. translated code on identical
   inputs to catch semantic drift; loops back to the translator on divergence.
   Classes are covered as well as functions: it builds a fresh instance per call
   and compares both the return value and **the attributes the object holds
   afterwards**, so a method that mutates and returns nothing cannot pass
   vacuously. It also records what it *could not* check — an `async def`, a
   property, a class whose constructor cannot be built from generated arguments
   — by name, as unverified rather than counted as passing. "Verified
   equivalent" always means code was executed and compared, never merely that
   nothing was found.
5. **Idiom/style agent** — cleans up literal translations (prettier backstop).
6. **Reviewer/summarizer** — produces the migration report.

## Stack

Everything is **free / open-source — no API key, no cost.**

Python 3.12 · LangGraph (orchestration) · **local Ollama** LLM (default
`qwen3:14b`; set `qwen2.5:7b` in `codeshift/config.py` for faster, lower-quality runs)
· tree-sitter + `ast` (parsing) · networkx (dependency DAG) · Hypothesis + pytest
(differential testing; TypeScript executed live via `tsx`) · Docker (execution
sandbox, optional — see below) · mypy + `tsc` (type oracles) · Prettier (idiom
backstop).

The LLM is isolated in `codeshift/llm/client.py`, so swapping the backend is a
one-file change.

## Sandboxing

The test-equivalence agent **executes** the translated code, which a language
model wrote. `sandbox` in `codeshift/config.py` decides what that execution gets:

| Setting | Behaviour |
|---|---|
| `"docker"` | Requires isolation. Both sides run in a throwaway container — no network, read-only mounts, non-root, memory/CPU/PID capped. **If Docker is unavailable, nothing is executed** and the affected modules are reported as unverified rather than run unprotected. Use this for code you did not write. |
| `"auto"` (default) | Isolates when Docker is present; otherwise runs on the host and says so, in the log and in the report. |
| `"host"` | Deliberate, unisolated execution. Fast, and fine for a fixture you wrote yourself. |

The sandbox images build themselves on first use (`codeshift/sandbox/images/`)
and are tagged by a hash of their Dockerfile, so editing one rebuilds it. The
build needs the network; the runs never have it.

A run's isolation is stated at the top of `REPORT.md` — "verified equivalent"
means something different depending on where the code ran.

## Status

**The architecture is complete; the tool is not yet validated at scale.** All six
agents work, the pipeline runs end to end at zero cost on a local model, and
"verified equivalent" means code was executed and compared. But every result so
far comes from two small fixtures totalling 7 modules — see
[Limitations](#limitations) before pointing this at a real codebase.

## Prerequisites

- A Python 3.12 environment (the author's is a conda env named `starGPU`;
  nothing depends on the name).
- **[Ollama](https://ollama.com)** running locally, with a model pulled:
  ```bash
  ollama pull qwen3:14b
  ```
- **Node.js** (for the TypeScript target: `npx tsx` runs it, `npx prettier` formats it).
  Not needed for running translated code under `sandbox="docker"` — the image
  carries its own — but still needed for the `tsc` and Prettier passes.
- **Docker** — optional, and the difference between isolated and unisolated
  execution. See [Sandboxing](#sandboxing).

## Setup

```bash
PY="python"                     # or the full path to your env's interpreter
"$PY" -m pip install -r requirements.txt
```

For type checking, copy `pyrightconfig.example.json` to `pyrightconfig.json` and
point `venvPath`/`venv` at your environment — Pyright cannot resolve the
installed packages without them, which is why the real file is gitignored.

No API key or `.env` is needed. To point at a remote Ollama server, set the
`OLLAMA_HOST` environment variable (or `ollama_host` in `codeshift/config.py`).

## Usage

```bash
"$PY" main.py --source ./tests/fixtures/sample_app --from python --to typescript
```

Translated code is written to `data/output/`, and the migration report to
`data/output/REPORT.md` (also printed to the console).

### Dashboard

```bash
"$PY" -m streamlit run ui/app.py
```

Launches runs from the browser and streams them live: each module's verification
verdict, the translate↔verify loop's attempt-by-attempt error counts (`1 → 0 → 1`,
labelled improving/stuck/regressed), the report, and source-vs-translated code
side by side. The graph runs on a worker thread and publishes a state snapshot
after every node, so the page stays responsive through a 20-minute run.

## Layout

```
codeshift/
  graph.py, state.py, config.py   # orchestration core
  candidates.py                   # best-attempt scoring across retries
  verification.py                 # verified vs. never-checked (one shared rule)
  llm/                            # the ONLY LLM boundary (local Ollama)
    prompts/pitfalls/<a>-<b>.md   # per-pair semantic trip-wires (optional)
  agents/                         # one module per agent = one graph node
  adapters/                       # per-language plug-ins (python/, typescript/)
  sandbox/                        # container isolation (policy.py decides, loudly)
  depgraph/  equivalence/  report/  utils/
ui/                               # Streamlit dashboard (app.py, runner.py)
```

## Tests

```bash
"$PY" -m pytest tests -q        # 190 tests
"$PY" -m mypy codeshift
"$PY" -m pyright
```

## Limitations

Stated plainly, because a migration tool that oversells its own verification is
worse than no tool. Everything below is known and unfixed.

**Only ever run on small fixtures.** The two test projects total 7 modules, each
with roughly one function or class. Every "verified equivalent" result in this
repo comes from those. Nothing is known about 50+ modules, which is where
context limits and compounding errors become the real problem.

**Import cycles are not handled.** `depgraph/builder.py` topologically sorts the
dependency graph and assumes it is acyclic; a project with circular imports
raises rather than degrading gracefully. Most real Python codebases have at
least one.

**The Docker sandbox has never actually run a container.** Docker is not
installed on the development machine, so the container path is covered by unit
tests asserting the argv, mounts and flags — not by execution. `sandbox="docker"`
is the documented way to run untrusted code safely; treat that claim as
untested until someone runs it on a machine with Docker.

**Comparison gaps that can produce wrong reports**, rather than crashes:

- Floats are compared exactly (`equivalence/diff.py`), so numeric code would
  report drift on ordinary rounding differences.
- Object state that is not JSON-native diverges on correct translations: a
  Python `set` serializes as `"{'a', 'b'}"` while a JS `Set` serializes as `{}`
  — which also means a *wrong* set compares equal to a right one. `datetime`
  and JS `Date` disagree on format.
- Parse errors are swallowed (`adapters/python/parser.py`) instead of being
  surfaced in the run's error list.
- Hypothesis cannot shrink (`equivalence/inputs.py`), so a single bug arrives as
  dozens of near-identical failures rather than one minimal repro. The
  translator dedupes them for its retry prompt, which treats the symptom.
- Constructors inherited from a base class are refused rather than resolved,
  so those classes are reported unverified instead of being tested.

**Results are not reproducible.** The LLM is nondeterministic. The best observed
runs are 4/4 modules on `sample_app` and 3/3 on `class_app`, every module on the
first attempt — but a clean run is not guaranteed to repeat.
