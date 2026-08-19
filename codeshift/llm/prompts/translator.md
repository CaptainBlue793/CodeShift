# Translator prompt

Translate one {source_lang} module to {target_lang}, **preserving behavior
exactly**. Idiomatic cleanup happens in a later step — here, correctness first.

## Inputs
- Source module code.
- Signatures/types of already-translated dependency modules (use them; do not
  re-translate them).
- Inferred types for this module.
- On retry: **your previous attempt's code, with line numbers**, plus the
  type-checker diagnostics and/or behavioral divergences it produced.

## On retry
You are being shown your own previous output because it failed. Treat it as a
patch job, not a fresh translation:
- Locate each reported line in the numbered code and change **that** code.
- Keep everything the diagnostics do not implicate — a rewrite that reintroduces
  a fixed bug is worse than a narrow edit.
- A diagnostic means your code was wrong, not that the source was. Where the two
  languages differ (a method that exists in one and not the other, different
  defaults for the same-named operation), write the target code that reproduces
  the **source's** behavior rather than the code that merely looks similar.
- Still output the complete module, not a diff.

## Rules
- Preserve observable behavior: return values, side effects, exceptions, ordering.
- **Export every top-level function (and class)** so other modules and tests can
  import it (in TypeScript, prefix each with `export`).
- **Translate a class as a class**, not as loose functions or a factory that
  returns an object literal. Keep its constructor's parameters in the same order,
  keep each method a method, and keep the attributes it stores — the equivalence
  check builds an instance and compares the attributes afterwards, so a renamed
  method or a field folded into a closure reads as behavioral drift. Renaming a
  field to the target's conventions (`total_items` -> `totalItems`) is fine;
  dropping one, or storing something different in it, is not.
- **Import each dependency from the specifier printed in its header**, copied
  exactly (e.g. a header reading `- import it from "../core/money"` means
  `import { formatCents } from "../core/money"`). The specifier already accounts
  for the directory this module is emitted into; do not shorten it to `./name`,
  do not add a file extension, and do not invent a path of your own.
- Match the dependencies' already-translated interfaces and their exported names.
- If a construct has no direct target equivalent, choose the closest
  behavior-preserving option and add a brief `// NOTE:` comment.

## Output
- Only the translated {target_lang} source for this module. No prose, no
  Markdown fences.
