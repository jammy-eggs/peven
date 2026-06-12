from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

import peven
from peven.worker import Worker


julia = shutil.which("julia")
transportProject = Path.home() / "peventransport"

pytestmark = pytest.mark.skipif(
    julia is None or not transportProject.exists(),
    reason="julia and ~/peventransport required",
)


@peven.env("e2e")
class E2E:
    prompt = peven.place()
    mid = peven.place()
    done = peven.place(terminal=True)
    solve = peven.transition(inputs=["prompt"], outputs=["mid"], executor="solve")
    judge = peven.transition(inputs=["mid"], outputs=["done"], executor="judge")


@peven.executor("solve")
async def solve(ctx, store):
    store["question"] = ctx.inputs["prompt"][0].payload["q"]
    return {"mid": [peven.token(color="draft", runKey=ctx.bundle.runKey, payload="4")]}


@peven.executor("judge")
async def judge(ctx, store):
    draft = ctx.inputs["mid"][0].payload
    return {
        "done": [peven.token(color="answer", runKey=ctx.bundle.runKey, payload=draft)]
    }


runKeys = ("task-e2e#g0", "task-e2e#g1")


def buildWorker(workerId: str, workerRunKeys: list[str]) -> Worker:
    worker = Worker(workerId, [solve, judge])
    for runKey in workerRunKeys:
        worker.assign(runKey, {})
    return worker


def test_001() -> None:
    """The public API drives the whole stack: gateway, load, fire, results.

    A two-hop net where the judge consumes a token the worker itself
    produced one hop earlier, run as a G=2 group in one worker's hand
    (fully sequential execution), through the real engine and gateway.
    """

    async def scenario():
        async with peven.gateway(
            buildWorker, workers=1, project=transportProject
        ) as gw:
            await gw.load(E2E)
            marking = peven.mark(
                *[
                    peven.initialMarking(
                        runKey=peven.runKey(key),
                        tokens=[("prompt", "question", {"q": "2+2"})],
                    )
                    for key in runKeys
                ]
            )

            results = {
                result.runKey: result async for result in gw.fire(marking, fuse=50)
            }

        assert set(results) == set(runKeys)
        for runKey in runKeys:
            result = results[runKey]
            assert result.status == "completed"
            assert [step.bundle.transitionId for step in result.trace] == [
                "solve",
                "judge",
            ]
            assert result.finalMarking["done"][0].payload == "4"

    asyncio.run(asyncio.wait_for(scenario(), timeout=180))
