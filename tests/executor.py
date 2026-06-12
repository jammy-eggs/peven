from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """The executor decorator records the transport-facing executor name.

    This slice does not add a registry, worker invocation, or result validation.
    It only gives imported Python callables a stable name that transitions can
    reference later.
    """

    @peven.executor("sim")
    def sim(ctx):
        return {"done": []}

    assert sim.__executor__ == "sim"
    assert sim("ctx") == {"done": []}


def test_002() -> None:
    """Executor names must be explicit strings because workers route by name."""
    with pytest.raises(TypeError, match="executor name"):
        peven.executor(1)
    with pytest.raises(ValueError, match="executor name"):
        peven.executor("")


def test_003() -> None:
    """The executor decorator should preserve async callables unchanged."""

    @peven.executor("agent")
    async def agent(ctx):
        return {"done": []}

    assert agent.__executor__ == "agent"


def test_004() -> None:
    """Only callables can be tagged as executors."""
    with pytest.raises(TypeError, match="callables"):
        peven.executor("bad")(object())
