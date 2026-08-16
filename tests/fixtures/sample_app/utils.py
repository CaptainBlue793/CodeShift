"""String utilities (no internal dependencies)."""


def slugify(text: str) -> str:
    return "-".join(text.lower().split())
