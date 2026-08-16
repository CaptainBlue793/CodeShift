"""The other half: customers needs orders to count what a customer has."""
from models import tag


def owner_label(order_id: str) -> str:
    return f"customer-{tag(order_id)}"


def order_count(customer: str) -> int:
    from orders import describe
    return len(describe(customer))
