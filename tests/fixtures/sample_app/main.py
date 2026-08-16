"""Entry point — depends on service."""
from service import register


def run() -> dict:
    return register(1, "Ada Lovelace")


if __name__ == "__main__":
    print(run())
