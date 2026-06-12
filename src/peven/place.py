from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class Place:
    terminal: bool = False
    capacity: int | None = None

    def __post_init__(self) -> None:
        if type(self.terminal) is not bool:
            raise TypeError("place terminal must be a bool")
        if self.capacity is not None:
            if type(self.capacity) is not int:
                raise TypeError("place capacity must be an int or None")
            if self.capacity < 1:
                raise ValueError("place capacity must be greater than 0")


def place(*, terminal: bool = False, capacity: int | None = None) -> Place:
    return Place(terminal=terminal, capacity=capacity)
