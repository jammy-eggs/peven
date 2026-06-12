from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, eq=False)
class Transition:
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    executor: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", placeIds("inputs", self.inputs))
        object.__setattr__(self, "outputs", placeIds("outputs", self.outputs))
        if type(self.executor) is not str:
            raise TypeError("transition executor must be a string")
        if not self.executor:
            raise ValueError("transition executor must be non-empty")


def transition(
    *,
    inputs: list[str] | tuple[str, ...],
    outputs: list[str] | tuple[str, ...],
    executor: str,
) -> Transition:
    return Transition(inputs=inputs, outputs=outputs, executor=executor)


def placeIds(kind: str, ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if type(ids) not in (list, tuple):
        raise TypeError(f"transition {kind} must be a list or tuple")
    if not ids:
        raise ValueError(f"transition {kind} must be non-empty")

    seen: set[str] = set()
    for id in ids:
        if type(id) is not str:
            raise TypeError(f"transition {kind} must contain only strings")
        if not id:
            raise ValueError(f"transition {kind} must contain non-empty strings")
        if id in seen:
            raise ValueError(f"transition {kind} cannot repeat place {id}")
        seen.add(id)

    return tuple(ids)
