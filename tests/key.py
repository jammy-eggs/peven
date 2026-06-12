from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """Run keys are opaque authoring objects backed by unique strings.

    Peven.jl requires runKey as a String, but Python users should not need to
    invent collision-free run key strings by hand.
    """
    left = peven.runKey()
    right = peven.runKey()

    assert left != right
    assert type(left.value) is str
    assert len(left.value) == 32


def test_002() -> None:
    """RunKey is not exported as a duplicate public constructor."""
    assert not hasattr(peven, "RunKey")


def test_003() -> None:
    """Run keys accept explicit values so task and run identity stay distinct.

    Group rollouts name run keys like task-003#g0, where the task id is shared
    and the group index is per rollout. The explicit value is carried verbatim.
    """
    key = peven.runKey("task-003#g0")

    assert key.value == "task-003#g0"
    assert key == peven.runKey("task-003#g0")


def test_004() -> None:
    """Explicit run key values must be non-empty strings."""
    with pytest.raises(ValueError):
        peven.runKey("")
    with pytest.raises(TypeError):
        peven.runKey(123)
