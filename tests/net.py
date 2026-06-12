from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """Net snapshots an env class into the frozen authoring boundary."""

    @peven.env("airline")
    class Airline:
        start = peven.place()
        done = peven.place(terminal=True)
        finish = peven.transition(inputs=["start"], outputs=["done"], executor="finish")

    spec = peven.net(Airline)

    assert spec.name == "airline"
    assert spec.places["start"] is Airline.start
    assert spec.places["done"] is Airline.done
    assert spec.transitions["finish"] is Airline.finish


def test_002() -> None:
    """Net mappings are snapshots, not mutable env class storage."""

    @peven.env("airline")
    class Airline:
        start = peven.place()
        done = peven.place(terminal=True)
        finish = peven.transition(inputs=["start"], outputs=["done"], executor="finish")

    spec = peven.net(Airline)

    with pytest.raises(TypeError):
        spec.places["late"] = peven.place()
    with pytest.raises(TypeError):
        spec.transitions["late"] = peven.transition(
            inputs=["start"],
            outputs=["done"],
            executor="late",
        )


def test_003() -> None:
    """The package root exposes net(), not a duplicate public Net type."""
    assert not hasattr(peven, "Net")


def test_004() -> None:
    """Net only accepts classes finalized by peven.env."""
    with pytest.raises(TypeError, match="env class"):
        peven.net(object())

    class Plain:
        pass

    with pytest.raises(TypeError, match=r"peven\.env"):
        peven.net(Plain)


def test_005() -> None:
    """Net lower emits Peven.jl-shaped topology without runtime behavior."""

    @peven.env("airline")
    class Airline:
        start = peven.place(capacity=2)
        done = peven.place(terminal=True)
        finish = peven.transition(inputs=["start"], outputs=["done"], executor="finish")

    assert peven.net(Airline).lower() == {
        "name": "airline",
        "places": [
            {"id": "start", "capacity": 2},
            {"id": "done", "capacity": None},
        ],
        "transitions": [
            {"id": "finish", "executor": "finish"},
        ],
        "arcsFrom": [
            {
                "transition": "finish",
                "from": "start",
                "weight": 1,
                "optional": False,
            },
        ],
        "arcsTo": [
            {"transition": "finish", "to": "done", "weight": 1},
        ],
    }
