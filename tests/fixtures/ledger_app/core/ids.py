"""Reference numbers and their check digits.

Depends on `core.text` for normalization so that a reference derived from a
name is stable however the name was typed.
"""
from __future__ import annotations

from core.text import initials, slugify


def checksum(text: str) -> int:
    """A small position-weighted checksum, in `0..96`.

    Deliberately not a hash: it has to be reproducible across languages and
    readable in a printed reference.
    """
    total = 0
    for index, char in enumerate(text):
        total = total + (index + 1) * ord(char)
    return total % 97


def check_digit(text: str) -> str:
    """The checksum rendered as two characters, so refs are fixed width."""
    return str(checksum(text)).rjust(2, "0")


def make_ref(prefix: str, sequence: int) -> str:
    """`INV` + 42 -> `INV-000042-17`: prefix, padded sequence, check digit."""
    if sequence < 0:
        raise ValueError("sequence must not be negative")
    head = slugify(prefix).upper().replace("-", "")
    if not head:
        head = "REF"
    body = head + "-" + str(sequence).rjust(6, "0")
    return body + "-" + check_digit(body)


def is_valid_ref(ref: str) -> bool:
    """True when the trailing check digit matches the rest of the reference."""
    cut = ref.rfind("-")
    if cut <= 0:
        return False
    body = ref[:cut]
    return ref[cut + 1 :] == check_digit(body)


def sequence_of(ref: str) -> int:
    """The numeric middle of a reference, or -1 when it has none."""
    parts = ref.split("-")
    if len(parts) < 3:
        return -1
    if not parts[1].isdigit():
        return -1
    return int(parts[1])


def party_code(name: str) -> str:
    """A short, stable code for a counterparty: initials plus a check digit."""
    head = initials(name)
    if not head:
        return "XX-00"
    return head + "-" + check_digit(head)
