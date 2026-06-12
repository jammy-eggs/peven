from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """Env finalization records class-body places by authored name.

    A place object only stores place metadata. The class attribute name is the
    authored place id, and env owns that name-to-place map because naming is a
    net-level concern.
    """

    @peven.env("airline")
    class Airline:
        start = peven.place()
        done = peven.place(terminal=True)
        finish = peven.transition(inputs=["start"], outputs=["done"], executor="finish")

    assert Airline.__env__ == "airline"
    assert Airline.__places__ == {
        "start": Airline.start,
        "done": Airline.done,
    }
    assert Airline.__transitions__ == {"finish": Airline.finish}
    assert Airline.__places__["done"].terminal is True
    assert Airline.__name__ == "Airline"


def test_002() -> None:
    """Env names must be explicit strings because they become serialized ids."""
    with pytest.raises(TypeError, match="env name"):
        peven.env(1)
    with pytest.raises(ValueError, match="env name"):
        peven.env("")


def test_003() -> None:
    """The env decorator finalizes classes only."""
    with pytest.raises(TypeError, match="classes"):
        peven.env("bad")(object())


def test_004() -> None:
    """Empty env classes should fail before later passes need special cases."""
    with pytest.raises(ValueError, match="at least one place"):

        @peven.env("empty")
        class Empty:
            pass


def test_005() -> None:
    """Place reuse is a net-level ambiguity, not place-local state.

    Assigning one place object to two class names would lower one declaration to
    two different Julia place ids, so env rejects it while Place remains only
    place metadata.
    """
    shared = peven.place()

    with pytest.raises(ValueError, match="cannot be reused"):

        @peven.env("duplicate")
        class Duplicate:
            left = shared
            right = shared


def test_006() -> None:
    """Env classes need at least one transition to become a net fragment."""
    with pytest.raises(ValueError, match="at least one transition"):

        @peven.env("places_only")
        class PlacesOnly:
            start = peven.place()
            done = peven.place(terminal=True)


def test_007() -> None:
    """Transition reuse is a net-level ambiguity, matching place reuse."""
    shared = peven.transition(inputs=["start"], outputs=["done"], executor="finish")

    with pytest.raises(ValueError, match="transition declarations cannot be reused"):

        @peven.env("duplicate_transition")
        class DuplicateTransition:
            start = peven.place()
            done = peven.place(terminal=True)
            left = shared
            right = shared


def test_008() -> None:
    """Transition inputs must reference places declared on the same env class."""
    with pytest.raises(ValueError, match="input missing is not a place"):

        @peven.env("missing_input")
        class MissingInput:
            done = peven.place(terminal=True)
            finish = peven.transition(
                inputs=["missing"],
                outputs=["done"],
                executor="finish",
            )


def test_009() -> None:
    """Transition outputs must reference places declared on the same env class."""
    with pytest.raises(ValueError, match="output missing is not a place"):

        @peven.env("missing_output")
        class MissingOutput:
            start = peven.place()
            finish = peven.transition(
                inputs=["start"],
                outputs=["missing"],
                executor="finish",
            )


def test_010() -> None:
    """Terminal places may receive tokens but must not be consumed.

    `terminal=True` is authoring intent for a final sink. Env validation can
    enforce that intent without introducing runtime behavior.
    """
    with pytest.raises(ValueError, match="cannot consume terminal place done"):

        @peven.env("consume_terminal")
        class ConsumeTerminal:
            done = peven.place(terminal=True)
            next = peven.place()
            restart = peven.transition(
                inputs=["done"],
                outputs=["next"],
                executor="restart",
            )


def test_011() -> None:
    """A transition may loop through a non-terminal place."""

    @peven.env("loop")
    class Loop:
        state = peven.place()
        step = peven.transition(
            inputs=["state"],
            outputs=["state"],
            executor="step",
        )

    assert Loop.__transitions__ == {"step": Loop.step}
