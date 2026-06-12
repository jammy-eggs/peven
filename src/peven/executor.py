from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar


F = TypeVar("F", bound=Callable)


def executor(name: str) -> Callable[[F], F]:
    if type(name) is not str:
        raise TypeError("executor name must be a string")
    if not name:
        raise ValueError("executor name must be non-empty")

    def wrap(fn: F) -> F:
        if not callable(fn):
            raise TypeError("peven.executor can only decorate callables")
        fn.__executor__ = name
        return fn

    return wrap
