"""Half of a circular import: orders needs customers to resolve an owner."""
from customers import owner_label
from models import tag


def describe(order_id: str) -> str:
    return f"{tag(order_id)} for {owner_label(order_id)}"
