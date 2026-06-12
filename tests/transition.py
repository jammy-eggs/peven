from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """Transition declarations preserve topology and executor metadata.

    The declaration is Python-side authoring IR only. Peven.jl owns firing, arc
    validation, retries, joins, execution contexts, and runtime semantics.
    """
    transition = peven.transition(
        inputs=["state", "db"],
        outputs=["agent"],
        executor="sim",
    )

    assert transition.inputs == ("state", "db")
    assert transition.outputs == ("agent",)
    assert transition.executor == "sim"


def test_002() -> None:
    """Separate transition declarations are distinct authored nodes."""
    left = peven.transition(inputs=["a"], outputs=["b"], executor="step")
    right = peven.transition(inputs=["a"], outputs=["b"], executor="step")

    assert left != right


def test_003() -> None:
    """A transition may consume from and emit to the same place.

    Loops are central Petri-net structure. Duplicate rejection only applies
    within one side of the transition, not across inputs and outputs.
    """
    transition = peven.transition(
        inputs=["state"],
        outputs=["state", "score"],
        executor="step",
    )

    assert transition.inputs == ("state",)
    assert transition.outputs == ("state", "score")


def test_004() -> None:
    """Inputs and outputs must be explicit sequences, not bare strings or sets."""
    with pytest.raises(TypeError, match="inputs"):
        peven.transition(inputs="state", outputs=["done"], executor="step")
    with pytest.raises(TypeError, match="outputs"):
        peven.transition(inputs=["state"], outputs={"done"}, executor="step")


def test_005() -> None:
    """Inputs and outputs must name at least one place."""
    with pytest.raises(ValueError, match="inputs"):
        peven.transition(inputs=[], outputs=["done"], executor="step")
    with pytest.raises(ValueError, match="outputs"):
        peven.transition(inputs=["state"], outputs=[], executor="step")


def test_006() -> None:
    """Duplicate names on one side are rejected instead of implying weights.

    Peven.jl supports weighted arcs internally, but this authoring layer does
    not expose weights in the first transition surface.
    """
    with pytest.raises(ValueError, match="inputs"):
        peven.transition(inputs=["state", "state"], outputs=["done"], executor="step")
    with pytest.raises(ValueError, match="outputs"):
        peven.transition(inputs=["state"], outputs=["done", "done"], executor="step")


def test_007() -> None:
    """Place ids and executor names must be explicit strings."""
    with pytest.raises(TypeError, match="inputs"):
        peven.transition(inputs=[1], outputs=["done"], executor="step")
    with pytest.raises(TypeError, match="outputs"):
        peven.transition(inputs=["state"], outputs=[1], executor="step")
    with pytest.raises(TypeError, match="executor"):
        peven.transition(inputs=["state"], outputs=["done"], executor=1)
    with pytest.raises(ValueError, match="inputs"):
        peven.transition(inputs=[""], outputs=["done"], executor="step")
    with pytest.raises(ValueError, match="outputs"):
        peven.transition(inputs=["state"], outputs=[""], executor="step")
    with pytest.raises(ValueError, match="executor"):
        peven.transition(inputs=["state"], outputs=["done"], executor="")
