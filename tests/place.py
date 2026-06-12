from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """A bare place declaration records only topology metadata.

    Initial rollout state is intentionally absent here. Tokens enter places
    through the marking API later, not through place declarations.
    """
    place = peven.place()

    assert place.terminal is False
    assert place.capacity is None


def test_002() -> None:
    """Terminal and capacity metadata are preserved without runtime behavior.

    `terminal` records authoring intent for later transition validation, while
    `capacity` mirrors the Julia place field without adding Python execution.
    """
    place = peven.place(terminal=True, capacity=1)

    assert place.terminal is True
    assert place.capacity == 1


def test_003() -> None:
    """The package root exposes the constructor, not a duplicate public type."""
    assert not hasattr(peven, "Place")


def test_004() -> None:
    """Separate place declarations are distinct authored nodes.

    Places are abstract net nodes, so equality follows declaration identity
    instead of treating matching metadata as the same place.
    """
    assert peven.place() != peven.place()


def test_005() -> None:
    """Terminal intent must be explicit instead of inherited from truthiness."""
    with pytest.raises(TypeError, match="terminal"):
        peven.place(terminal=1)


def test_006() -> None:
    """Capacity accepts only positive integer bounds or no bound."""
    with pytest.raises(TypeError, match="capacity"):
        peven.place(capacity=True)
    with pytest.raises(TypeError, match="capacity"):
        peven.place(capacity="1")
    with pytest.raises(ValueError, match="capacity"):
        peven.place(capacity=0)
