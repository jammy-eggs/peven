"""Worker process pool.

Each worker is its own OS process: the GIL stays per-worker and mutable
rollout state stays process-local. workerIds embed the pid so a restarted
worker is a new identity, per the liveness contract. buildWorker must be
a module-level callable; it is imported by name inside the child process,
which is the only place a Worker and its stores can be constructed.
"""

from __future__ import annotations

import asyncio
import multiprocessing
import os
from collections.abc import Callable

from peven.worker.dealer import runWorker
from peven.worker.worker import Worker


def workerProcess(endpoint: str, buildWorker: Callable, runKeys: list[str]) -> None:
    workerId = f"worker-{os.getpid()}"
    asyncio.run(runWorker(endpoint, buildWorker(workerId, runKeys)))


def startWorkers(
    endpoint: str,
    buildWorker: Callable[[str, list[str]], Worker],
    partitions: list[list[str]],
) -> list[multiprocessing.Process]:
    if type(partitions) is not list:
        raise TypeError("worker partitions must be a list")
    if not partitions:
        raise ValueError("worker partitions must be non-empty")

    spawn = multiprocessing.get_context("spawn")
    processes = []
    for runKeys in partitions:
        process = spawn.Process(
            target=workerProcess,
            args=(endpoint, buildWorker, list(runKeys)),
            daemon=True,
        )
        process.start()
        processes.append(process)
    return processes


def stopWorkers(processes: list[multiprocessing.Process]) -> None:
    for process in processes:
        process.terminate()
    for process in processes:
        process.join()
