from __future__ import annotations

import asyncio
import multiprocessing
import os
import shutil
from contextlib import aclosing
from pathlib import Path

import pytest

import peven
from peven.gateway import gateway
from peven.worker import Worker, ipc


julia = shutil.which("julia")
transportProject = Path.home() / "peventransport"

pytestmark = pytest.mark.skipif(
    julia is None or not transportProject.exists(),
    reason="julia and ~/peventransport required",
)


@peven.executor("emit")
async def emit(ctx, store):
    token = ctx.inputs["start"][0]
    if token.payload == "die":
        os._exit(1)
    if token.payload == "boom":
        raise RuntimeError("bad judge")
    return {
        "done": [
            peven.token(color="answer", runKey=ctx.bundle.runKey, payload=token.payload)
        ]
    }


@peven.env("tiny")
class Tiny:
    start = peven.place()
    done = peven.place(terminal=True)
    finish = peven.transition(inputs=["start"], outputs=["done"], executor="emit")


@peven.env("orphaned")
class Orphaned:
    start = peven.place()
    stray = peven.place()
    done = peven.place(terminal=True)
    finish = peven.transition(inputs=["start"], outputs=["done"], executor="emit")


def buildWorker(workerId: str, runKeys: list[str]) -> Worker:
    worker = Worker(workerId, [emit])
    for runKey in runKeys:
        worker.assign(runKey, {})
    return worker


def test_001() -> None:
    """The session owns the Julia gateway process from enter to exit.

    Julia leads its own process group (the orphan guard: teardown kills the
    group, so nothing julia spawned can outlive the session holding a port),
    and exit is unconditional.
    """

    async def scenario():
        async with gateway(buildWorker, project=transportProject) as gw:
            process = gw.process
            assert process.poll() is None
            assert os.getpgid(process.pid) == process.pid
        assert process.poll() is not None

    asyncio.run(asyncio.wait_for(scenario(), timeout=60))


def test_002() -> None:
    """Gateway construction validates its knobs before any side effects."""
    with pytest.raises(TypeError, match="buildWorker must be callable"):
        gateway("nope")
    with pytest.raises(TypeError, match="workers must be an int"):
        gateway(buildWorker, workers=True)
    with pytest.raises(ValueError, match="workers must be greater than 0"):
        gateway(buildWorker, workers=0)


def test_003() -> None:
    """load lowers the env, the engine validates it, and the ack names it.

    First proof that the spawned Julia actually serves: the netLoaded reply
    only arrives once PevenTransport is up and the net passed engine
    validation.
    """

    async def scenario():
        async with gateway(buildWorker, project=transportProject) as gw:
            await gw.load(Tiny)
            assert gw.netName == "tiny"

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_004() -> None:
    """Engine-rejected nets surface as IpcError carrying the gateway reason."""

    async def scenario():
        async with gateway(buildWorker, project=transportProject) as gw:
            with pytest.raises(ipc.IpcError, match='invalid net "orphaned"'):
                await gw.load(Orphaned)

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_005() -> None:
    """fire streams one typed RunResult per run key in the group marking.

    Two run keys dealt across two workers, both rollouts completed, and
    each final marking carries the payload its own executor emitted.
    """

    async def scenario():
        async with gateway(buildWorker, workers=2, project=transportProject) as gw:
            await gw.load(Tiny)
            marking = peven.mark(
                peven.initialMarking(
                    runKey=peven.runKey("task-g#g0"), tokens=[("start", "q", "a")]
                ),
                peven.initialMarking(
                    runKey=peven.runKey("task-g#g1"), tokens=[("start", "q", "b")]
                ),
            )

            results = {
                result.runKey: result async for result in gw.fire(marking, fuse=50)
            }

        assert set(results) == {"task-g#g0", "task-g#g1"}
        for runKey, payload in [("task-g#g0", "a"), ("task-g#g1", "b")]:
            result = results[runKey]
            assert result.status == "completed"
            assert result.finalMarking["done"][0].payload == payload

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_006() -> None:
    """fire without a loaded net fails before any processes start."""

    async def scenario():
        async with gateway(buildWorker, project=transportProject) as gw:
            marking = peven.initialMarking(
                runKey=peven.runKey(), tokens=[("start", "q", None)]
            )
            with pytest.raises(ValueError, match="no net loaded"):
                async for _ in gw.fire(marking):
                    pass

    asyncio.run(asyncio.wait_for(scenario(), timeout=60))


