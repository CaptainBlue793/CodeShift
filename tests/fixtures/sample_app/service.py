"""User service — depends on models and utils."""
from models import make_user
from utils import slugify


def register(user_id: int, name: str) -> dict:
    user = make_user(user_id, name)
    user["slug"] = slugify(name)
    return user
