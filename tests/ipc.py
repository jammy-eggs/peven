from __future__ import annotations

import pytest

import peven
from peven.worker import ipc
from peven.worker.context import Bundle


def test_001() -> None:
    """Every outbound worker message round-trips through the msgpack codec.

    PevenTransport.jl decodes these exact shapes; field names and kinds are
    the wire contract from src/ipc.jl.
    """
    messages = [
        ipc.workerHello("worker-1"),
        ipc.workerGoodbye("worker-1"),
        ipc.assign("task-003#g0", "worker-1"),
        ipc.release("task-003#g0"),
        ipc.executorResult(7, {"done": [{"color": "state", "runKey": "task-003#g0", "payload": None}]}),
        ipc.executorError(7, "boom"),
    ]

    for message in messages:
        assert ipc.decode(ipc.encode(message)) == message


def test_002() -> None:
    """Builder kinds and fields match the PevenTransport contract verbatim."""
    assert ipc.workerHello("w") == {"kind": "workerHello", "workerId": "w", "protocol": 1}
    assert ipc.workerGoodbye("w") == {"kind": "workerGoodbye", "workerId": "w"}
    assert ipc.assign("r", "w") == {"kind": "assign", "runKey": "r", "workerId": "w"}
    assert ipc.release("r") == {"kind": "release", "runKey": "r"}
    assert ipc.executorResult(1, {}) == {
        "kind": "executorResult",
        "callId": 1,
        "outputs": {},
    }
    assert ipc.executorError(1, "e") == {
        "kind": "executorError",
        "callId": 1,
        "error": "e",
    }


def test_003() -> None:
    """Payloads above the 8 MiB cap are rejected on encode and decode."""
    oversized = {"kind": "executorError", "callId": 1, "error": "x" * ipc.maxPayloadBytes}

    with pytest.raises(ipc.IpcError, match="exceeds"):
        ipc.encode(oversized)
    with pytest.raises(ipc.IpcError, match="exceeds"):
        ipc.decode(b"\x00" * (ipc.maxPayloadBytes + 1))


def test_004() -> None:
    """Call ids are strictly positive integers, never bools.

    callId correlates one executor call with one reply. Python bools satisfy
    isinstance int checks, so the exact-type rule guards the bool trap.
    """
    with pytest.raises(ipc.IpcError, match="positive"):
        ipc.executorError(0, "boom")
    with pytest.raises(ipc.IpcError, match="positive"):
        ipc.executorResult(-1, {})
    with pytest.raises(ipc.IpcError, match="integer"):
        ipc.executorResult(True, {})
    with pytest.raises(ipc.IpcError, match="integer"):
        ipc.executorResult("1", {})


def test_005() -> None:
    """Identity and key fields must be non-empty strings."""
    with pytest.raises(ipc.IpcError, match="workerId must be non-empty"):
        ipc.workerHello("")
    with pytest.raises(ipc.IpcError, match="workerId must be a string"):
        ipc.workerGoodbye(1)
    with pytest.raises(ipc.IpcError, match="runKey must be non-empty"):
        ipc.assign("", "w")
    with pytest.raises(ipc.IpcError, match="runKey must be non-empty"):
        ipc.release("")
    with pytest.raises(ipc.IpcError, match="error must be non-empty"):
        ipc.executorError(1, "")


def test_006() -> None:
    """Executor outputs must be a map of token buckets."""
    with pytest.raises(ipc.IpcError, match="outputs must be a map"):
        ipc.executorResult(1, [("done", [])])


def executorCallMessage() -> dict:
    """The exact shape PevenTransport.jl src/ipc.jl executorCall emits."""
    return {
        "kind": "executorCall",
        "callId": 7,
        "executorName": "agent",
        "ctx": {
            "bundle": {
                "transitionId": "solve",
                "runKey": "task-003#g0",
                "selectedKey": None,
            },
            "firingId": 12,
            "attempt": 1,
            "inputs": {
                "sim_input": [
                    {"color": "state", "runKey": "task-003#g0", "payload": {"turn": 3}},
                ],
                "db": [
                    {"color": "db", "runKey": "task-003#g0"},
                ],
            },
        },
    }


