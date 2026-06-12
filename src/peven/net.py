from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from peven.place import Place
from peven.transition import Transition


@dataclass(frozen=True, slots=True)
class Net:
    name: str
    places: Mapping[str, Place]
    transitions: Mapping[str, Transition]

    def lower(self) -> dict[str, object]:
        return {
            "name": self.name,
            "places": [
                {"id": pid, "capacity": place.capacity}
                for pid, place in self.places.items()
            ],
            "transitions": [
                {"id": tid, "executor": transition.executor}
                for tid, transition in self.transitions.items()
            ],
            "arcsFrom": [
                {
                    "transition": tid,
                    "from": pid,
                    "weight": 1,
                    "optional": False,
                }
                for tid, transition in self.transitions.items()
                for pid in transition.inputs
            ],
            "arcsTo": [
                {"transition": tid, "to": pid, "weight": 1}
                for tid, transition in self.transitions.items()
                for pid in transition.outputs
            ],
        }


def net(envClass: type) -> Net:
    if not isinstance(envClass, type):
        raise TypeError("peven.net expects an env class")
    if not hasattr(envClass, "__env__"):
        raise TypeError("peven.net expects a class decorated with peven.env()")

    return Net(
        name=envClass.__env__,
        places=MappingProxyType(dict(envClass.__places__)),
        transitions=MappingProxyType(dict(envClass.__transitions__)),
    )
