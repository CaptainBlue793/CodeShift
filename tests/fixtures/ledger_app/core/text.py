"""String helpers used across the engine. No internal dependencies."""
from __future__ import annotations


def normalize_space(text: str) -> str:
    """Collapse every run of whitespace to a single space and strip the ends."""
    return " ".join(text.split())


def slugify(text: str) -> str:
    """A lowercase, hyphen-joined key derived from free text."""
    cleaned = "".join(c if c.isalnum() else " " for c in text.lower())
    return "-".join(cleaned.split())


def pad_right(text: str, width: int) -> str:
    """Left-align `text` in a field `width` characters wide."""
    if width <= len(text):
        return text
    return text + " " * (width - len(text))


def pad_left(text: str, width: int) -> str:
    """Right-align `text` in a field `width` characters wide."""
    if width <= len(text):
        return text
    return " " * (width - len(text)) + text


def truncate(text: str, width: int) -> str:
    """Shorten `text` to `width`, marking the cut with an ellipsis."""
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def title_case(text: str) -> str:
    """Capitalize each whitespace-separated word, lowercasing the rest."""
    out = []
    for word in normalize_space(text).split(" "):
        if not word:
            continue
        out.append(word[0].upper() + word[1:].lower())
    return " ".join(out)


def initials(name: str) -> str:
    """First letter of each word, uppercased: `Acme Trading Co` -> `ATC`."""
    return "".join(w[0].upper() for w in normalize_space(name).split(" ") if w)
