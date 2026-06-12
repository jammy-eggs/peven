from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class RunKey:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str:
            raise TypeError("runKey value must be a string")
        if not self.value:
            raise ValueError("runKey value must be non-empty")

def runKey(value: str | None = None) -> RunKey:
    if value is None:
        return RunKey(value=uuid4().hex)
    return RunKey(value=value)
