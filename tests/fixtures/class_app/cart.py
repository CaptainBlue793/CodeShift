"""A stateful class — the case top-level functions never covered.

`add` is the interesting one: it mutates the receiver *and* returns a value, so
a translation can get the return right while storing the wrong thing.
"""


class Cart:
    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.items: list[str] = []

    def add(self, item: str) -> int:
        self.items.append(self.normalize(item))
        return len(self.items)

    def label(self) -> str:
        return f"{self.owner}: {len(self.items)}"

    @staticmethod
    def normalize(item: str) -> str:
        return item.strip().lower()
