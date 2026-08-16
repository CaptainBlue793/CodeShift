# Reviewer/summarizer prompt

Write the migration report for a completed run. Be factual and lead with the
outcome.

## Inputs
- Per-module status (translated / verified / idiomatic / failed).
- Divergences found and whether they were resolved.
- Equivalence-test coverage and any unresolved risks.

## Output (Markdown)
- One-paragraph outcome summary.
- Per-module table: status, attempts, residual risks.
- "Needs human attention" section for failed modules and unresolved divergences.
