# Divergence-classification prompt (cheap step)

Given one input and the two outputs (original vs translated), decide whether
they are behaviorally equivalent, and if not, classify the difference.

## Inputs
- The input.
- Original output (stdout / return value / exception / exit code).
- Translated output (same fields).

## Output (concise)
- `equivalent`: true/false
- If false: category (`value_mismatch` | `exception_behavior` | `type_shape` |
  `ordering` | `other`) and a one-line description precise enough for the
  translator to fix the specific mismatch.
