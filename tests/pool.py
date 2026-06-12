from __future__ import annotations

import asyncio

import pytest
import zmq
import zmq.asyncio

import peven
from peven.worker import Worker, ipc
from peven.worker.pool import startWorkers, stopWorkers


@peven.executor("echo")
async def echo(ctx, store):
    return {}


def buildWorker(workerId: str, runKeys: list[str]) -> Worker:
    worker = Worker(workerId, [echo])
    for runKey in runKeys:
        worker.assign(runKey, {})
    return worker


def test_001() -> None:
    """startWorkers deals one partition of run keys to each spawned process.

    Worker identities are per-process-instance per the liveness contract,
    every run key in a worker's partition is claimed by that worker, and
    stopWorkers leaves no processes alive — disconnect is the designed
    shutdown path.
    """

    async def scenario():
        context = zmq.asyncio.Context()
        router = context.socket(zmq.ROUTER)
        port = router.bind_to_random_port("tcp://127.0.0.1")

        partitions = [["task-003#g0"], ["task-003#g1"]]
        processes = startWorkers(f"tcp://127.0.0.1:{port}", buildWorker, partitions)
        try:
            seen = set()
            claimed = set()
            for _ in range(4):
                identity, payload = await asyncio.wait_for(
                    router.recv_multipart(), timeout=20
                )
                message = ipc.decode(payload)
                if message["kind"] == "workerHello":
                    assert message["protocol"] == 1
                    seen.add(message["workerId"])
                    reply = {"kind": "workerReady", "workerId": message["workerId"]}
                else:
                    assert message["kind"] == "assign"
                    claimed.add(message["runKey"])
                    reply = {
                        "kind": "assigned",
                        "runKey": message["runKey"],
                        "workerId": message["workerId"],
                    }
                await router.send_multipart([identity, ipc.encode(reply)])

            assert seen == {f"worker-{process.pid}" for process in processes}
            assert claimed == {"task-003#g0", "task-003#g1"}
        finally:
            stopWorkers(processes)
            router.close(0)
            context.term()

        assert all(not process.is_alive() for process in processes)

    asyncio.run(asyncio.wait_for(scenario(), timeout=60))


def test_002() -> None:
    """Worker partitions are a non-empty list of run-key hands."""
    with pytest.raises(TypeError, match="partitions must be a list"):
        startWorkers("tcp://127.0.0.1:1", buildWorker, (["r"],))
    with pytest.raises(ValueError, match="partitions must be non-empty"):
        startWorkers("tcp://127.0.0.1:1", buildWorker, [])