def test_007() -> None:
    """An executorCall decodes through the byte path into an ExecutionContext.

    Tokens decode into the canonical authoring Token, and a token row without
    a payload field defaults to None, matching Julia's get(token, "payload",
    nothing).
    """
    callId, executorName, ctx = ipc.decodeExecutorCall(
        ipc.decode(ipc.encode(executorCallMessage()))
    )

    assert callId == 7
    assert executorName == "agent"
    assert ctx.bundle == Bundle(
        transitionId="solve", runKey="task-003#g0", selectedKey=None
    )
    assert ctx.firingId == 12
    assert ctx.attempt == 1
    assert ctx.inputs["sim_input"] == (
        peven.token(color="state", runKey="task-003#g0", payload={"turn": 3}),
    )
    assert ctx.inputs["db"] == (peven.token(color="db", runKey="task-003#g0", payload=None),)


def test_008() -> None:
    """Executor call envelopes reject wrong kinds and malformed headers."""
    with pytest.raises(ipc.IpcError, match="expected kind"):
        ipc.decodeExecutorCall({"kind": "workerReady", "workerId": "w"})
    with pytest.raises(ipc.IpcError, match="message must be a map"):
        ipc.decodeExecutorCall("executorCall")

    noCallId = executorCallMessage()
    del noCallId["callId"]
    with pytest.raises(ipc.IpcError, match="callId must be an integer"):
        ipc.decodeExecutorCall(noCallId)

    emptyName = executorCallMessage()
    emptyName["executorName"] = ""
    with pytest.raises(ipc.IpcError, match="executorName must be non-empty"):
        ipc.decodeExecutorCall(emptyName)


def test_009() -> None:
    """Context payloads reject structural drift from the Peven.jl shape."""
    noBundle = executorCallMessage()
    del noBundle["ctx"]["bundle"]
    with pytest.raises(ipc.IpcError, match="missing required field 'bundle'"):
        ipc.decodeExecutorCall(noBundle)

    boolFiring = executorCallMessage()
    boolFiring["ctx"]["firingId"] = True
    with pytest.raises(ipc.IpcError, match="firingId must be an integer"):
        ipc.decodeExecutorCall(boolFiring)

    listInputs = executorCallMessage()
    listInputs["ctx"]["inputs"] = []
    with pytest.raises(ipc.IpcError, match="inputs must be a map"):
        ipc.decodeExecutorCall(listInputs)

    tupleBucket = executorCallMessage()
    tupleBucket["ctx"]["inputs"]["sim_input"] = {}
    with pytest.raises(ipc.IpcError, match="token buckets must be lists"):
        ipc.decodeExecutorCall(tupleBucket)

    badToken = executorCallMessage()
    badToken["ctx"]["inputs"]["sim_input"] = ["token"]
    with pytest.raises(ipc.IpcError, match="token must be a map"):
        ipc.decodeExecutorCall(badToken)

    emptyColor = executorCallMessage()
    emptyColor["ctx"]["inputs"]["sim_input"] = [{"color": "", "runKey": "r"}]
    with pytest.raises(ipc.IpcError, match="color must be non-empty"):
        ipc.decodeExecutorCall(emptyColor)


def test_010() -> None:
    """Control replies from the gateway decode to their identity fields."""
    assert ipc.decodeWorkerReady({"kind": "workerReady", "workerId": "w"}) == "w"
    assert ipc.decodeWorkerGone({"kind": "workerGone", "workerId": "w"}) == "w"
    assert ipc.decodeAssigned(
        {"kind": "assigned", "runKey": "r", "workerId": "w"}
    ) == ("r", "w")
    assert ipc.decodeReleased({"kind": "released", "runKey": "r"}) == "r"
    assert ipc.decodeGatewayError({"kind": "gatewayError", "error": "boom"}) == "boom"


def test_011() -> None:
    """Control replies reject wrong kinds and empty identity fields."""
    with pytest.raises(ipc.IpcError, match="expected kind"):
        ipc.decodeWorkerReady({"kind": "assigned", "runKey": "r", "workerId": "w"})
    with pytest.raises(ipc.IpcError, match="workerId must be non-empty"):
        ipc.decodeWorkerReady({"kind": "workerReady", "workerId": ""})
    with pytest.raises(ipc.IpcError, match="missing required field 'runKey'"):
        ipc.decodeAssigned({"kind": "assigned", "workerId": "w"})
    with pytest.raises(ipc.IpcError, match="error must be non-empty"):
        ipc.decodeGatewayError({"kind": "gatewayError", "error": ""})


