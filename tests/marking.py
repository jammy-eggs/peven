from __future__ import annotations

import pytest

import peven


def test_001() -> None:
    """Marking normalizes initial token rows into Peven.jl-shaped buckets."""
    runKey = peven.runKey()
    state = {"kind": "state", "tid": "task-1"}
    db = {"kind": "db", "tid": "task-1"}

    marking = peven.initialMarking(
        runKey=runKey,
        tokens=[
            ("sim_input", "state", state),
            ("db", "db", db),
        ],
    )

    stateToken = marking.tokensByPlace["sim_input"][0]
    dbToken = marking.tokensByPlace["db"][0]
    assert stateToken.color == "state"
    assert stateToken.runKey == runKey.value
    assert stateToken.payload is state
    assert dbToken.color == "db"
    assert dbToken.runKey == runKey.value
    assert dbToken.payload is db


def test_002() -> None:
    """Multiple token rows for one place preserve insertion order."""
    marking = peven.initialMarking(
        runKey=peven.runKey(),
        tokens=[
            ("candidate", "sample", "a"),
            ("candidate", "sample", "b"),
        ],
    )

    assert [token.payload for token in marking.tokensByPlace["candidate"]] == ["a", "b"]


def test_003() -> None:
    """Marking and Token types stay private; token() is the one constructor."""
    assert not hasattr(peven, "Marking")
    assert not hasattr(peven, "Token")


def test_004() -> None:
    """Run keys must be explicit because they partition concurrent runs."""
    with pytest.raises(TypeError, match="runKey"):
        peven.initialMarking(runKey="run-1", tokens=[("start", "default", "payload")])


def test_005() -> None:
    """Token rows must be supplied as a non-empty list."""
    with pytest.raises(TypeError, match="tokens"):
        peven.initialMarking(
            runKey=peven.runKey(),
            tokens=(("start", "default", "payload"),),
        )
    with pytest.raises(ValueError, match="tokens"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[])


def test_006() -> None:
    """Each token row must be a three-tuple."""
    with pytest.raises(TypeError, match="rows"):
        peven.initialMarking(
            runKey=peven.runKey(),
            tokens=[["start", "default", "payload"]],
        )
    with pytest.raises(ValueError, match="rows"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[("start", "payload")])


def test_007() -> None:
    """Token place ids must be explicit non-empty strings."""
    with pytest.raises(TypeError, match="place"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[(1, "default", "payload")])
    with pytest.raises(ValueError, match="place"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[("", "default", "payload")])


def test_008() -> None:
    """Token colors must be explicit non-empty strings."""
    with pytest.raises(TypeError, match="color"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[("start", 1, "payload")])
    with pytest.raises(ValueError, match="color"):
        peven.initialMarking(runKey=peven.runKey(), tokens=[("start", "", "payload")])


def test_009() -> None:
    """Initial marking lower emits Peven.jl token buckets."""
    runKey = peven.runKey()
    marking = peven.initialMarking(
        runKey=runKey,
        tokens=[
            ("sim_input", "state", {"task": 1}),
            ("db", "db", None),
        ],
    )

    assert marking.lower() == {
        "tokensByPlace": {
            "sim_input": [
                {
                    "color": "state",
                    "runKey": runKey.value,
                    "payload": {"task": 1},
                },
            ],
            "db": [
                {
                    "color": "db",
                    "runKey": runKey.value,
                    "payload": None,
                },
            ],
        }
    }


def test_010() -> None:
    """Mark combines per-run markings into one group marking.

    A GRPO-style group is one topology with G run keys. Each run key builds its
    own initial marking, and mark stitches them into the single marking sent to
    Julia, preserving per-place token order and per-run runKeys verbatim.
    """
    g0 = peven.runKey("task-003#g0")
    g1 = peven.runKey("task-003#g1")
    marking = peven.mark(
        peven.initialMarking(runKey=g0, tokens=[("sim_input", "state", "s0")]),
        peven.initialMarking(runKey=g1, tokens=[("sim_input", "state", "s1")]),
    )

    tokens = marking.tokensByPlace["sim_input"]
    assert [token.runKey for token in tokens] == [g0.value, g1.value]
    assert [token.payload for token in tokens] == ["s0", "s1"]


def test_011() -> None:
    """Mark with one marking round-trips it unchanged."""
    marking = peven.initialMarking(
        runKey=peven.runKey(),
        tokens=[("db", "db", None)],
    )

    assert peven.mark(marking) == marking


def test_012() -> None:
    """Mark requires at least one marking and rejects non-marking arguments."""
    with pytest.raises(ValueError, match="at least one"):
        peven.mark()
    with pytest.raises(TypeError, match="markings"):
        peven.mark({"tokensByPlace": {}})


def test_013() -> None:
    """A merged group marking lowers with every run key intact."""
    g0 = peven.runKey("task-003#g0")
    g1 = peven.runKey("task-003#g1")
    marking = peven.mark(
        peven.initialMarking(runKey=g0, tokens=[("db", "db", None)]),
        peven.initialMarking(runKey=g1, tokens=[("db", "db", None)]),
    )

    lowered = marking.lower()
    assert [token["runKey"] for token in lowered["tokensByPlace"]["db"]] == [
        g0.value,
        g1.value,
    ]


def test_014() -> None:
    """token() is the public constructor executors use for output tokens.

    Executors build output tokens against the wire runKey string from
    ctx.bundle.runKey, so token() takes a plain string, not a RunKey.
    """
    built = peven.token(color="state", runKey="task-003#g0", payload={"turn": 1})

    assert built.color == "state"
    assert built.runKey == "task-003#g0"
    assert built.payload == {"turn": 1}
    assert peven.token(color="db", runKey="r").payload is None

    with pytest.raises(ValueError, match="color"):
        peven.token(color="", runKey="r")
    with pytest.raises(TypeError, match="runKey"):
        peven.token(color="state", runKey=peven.runKey())
