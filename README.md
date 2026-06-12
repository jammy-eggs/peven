# Peven

Peven is Python authoring for structured LLM environments backed by a Julia Petri-net runtime.

If PydanticAI makes it easy to build agents, Peven makes it easy to build the environment around them: places, transitions, joins, guards, retries, and the topology you want to evaluate.

## Why use it

- Author environments in Python, next to the agents and tools you already write.
- Make topology explicit instead of hiding it inside one giant agent loop.
- Run the hard state-machine part on a Julia engine built for Petri nets and concurrent firing.
- Compare workflows: single-shot, judge loops, keyed joins, guarded retries, branch-and-merge topologies.
- Surface intermediate environment state at any point in a run — a sparse terminal reward is not the only signal a long-horizon rollout can yield.
- Represent multi-turn loops directly: retries, judge-revise cycles, and turn-taking are cycles, which DAG-based frameworks cannot express without escape hatches.

## When not to use it

Peven is probably overkill for a single prompt, a linear chain, or an agent loop that is easier to read as ordinary Python. It starts to pay for itself when the environment has real topology: branching, joins, guards, retries, traces, or reproducible state you want to inspect and compare.

## Install

First install the Python package:

```bash
uv add peven
```

or

```bash
pip install peven
```

Peven also needs a Julia runtime. One command provisions it:

```bash
uv run peven setup
```

