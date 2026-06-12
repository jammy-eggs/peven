from __future__ import annotations

import asyncio

import pytest

import peven
from peven.worker import Worker, ipc
from peven.worker.worker import encodeOutputs


@peven.executor("echo")
async def echo(ctx, store):
    store["calls"] = store.get("calls", 0) + 1
    token = ctx.inputs["sim_input"][0]
    return {
        "done": [peven.token(color="state", runKey=ctx.bundle.runKey, payload=token.payload)]
    }


@peven.executor("fanout")
async def fanout(ctx, store):
    runKey = ctx.bundle.runKey
    return {
        "candidates": [
            peven.token(color="sample", runKey=runKey, payload="a"),
            peven.token(color="sample", runKey=runKey, payload="b"),
        ]
    }


def callMessage(
    callId: int = 7,
    executorName: str = "echo",
    runKey: str = "task-003#g0",
) -> dict:
    return {
        "kind": "executorCall",
        "callId": callId,
        "executorName": executorName,
        "ctx": {
            "bundle": {"transitionId": "solve", "runKey": runKey, "selectedKey": None},
            "firingId": 1,
            "attempt": 1,
            "inputs": {
                "sim_input": [
                    {"color": "state", "runKey": runKey, "payload": {"turn": 1}}
                ]
            },
        },
    }


def handle(worker: Worker, message: dict) -> dict:
    return asyncio.run(worker.handle(ipc.decode(ipc.encode(message))))


def test_001() -> None:
    """An executorCall round-trips bytes-in to an executorResult reply.

    This is the whole worker contract: decode the gateway's call, run the
    registered executor against the run's store, reply with wire-shaped
    token buckets carrying the bundle runKey.
    """
    worker = Worker("w0", [echo])
    worker.assign("task-003#g0", {})

    reply = handle(worker, callMessage())

    assert reply == {
        "kind": "executorResult",
        "callId": 7,
        "outputs": {
            "done": [
                {"color": "state", "runKey": "task-003#g0", "payload": {"turn": 1}}
            ]
        },
    }


def test_002() -> None:
    """A run key's store is one mutable object across its executor calls."""
    worker = Worker("w0", [echo])
    store: dict = {}
    worker.assign("task-003#g0", store)

    handle(worker, callMessage(callId=1))
    handle(worker, callMessage(callId=2))

    assert store["calls"] == 2


def test_003() -> None:
    """One firing may emit multiple output tokens into one place."""
    worker = Worker("w0", [fanout])
    worker.assign("task-003#g0")

    reply = handle(worker, callMessage(executorName="fanout"))

    assert [token["payload"] for token in reply["outputs"]["candidates"]] == ["a", "b"]


def test_004() -> None:
    """Executor exceptions become executorError replies, never raises.

    The repr keeps the exception type visible across the wire, including
    exceptions constructed without a message.
    """

    @peven.executor("boom")
    async def boom(ctx, store):
        raise RuntimeError("bad tool")

    @peven.executor("mute")
    async def mute(ctx, store):
        raise ValueError()

    worker = Worker("w0", [boom, mute])
    worker.assign("task-003#g0")

    reply = handle(worker, callMessage(executorName="boom"))
    assert reply == {
        "kind": "executorError",
        "callId": 7,
        "error": "RuntimeError('bad tool')",
    }

    reply = handle(worker, callMessage(executorName="mute"))
    assert reply["error"] == "ValueError()"


def test_005() -> None:
    """Calls naming an unregistered executor fail as executorError replies."""
    worker = Worker("w0", [echo])
    worker.assign("task-003#g0")

    reply = handle(worker, callMessage(executorName="missing"))

    assert reply["kind"] == "executorError"
    assert "unknown executor missing" in reply["error"]


def test_006() -> None:
    """Calls for an unassigned run key fail as executorError replies.

    Run keys are sticky-routed to one owning worker; a call for a key this
    worker does not own is a routing fault the engine must see.
    """
    worker = Worker("w0", [echo])

    reply = handle(worker, callMessage())

    assert reply["kind"] == "executorError"
    assert "not assigned to worker w0" in reply["error"]


def test_007() -> None:
    """Executor outputs must be token buckets carrying the bundle runKey."""
    with pytest.raises(TypeError, match="dict of token lists"):
        encodeOutputs([peven.token(color="state", runKey="r")], "r")
    with pytest.raises(TypeError, match="places must be strings"):
        encodeOutputs({1: []}, "r")
    with pytest.raises(ValueError, match="places must be non-empty"):
        encodeOutputs({"": []}, "r")
    with pytest.raises(TypeError, match="must be a list"):
        encodeOutputs({"done": peven.token(color="state", runKey="r")}, "r")
    with pytest.raises(TypeError, match="must contain tokens"):
        encodeOutputs({"done": [{"color": "state", "runKey": "r"}]}, "r")
    with pytest.raises(ValueError, match="does not match bundle runKey"):
        encodeOutputs({"done": [peven.token(color="state", runKey="other")]}, "r")


def test_008() -> None:
    """Workers only accept async executors registered under unique names."""

    async def untagged(ctx, store):
        return {}

    @peven.executor("sync")
    def sync(ctx, store):
        return {}

    @peven.executor("echo")
    async def echoTwin(ctx, store):
        return {}

    with pytest.raises(TypeError, match="decorated with peven"):
        Worker("w0", [untagged])
    with pytest.raises(TypeError, match="must be an async function"):
        Worker("w0", [sync])
    with pytest.raises(ValueError, match="registered twice"):
        Worker("w0", [echo, echoTwin])
    with pytest.raises(ValueError, match="executors must be non-empty"):
        Worker("w0", [])
    with pytest.raises(ValueError, match="workerId must be non-empty"):
        Worker("", [echo])


def test_009() -> None:
    """Assignment is exclusive while held and evicted on release."""
    worker = Worker("w0", [echo])
    worker.assign("task-003#g0", {"db": 1})

    with pytest.raises(ValueError, match="already assigned"):
        worker.assign("task-003#g0")

    worker.release("task-003#g0")
    with pytest.raises(ValueError, match="not assigned"):
        worker.release("task-003#g0")

    worker.assign("task-003#g0")
    assert worker.stores["task-003#g0"] is None
