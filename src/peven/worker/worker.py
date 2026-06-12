"""Worker execution core.

A worker owns rollout state for its assigned run keys and executes
transition callbacks. handle() speaks decoded IPC messages only;
transport is layered on top of it.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from peven.marking import Token
from peven.worker import ipc
from peven.worker.context import ExecutionContext


class Worker:
    def __init__(self, workerId: str, executors: list[Callable]) -> None:
        if type(workerId) is not str:
            raise TypeError("worker workerId must be a string")
        if not workerId:
            raise ValueError("worker workerId must be non-empty")
        if type(executors) is not list:
            raise TypeError("worker executors must be a list")
        if not executors:
            raise ValueError("worker executors must be non-empty")

        registry: dict[str, Callable] = {}
        for fn in executors:
            name = getattr(fn, "__executor__", None)
            if name is None:
                raise TypeError("worker executors must be decorated with peven.executor")
            if not inspect.iscoroutinefunction(fn):
                raise TypeError(f"executor {name} must be an async function")
            if name in registry:
                raise ValueError(f"executor {name} is registered twice")
            registry[name] = fn

        self.workerId = workerId
        self.executors = registry
        self.stores: dict[str, object] = {}

    def assign(self, runKey: str, store: object = None) -> None:
        if type(runKey) is not str:
            raise TypeError("worker runKey must be a string")
        if not runKey:
            raise ValueError("worker runKey must be non-empty")
        if runKey in self.stores:
            raise ValueError(f"runKey {runKey} is already assigned")
        self.stores[runKey] = store

    def release(self, runKey: str) -> None:
        if runKey not in self.stores:
            raise ValueError(f"runKey {runKey} is not assigned")
        del self.stores[runKey]

    async def handle(self, message: object) -> dict:
        callId, executorName, ctx = ipc.decodeExecutorCall(message)
        try:
            outputs = await self.execute(executorName, ctx)
        except Exception as error:
            return ipc.executorError(callId, repr(error))
        return ipc.executorResult(callId, outputs)

    async def execute(self, executorName: str, ctx: ExecutionContext) -> dict:
        runKey = ctx.bundle.runKey
        if runKey not in self.stores:
            raise ValueError(f"runKey {runKey} is not assigned to worker {self.workerId}")

        fn = self.executors.get(executorName)
        if fn is None:
            raise ValueError(f"unknown executor {executorName}")

        outputs = await fn(ctx, self.stores[runKey])
        return encodeOutputs(outputs, runKey)


def encodeOutputs(outputs: object, runKey: str) -> dict:
    if type(outputs) is not dict:
        raise TypeError("executor outputs must be a dict of token lists by place")

    encoded: dict[str, list[dict]] = {}
    for place, tokens in outputs.items():
        if type(place) is not str:
            raise TypeError("executor output places must be strings")
        if not place:
            raise ValueError("executor output places must be non-empty")
        if type(tokens) is not list:
            raise TypeError(f"executor outputs for {place} must be a list")

        bucket = []
        for token in tokens:
            if type(token) is not Token:
                raise TypeError(f"executor outputs for {place} must contain tokens")
            if token.runKey != runKey:
                raise ValueError(
                    f"output token runKey {token.runKey} does not match bundle runKey {runKey}"
                )
            bucket.append(ipc.tokenMessage(token))
        encoded[place] = bucket

    return encoded
