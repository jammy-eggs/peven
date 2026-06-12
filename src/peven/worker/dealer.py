"""ZMQ DEALER shell around the worker core.

Liveness is ZMTP-level and gateway-owned: the ROUTER heartbeats, libzmq
answers automatically, and a dropped socket means this worker is dead.
Reconnection is disabled so death is final; the pool restarts a fresh
worker under a new workerId.
"""

from __future__ import annotations

import zmq
import zmq.asyncio

from peven.worker import ipc
from peven.worker.worker import Worker


def workerSocket(context: zmq.Context) -> zmq.Socket:
    socket = context.socket(zmq.DEALER)
    socket.setsockopt(zmq.RECONNECT_IVL, -1)
    socket.setsockopt(zmq.LINGER, 0)
    return socket


async def runWorker(endpoint: str, worker: Worker) -> None:
    context = zmq.asyncio.Context()
    socket = workerSocket(context)
    socket.connect(endpoint)
    try:
        await socket.send(ipc.encode(ipc.workerHello(worker.workerId)))
        ipc.decodeWorkerReady(ipc.decode(await socket.recv()))

        for runKey in worker.stores:
            await socket.send(ipc.encode(ipc.assign(runKey, worker.workerId)))
            ipc.decodeAssigned(ipc.decode(await socket.recv()))

        while True:
            message = ipc.decode(await socket.recv())
            if type(message) is dict and message.get("kind") == "gatewayError":
                raise ipc.IpcError(ipc.decodeGatewayError(message))
            await socket.send(ipc.encode(await worker.handle(message)))
    finally:
        socket.close()
        context.term()
