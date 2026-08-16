"""Domain data helpers (no internal dependencies)."""


def make_user(user_id: int, name: str) -> dict:
    return {"id": user_id, "name": name}