def test_012() -> None:
    """Control builders match the ipc.jl contract: knobs only when given."""
    assert ipc.loadNet({"name": "n"}) == {"kind": "loadNet", "net": {"name": "n"}}
    assert ipc.fire("task-003", "n", {"tokensByPlace": {}}) == {
        "kind": "fire",
        "fireId": "task-003",
        "net": "n",
        "marking": {"tokensByPlace": {}},
    }
    assert ipc.fire("task-003", "n", {"tokensByPlace": {}}, fuse=50, maxConcurrency=4) == {
        "kind": "fire",
        "fireId": "task-003",
        "net": "n",
        "marking": {"tokensByPlace": {}},
        "fuse": 50,
        "maxConcurrency": 4,
    }

    with pytest.raises(ipc.IpcError, match="net must be a map"):
        ipc.loadNet([("name", "n")])
    with pytest.raises(ipc.IpcError, match="fireId must be non-empty"):
        ipc.fire("", "n", {})
    with pytest.raises(ipc.IpcError, match="net must be non-empty"):
        ipc.fire("task-003", "", {})
    with pytest.raises(ipc.IpcError, match="marking must be a map"):
        ipc.fire("task-003", "n", None)


def test_013() -> None:
    """netLoaded and fireFinished decode their reply fields.

    fireFinished error is nil on success and a non-empty string when the
    engine threw — the gateway always sends the terminal message either way.
    """
    assert ipc.decodeNetLoaded({"kind": "netLoaded", "name": "n"}) == "n"
    assert ipc.decodeFireFinished(
        {"kind": "fireFinished", "fireId": "task-003", "error": None}
    ) == ("task-003", None)
    assert ipc.decodeFireFinished(
        {"kind": "fireFinished", "fireId": "task-003", "error": "boom"}
    ) == ("task-003", "boom")

    with pytest.raises(ipc.IpcError, match="name must be non-empty"):
        ipc.decodeNetLoaded({"kind": "netLoaded", "name": ""})
    with pytest.raises(ipc.IpcError, match="error must be non-empty"):
        ipc.decodeFireFinished({"kind": "fireFinished", "fireId": "f", "error": ""})


def runFinishedMessage() -> dict:
    """The exact shape ipc.jl runFinished emits for a completed run."""
    return {
        "kind": "runFinished",
        "fireId": "task-003",
        "result": {
            "runKey": "task-003#g0",
            "status": "completed",
            "error": None,
            "reason": None,
            "trace": [
                {
                    "bundle": {
                        "transitionId": "solve",
                        "runKey": "task-003#g0",
                        "selectedKey": None,
                    },
                    "firingId": 1,
                    "status": "completed",
                    "outputs": [
                        {"color": "draft", "runKey": "task-003#g0", "payload": "4"}
                    ],
                    "error": None,
                    "attempts": 1,
                },
            ],
            "finalMarking": {
                "tokensByPlace": {
                    "done": [
                        {"color": "answer", "runKey": "task-003#g0", "payload": "4"}
                    ]
                }
            },
        },
    }


def test_014() -> None:
    """runFinished decodes through the byte path into a typed RunResult.

    The engine's RunResult crosses field for field; trace entries reuse the
    bundle and token shapes, and finalMarking is canonical token buckets.
    """
    fireId, result = ipc.decodeRunFinished(
        ipc.decode(ipc.encode(runFinishedMessage()))
    )

    assert fireId == "task-003"
    assert result.runKey == "task-003#g0"
    assert result.status == "completed"
    assert result.error is None
    assert result.reason is None
    step = result.trace[0]
    assert step.bundle == Bundle(
        transitionId="solve", runKey="task-003#g0", selectedKey=None
    )
    assert step.firingId == 1
    assert step.attempts == 1
    assert step.outputs == (
        peven.token(color="draft", runKey="task-003#g0", payload="4"),
    )
    assert result.finalMarking == {
        "done": (peven.token(color="answer", runKey="task-003#g0", payload="4"),)
    }


def test_015() -> None:
    """Run results reject structural drift from the ipc.jl shape."""
    noTrace = runFinishedMessage()
    del noTrace["result"]["trace"]
    with pytest.raises(ipc.IpcError, match="missing required field 'trace'"):
        ipc.decodeRunFinished(noTrace)

    boolFiring = runFinishedMessage()
    boolFiring["result"]["trace"][0]["firingId"] = True
    with pytest.raises(ipc.IpcError, match="firingId must be an integer"):
        ipc.decodeRunFinished(boolFiring)

    mapOutputs = runFinishedMessage()
    mapOutputs["result"]["trace"][0]["outputs"] = {}
    with pytest.raises(ipc.IpcError, match="outputs must be a list"):
        ipc.decodeRunFinished(mapOutputs)

    noMarking = runFinishedMessage()
    del noMarking["result"]["finalMarking"]
    with pytest.raises(ipc.IpcError, match="missing required field 'finalMarking'"):
        ipc.decodeRunFinished(noMarking)
