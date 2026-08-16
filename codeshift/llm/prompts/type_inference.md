# Type-inference prompt

Add precise static {target_lang} types to a translated module that came from a
dynamically-typed source. Prefer specific types over `any`/`unknown`.

## Inputs
- Translated module code (may be under-typed).
- Inferred types from the source type oracle (mypy/pyright) — treat as ground truth.
- Dependency interfaces.

## Rules
- Use the oracle's types where available; infer the rest from usage.
- Introduce interfaces/type aliases for structured data.
- Never change runtime behavior — types only.

## Output
- The fully-typed {target_lang} module source.
