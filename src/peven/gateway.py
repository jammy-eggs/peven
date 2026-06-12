"""Trainer-facing gateway session.

gateway() spawns PevenTransport.serve and owns its lifetime; load() sends
the lowered net; fire() streams typed RunResults as rollouts finish.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import signal
import socket
import subprocess
from collections.abc import Callable
from contextlib import suppress
from uuid import uuid4

import zmq
import zmq.asyncio

from peven.marking import Marking
from peven.net import net
from peven.worker import ipc
from peven.worker.pool import startWorkers, stopWorkers


class Gateway:
    def __init__(self, buildWorker: Callable, workers: int, project: object) -> None:
        if not callable(buildWorker):
            raise TypeError("gateway buildWorker must be callable")
        if type(workers) is not int:
            raise TypeError("gateway workers must be an int")
        if workers < 1:
            raise ValueError("gateway workers must be greater than 0")
        self.buildWorker = buildWorker
        self.workers = workers
        self.project = project
        self.endpoint = None
        self.process = None
        self.context = None
        self.control = None
        self.netName = None

    async def __aenter__(self) -> Gateway:
        julia = shutil.which("julia")
        if julia is None:
            raise RuntimeError("julia not found; install it via juliaup")

        self.endpoint = f"tcp://127.0.0.1:{freePort()}"
        project = self.project if self.project is not None else "@peven"
        command = [
            julia,
            "--threads=2",
            f"--project={project}",
            "-e",
            "using PevenTransport; PevenTransport.serve(ARGS[1])",
            self.endpoint,
        ]
        self.process = subprocess.Popen(command, start_new_session=True)

        self.context = zmq.asyncio.Context()
        self.control = self.context.socket(zmq.DEALER)
        self.control.connect(self.endpoint)
        return self

    async def load(self, envClass: type) -> None:
        lowered = net(envClass).lower()
        await self.control.send(ipc.encode(ipc.loadNet(lowered)))
        reply = await self.recvControl(self.control)
        if type(reply) is dict and reply.get("kind") == "gatewayError":
            raise ipc.IpcError(ipc.decodeGatewayError(reply))
        ipc.decodeNetLoaded(reply)
        self.netName = lowered["name"]

    async def recvControl(self, socket: zmq.asyncio.Socket) -> object:
        while True:
            try:
                return ipc.decode(await asyncio.wait_for(socket.recv(), timeout=1))
            except TimeoutError:
                if self.process.poll() is not None:
                    raise RuntimeError(
                        "the gateway process exited; on first use this usually "
                        "means PevenTransport is missing — run: peven setup"
                    ) from None

    async def fire(
        self,
        marking: Marking,
        *,
        fuse: int | None = None,
        maxConcurrency: int | None = None,
    ):
        if self.netName is None:
            raise ValueError("no net loaded; call load first")
        lowered = marking.lower()
        runKeys = list(
            dict.fromkeys(
                token["runKey"]
                for bucket in lowered["tokensByPlace"].values()
                for token in bucket
            )
        )
        hands = [
            hand
            for hand in (runKeys[i :: self.workers] for i in range(self.workers))
            if hand
        ]

        fireId = uuid4().hex
        control = self.context.socket(zmq.DEALER)
        control.connect(self.endpoint)
        workers = startWorkers(self.endpoint, self.buildWorker, hands)
        try:
            while True:
                await control.send(
                    ipc.encode(
                        ipc.fire(fireId, self.netName, lowered, fuse, maxConcurrency)
                    )
                )
                message = await self.recvControl(control)
                if message.get("kind") != "fireFinished":
                    break
                _, error = ipc.decodeFireFinished(message)
                if error is None:
                    return
                if not error.startswith("no worker assigned"):
                    raise ipc.IpcError(error)
                await asyncio.sleep(0.05)

            while message.get("kind") == "runFinished":
                yield ipc.decodeRunFinished(message)[1]
                message = await self.recvControl(control)

            _, error = ipc.decodeFireFinished(message)
            if error is not None:
                raise ipc.IpcError(error)
        finally:
            stopWorkers(workers)
            control.close(0)

    async def __aexit__(self, *exc: object) -> None:
        self.control.close(0)
        self.context.term()
        with suppress(ProcessLookupError):
            os.killpg(self.process.pid, signal.SIGKILL)
        self.process.wait()


def gateway(
    buildWorker: Callable, *, workers: int = 1, project: object = None
) -> Gateway:
    return Gateway(buildWorker, workers, project)


def freePort() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]
