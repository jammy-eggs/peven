from __future__ import annotations

import asyncio

import pytest
import zmq
import zmq.asyncio

import peven
from peven.worker import Worker, ipc
from peven.worker.dealer import runWorker, workerSocket


@peven.executor("echo")
async def echo(ctx, store):
    return {
        "done": [peven.token(color="state", runKey=ctx.bundle.runKey, payload="ok")]
    }


def buildWorker() -> Worker:
    worker = Worker("w0", [echo])
    worker.assign("task-003#g0", {})
    return worker


async def handshake(router: zmq.asyncio.Socket) -> bytes:
    identity, payload = await router.recv_multipart()
    assert ipc.decode(payload) == {
        "kind": "workerHello",
        "workerId": "w0",
        "protocol": 1,
    }
    await router.send_multipart(
        [identity, ipc.encode({"kind": "workerReady", "workerId": "w0"})]
    )

    identity, payload = await router.recv_multipart()
    assert ipc.decode(payload) == {
        "kind": "assign",
        "runKey": "task-003#g0",
        "workerId": "w0",
    }
    await router.send_multipart(
        [
            identity,
            ipc.encode({"kind": "assigned", "runKey": "task-003#g0", "workerId": "w0"}),
        ]
    )
    return identity


def executorCall(callId: int) -> dict:
    return {
        "kind": "executorCall",
        "callId": callId,
        "executorName": "echo",
        "ctx": {
            "bundle": {
                "transitionId": "solve",
                "runKey": "task-003#g0",
                "selectedKey": None,
            },
            "firingId": 1,
            "attempt": 1,
            "inputs": {
                "sim_input": [
                    {"color": "state", "runKey": "task-003#g0", "payload": None}
                ]
            },
        },
    }


async def withGateway(scenario) -> None:
    context = zmq.asyncio.Context()
    router = context.socket(zmq.ROUTER)
    port = router.bind_to_random_port("tcp://127.0.0.1")
    task = asyncio.ensure_future(runWorker(f"tcp://127.0.0.1:{port}", buildWorker()))
    try:
        await scenario(router, task)
    finally:
        if not task.done():
            task.cancel()
        try:
            await task
        except (asyncio.CancelledError, ipc.IpcError):
            pass
        router.close(0)
        context.term()


def test_001() -> None:
    """The shell handshakes, claims its runs, and serves executor calls.

    Over real TCP: workerHello carries the protocol version, every
    pre-assigned runKey is claimed and acked, and an executorCall comes
    back as a wire-shaped executorResult.
    """

    async def scenario(router, task):
        identity = await handshake(router)

        await router.send_multipart([identity, ipc.encode(executorCall(3))])
        _, payload = await router.recv_multipart()

        assert ipc.decode(payload) == {
            "kind": "executorResult",
            "callId": 3,
            "outputs": {
                "done": [{"color": "state", "runKey": "task-003#g0", "payload": "ok"}]
            },
        }

    asyncio.run(asyncio.wait_for(withGateway(scenario), timeout=10))


def test_002() -> None:
    """A gatewayError push terminates the shell with the gateway's message."""

    async def scenario(router, task):
        identity = await handshake(router)

        await router.send_multipart(
            [identity, ipc.encode({"kind": "gatewayError", "error": "rejected"})]
        )
        with pytest.raises(ipc.IpcError, match="rejected"):
            await asyncio.wait_for(task, timeout=5)

    asyncio.run(asyncio.wait_for(withGateway(scenario), timeout=10))


def test_003() -> None:
    """Worker sockets never auto-reconnect; a dropped socket is death.

    RECONNECT_IVL = -1 is a binding requirement of the liveness contract:
    the gateway treats disconnect as worker death, so a silent reconnect
    would resurrect a forgotten identity.
    """
    context = zmq.Context()
    socket = workerSocket(context)

    assert socket.getsockopt(zmq.RECONNECT_IVL) == -1
    assert socket.getsockopt(zmq.LINGER) == 0

    socket.close()
    context.term()
