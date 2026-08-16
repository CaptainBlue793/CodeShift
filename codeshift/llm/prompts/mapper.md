# Mapper prompt

You resolve ambiguous or dynamic cross-module references that static parsing
could not settle (dynamic imports, re-exports, conditional imports), so the
dependency graph and translation order are correct.

## Inputs
- Project module list with statically-detected imports.
- Snippets around unresolved references.

## Output
- For each ambiguous reference: the module it actually depends on, or "none".
- Do not invent modules outside the provided list.
