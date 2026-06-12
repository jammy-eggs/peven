from __future__ import annotations

from collections.abc import Callable

from peven.place import Place
from peven.transition import Transition


def env(name: str) -> Callable[[type], type]:
    if type(name) is not str:
        raise TypeError("env name must be a string")
    if not name:
        raise ValueError("env name must be non-empty")

    def wrap(cls: type) -> type:
        if not isinstance(cls, type):
            raise TypeError("peven.env can only decorate classes")

        places: dict[str, Place] = {}
        transitions: dict[str, Transition] = {}

        for pid, value in cls.__dict__.items():
            if isinstance(value, Place):
                if value in places.values():
                    raise ValueError("place declarations cannot be reused")
                places[pid] = value
                continue

            if isinstance(value, Transition):
                if value in transitions.values():
                    raise ValueError("transition declarations cannot be reused")
                transitions[pid] = value

        if not places:
            raise ValueError("peven env must declare at least one place")
        if not transitions:
            raise ValueError("peven env must declare at least one transition")

        for tid, transition in transitions.items():
            for pid in transition.inputs:
                if pid not in places:
                    raise ValueError(f"transition {tid} input {pid} is not a place")
                if places[pid].terminal:
                    raise ValueError(
                        f"transition {tid} cannot consume terminal place {pid}"
                    )

            for pid in transition.outputs:
                if pid not in places:
                    raise ValueError(f"transition {tid} output {pid} is not a place")

        cls.__env__ = name
        cls.__places__ = places
        cls.__transitions__ = transitions
        return cls

    return wrap
