"""Domain data (no internal dependencies).

A dataclass has no methods to call, so the constructor is the behavior under
test: build one on each side and compare the attributes it comes out with.
"""
from dataclasses import dataclass


@dataclass
class User:
    user_id: int
    name: str
