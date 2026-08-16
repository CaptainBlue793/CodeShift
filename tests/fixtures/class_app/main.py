"""Entry point — depends on cart and models."""
from cart import Cart
from models import User


def run() -> str:
    user = User(1, "Ada Lovelace")
    cart = Cart(user.name)
    cart.add("  Widget ")
    return cart.label()


if __name__ == "__main__":
    print(run())
