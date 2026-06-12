from __future__ import annotations

import peven


def test_001() -> None:
    """The public surface is one canonical list of authoring constructors.

    This is the only test that asserts the full export list. Domain tests
    assert their own non-exports; adding a public name means updating exactly
    this contract.
    """
    assert peven.__all__ == [
        "env",
        "executor",
        "gateway",
        "initialMarking",
        "mark",
        "net",
        "place",
        "runKey",
        "token",
        "transition",
    ]
    for name in peven.__all__:
        assert hasattr(peven, name)