def groupMarking(payloads: dict[str, object]):
    return peven.mark(
        *[
            peven.initialMarking(
                runKey=peven.runKey(runKey), tokens=[("start", "q", payload)]
            )
            for runKey, payload in payloads.items()
        ]
    )


def test_007() -> None:
    """A worker process dying mid-call fails its rollout, not the group.

    The liveness contract end to end: the executor kills its own process
    before replying, the gateway detects the disconnect and fails the
    pending call, the engine misfires, and the rollout comes back as a
    failed RunResult — while the sibling rollout in the other worker's
    hand completes untouched. No hang, no exception, a result.
    """

    async def scenario():
        async with gateway(buildWorker, workers=2, project=transportProject) as gw:
            await gw.load(Tiny)
            marking = groupMarking({"task-f#g0": "die", "task-f#g1": "ok"})

            results = {
                result.runKey: result async for result in gw.fire(marking, fuse=50)
            }

        dead = results["task-f#g0"]
        assert dead.status == "failed"
        assert dead.reason == "executorFailed"
        assert "disconnected" in dead.error
        assert results["task-f#g1"].status == "completed"

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_008() -> None:
    """An executor exception fails its rollout; the worker keeps serving.

    Both rollouts share one worker's hand, so this also proves the worker
    survives an executor raise under real load: the failed rollout carries
    the Python exception repr across the wire, the sibling completes.
    """

    async def scenario():
        async with gateway(buildWorker, workers=1, project=transportProject) as gw:
            await gw.load(Tiny)
            marking = groupMarking({"task-f#g0": "boom", "task-f#g1": "ok"})

            results = {
                result.runKey: result async for result in gw.fire(marking, fuse=50)
            }

        failed = results["task-f#g0"]
        assert failed.status == "failed"
        assert failed.reason == "executorFailed"
        assert "RuntimeError('bad judge')" in failed.error
        assert results["task-f#g1"].status == "completed"

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_009() -> None:
    """An exhausted fuse stops launching but still reports every rollout.

    fuse=1 across a G=2 group: one rollout gets the only launch and
    completes, the starved one comes back incomplete with the fuse named
    as the reason. Which rollout wins is the engine's choice.
    """

    async def scenario():
        async with gateway(buildWorker, workers=1, project=transportProject) as gw:
            await gw.load(Tiny)
            marking = groupMarking({"task-f#g0": "ok", "task-f#g1": "ok"})

            results = [result async for result in gw.fire(marking, fuse=1)]

        assert sorted(result.status for result in results) == [
            "completed",
            "incomplete",
        ]
        starved = next(r for r in results if r.status == "incomplete")
        assert starved.reason == "fuseExhausted"

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_010() -> None:
    """Closing an abandoned result stream stops the fire's workers.

    A trainer that breaks out early (resampling a degenerate group) must
    not leak worker processes; closing the iterator runs fire's cleanup.
    """

    async def scenario():
        async with gateway(buildWorker, workers=2, project=transportProject) as gw:
            await gw.load(Tiny)
            marking = groupMarking({"task-f#g0": "ok", "task-f#g1": "ok"})

            async with aclosing(gw.fire(marking, fuse=50)) as stream:
                async for _ in stream:
                    break

            assert multiprocessing.active_children() == []

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))


def test_011(tmp_path) -> None:
    """A gateway that dies at boot raises an actionable error, not a hang.

    Pointing julia at an empty project makes `using PevenTransport` fail —
    the same failure a first-time user sees before running peven setup.
    """

    async def scenario():
        async with gateway(buildWorker, project=tmp_path) as gw:
            with pytest.raises(RuntimeError, match="run: peven setup"):
                await gw.load(Tiny)

    asyncio.run(asyncio.wait_for(scenario(), timeout=120))
