# Idiom/style prompt

Rewrite a behavior-verified literal translation into idiomatic {target_lang},
**without changing behavior**. A formatter/linter runs afterwards, so focus on
structure and idiom, not whitespace.

## Inputs
- The verified, literally-translated module.

## Rules
- Use idiomatic constructs (native iteration, standard library, language patterns).
- Preserve the public interface and all observable behavior.
- Do not add features, abstractions, or error handling for cases that can't happen.

## Output
- The idiomatic {target_lang} module source.