`setup` installs Julia via [juliaup](https://julialang.org/install/) if it is missing (it asks first; pass `--yes` for CI), then installs `PevenTransport.jl` — which brings `Peven.jl` with it — into a dedicated shared Julia environment. After that, `peven.gateway()` just works.

> PevenTransport.jl is newly registered; if `setup` reports the package was not found, the Julia General registry merge for new packages (a few days) has not completed yet. Try again later.

If you manage Julia yourself (for example through a pixi environment that pins it), skip `setup` and make sure `PevenTransport` is installed in your default Julia environment, or point `peven.gateway(project=...)` at a Julia project that has it.

## Quickstart

```python
import asyncio

import peven
from peven.worker import Worker


@peven.env("single_question")
class SingleQuestion:
    prompt = peven.place()
    report = peven.place(terminal=True)
    solve = peven.transition(inputs=["prompt"], outputs=["report"], executor="answer")


@peven.executor("answer")
async def answer(ctx, store):
    question = ctx.inputs["prompt"][0].payload
    store["asked"] = question
    answer = await askYourModel(question)  # any LLM client you like
    return {
        "report": [
            peven.token(color="report", runKey=ctx.bundle.runKey, payload=answer)
        ]
    }


def buildWorker(workerId, runKeys):
    worker = Worker(workerId, [answer])
    for runKey in runKeys:
        worker.assign(runKey, {})
    return worker


async def main():
    marking = peven.mark(
        *[
            peven.initialMarking(
                runKey=peven.runKey(f"mars#g{i}"),
                tokens=[("prompt", "question", "What planet is known as the red planet?")],
            )
            for i in range(4)
        ]
    )

    async with peven.gateway(buildWorker, workers=2) as gw:
        await gw.load(SingleQuestion)
        async for result in gw.fire(marking, fuse=100):
            print(result.runKey, result.status)
            print(result.finalMarking["report"][0].payload)


asyncio.run(main())
```

What is happening:

- The env class is the topology. It lowers to the Julia engine, which validates it and owns all scheduling.
- The marking is the group: four run keys means four independent rollouts of the same net, interleaved by the engine.
- Executors are async functions called by the engine whenever their transition fires. Each runs inside a worker process that owns its rollout's mutable state (`store`); tokens crossing the boundary carry data and handles, not state.
- `fire` streams one result per rollout as it finishes, so a training loop can act on early rollouts before slow ones complete.

## Results and traces

Every rollout comes back as a typed `RunResult`: `status` (`completed`, `failed`, or `incomplete`), `reason`, `error`, the `finalMarking`, and a `trace` — every firing that happened, with its bundle, attempt count, and output tokens. Failed rollouts are results, not exceptions: a crashed worker or a raising executor fails one rollout while its siblings complete, and the failure arrives in the stream with its reason attached.

The trace is the point. Because the topology is explicit, every intermediate state a rollout passed through is inspectable after the fact — which is exactly the signal sparse terminal rewards throw away.

## Why Julia

The Julia side is not there for novelty. It keeps the engine closer to the real Petri-net model.

Python is a great place to author agents and executors, but it pushes engine code toward shims, wrappers, and dynamic glue. Julia is a better fit for the symbolic runtime: markings, firing rules, joins, guards, retries, and termination stay explicit instead of dissolving into spaghetti soup.

The engine also exploits the formalism directly: transition dependencies are precomputed when the net is constructed, so after each firing only transitions whose input places could have changed are rechecked for enablement.

## Architecture

Peven has three layers:

- `peven` — Python authoring, the worker runtime that executes your callbacks, and the gateway session that drives runs.
- [`PevenTransport.jl`](https://github.com/jammy-eggs/PevenTransport.jl) — the ZMQ gateway between Python and the engine.
- [`Peven.jl`](https://github.com/jammy-eggs/Peven.jl) — the execution engine.

Python authors the net and lowers it to the wire; the gateway routes messages by run key and correlates calls; the engine validates and executes. Rollout state lives in Python worker processes — one owner per run key — and the engine calls back into them whenever a transition fires.

## Release notes

### 0.3.0

- Rebuilt around the PevenTransport wire contract: authoring lowers directly to the engine's net shape, and the old embedded-runtime layers (sinks, guard/join DSL, CLI, PydanticAI integration, MiniGrid example) are gone — v0.2.3 preserves them.
- New runtime: `peven.gateway()` owns the Julia gateway process, `load()` validates the net through the engine, and `fire()` streams one typed `RunResult` per rollout.
- Group rollouts: `peven.mark()` merges per-run markings; run keys partition independent rollouts over one topology, dealt across worker processes that own their rollouts' state.
- Failure semantics built for training: worker crashes and executor exceptions fail single rollouts as results with reasons; fuse exhaustion reports what it starved.
- `python -m peven setup` provisions the Julia side via juliaup and a dedicated shared environment.

### 0.2.3

- Added guard comparisons between field references, such as
  `peven.f.turns < peven.f.max_turns`.
- Removed fossilized version labels from guard and join indexing errors.

### 0.2.2

- Added optional input arcs via `peven.input(..., optional=True)`.
- Updated the MiniGrid DoorKey example so planner advice is an optional token,
  not a sentinel `{"advice": "none"}` token.
- Updated the packaged Julia runtime pins for optional-arc support.
- Added adapter parity coverage for optional inputs, optional-only rejection,
  and optional keyed-join rejection.

### 0.2.1

- Added `peven.place(terminal=True)` for Python-side completion normalization.
- Updated Rich output to hide `no_enabled_transition` for completed terminal-place runs.
- Added the MiniGrid DoorKey example under the `examples` dependency group.
- Added `gymnasium` and `minigrid` to the optional examples dependencies.

## Inspiration

Peven is inspired by a couple different things. For starters the name is taken from Patricia A. McKillip's Riddle-Master trilogy. Peven of Aum is a king, a ghost, and a master riddler who has only ever lost once. In the Riddle-Master trilogy, riddles are made up of three parts: questions, answers, and strictures. My hope for Peven is that it can help you explore evaluations by providing a runtime where you can ask a question, iterate based on the stricture, and, eventually, get to an answer. "Beware the unanswered Riddle."

My second point of inspiration comes from my time working at The LLM Data Company, where I had the chance to learn and experiment to my heart's content. A lot of my work centered around environments and benchmarks. I often wished I had a reusable framework or package to support my work here, something like a pydantic (which I love) but for evaluations.

Most of the architectural decisions I made regarding the engine are because I thought the math was cool. Peven should give you a pretty clear sense of (1) how I think about evaluations and (2) what types of evaluations I'm interested in.
