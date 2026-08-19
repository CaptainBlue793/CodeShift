# Python -> TypeScript semantic trip-wires

Operations that look equivalent and are not. Every entry below was verified by
running both languages; each one produces code that **type-checks and still
diverges**, which is the most expensive kind of bug for this pipeline to find.
When the source uses one of these, emit the right-hand form.

## Strings

- `text.split()` with **no argument** is not `split(/\s+/)`. Python also breaks
  on `\x1c`-`\x1f` and `\x85`, does *not* treat `\ufeff` as whitespace, and
  discards leading/trailing empty pieces. Emit:
  `text.split(/[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+/).filter(Boolean)`
  `text.split(sep)` with an explicit separator maps straight to `split(sep)` --
  no character class, no `.filter`.
- `text.strip()` is not `trim()`, and for the same reason: `trim()` leaves
  `\x1c`-`\x1f` in place and strips `\ufeff`, which Python keeps. Emit:
  `text.replace(/^[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\t\n\v\f\r \x1c-\x1f\x85\xa0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/g, "")`
  `lstrip()` and `rstrip()` keep only the half they need.
  `strip(chars)` with an argument strips *that set* from both ends, which is a
  different operation again.
- `len(s)` counts **code points**; JS `.length` counts UTF-16 code units, so
  every character above U+FFFF counts twice -- emoji, musical symbols, most CJK
  extensions, anything in an astral plane. `len("\U0001F600") == 1` but
  `"\u{1F600}".length === 2`. Emit `[...s].length` when the count is
  observable. The same split runs through indexing and slicing: `s[i]` and
  `s[a:b]` walk code points, while `s.charAt(i)` and `s.slice(a, b)` walk code
  units. `[...s]` gives an array you can index and slice safely.
- `"a" in s` is a substring test. JS `in` throws on strings -- use `s.includes("a")`.
- `s[-1]` is the last character. JS yields `undefined` -- use `s.at(-1)`.
- `str(x)` on a float keeps the decimal: `str(1.0) == "1.0"`, but
  `String(1.0) === "1"`. Preserve it explicitly if the value is observable.
- `c.isalnum()`, `.isalpha()` and `.isdigit()` are **Unicode-wide**: they are
  true for letters and digits in every script, so `"e".isalnum()`,
  `"\u00ea".isalnum()` and `"\U0002ae6a".isalnum()` are all true. An ASCII class
  silently drops every one of them past the first --
  `/[a-z0-9]/i` and `\w` match neither. Emit `/[\p{L}\p{N}]/u` for `isalnum()`,
  `/\p{L}/u` for `isalpha()`, `/\p{Nd}/u` for `isdigit()`. Test one character at
  a time: these are per-character predicates, and Python's return `False` on the
  empty string, which an anchored regex over `""` does not.

## Exceptions

- Python raises **`ValueError`**, `KeyError`, `IndexError`; JavaScript has none
  of those names, and `throw new Error(...)` produces a value whose class is
  `Error`. Where a caller can observe *which* error was raised -- a `catch` that
  discriminates, or a test comparing exception types -- a bare `Error` is a
  behavior change. Declare the classes the source raises and throw those:
  `class ValueError extends Error { constructor(message: string) { super(message); this.name = "ValueError"; } }`
  Reuse one definition per module rather than throwing an anonymous `Error`.

## Numbers

- `a // b` is **floor** division: `-7 // 2 == -4`. Use `Math.floor(a / b)`.
  `Math.trunc` gives `-3` and is wrong for negatives.
- `a % b` takes the sign of the **divisor**: `-7 % 3 == 2`, while JS gives `-1`.
  Use `((a % b) + b) % b`.
- `round()` is banker's rounding: `round(0.5) == 0`, `round(2.5) == 2`.
  `Math.round` gives `1` and `3`.
- Python ints are arbitrary precision; JS numbers lose integer precision beyond
  `2**53` (`2**53 + 1` round-trips to `2**53`). Use `BigInt` when a value can
  exceed that.

## Collections

- `sorted(xs)` compares numbers numerically. JS `.sort()` **with no comparator
  sorts lexicographically**: `[10, 9, 1].sort()` is `[1, 10, 9]`. Always pass
  one: `.sort((a, b) => a - b)`.
- `dict` preserves insertion order for every key. A JS object hoists
  integer-like keys into numeric order ahead of the rest -- `{b, "2", a, "1"}`
  enumerates as `1, 2, b, a`. If key order is observable, use a `Map`.
- Truthiness differs on containers: `bool([]) is False`, but `Boolean([]) === true`.
  Empty arrays, objects and `Map`s are all truthy in JS. Test `.length === 0`
  or `.size === 0` explicitly.
