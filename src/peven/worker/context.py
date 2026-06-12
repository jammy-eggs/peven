"""Execution context shapes mirroring Peven.jl.

Instances are built by the IPC decoder, which owns wire validation.
"""

from __future__ import annotations

from dataclasses import dataclass

from peven.marking import Token


@dataclass(frozen=True, slots=True)
class Bundle:
    transitionId: str
    runKey: str
    selectedKey: object


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    bundle: Bundle
    firingId: int
    attempt: int
    inputs: dict[str, tuple[Token, ...]]


@dataclass(frozen=True, slots=True)
class TransitionResult:
    bundle: Bundle
    firingId: int
    status: str
    outputs: tuple[Token, ...]
    error: str | None
    attempts: int


@dataclass(frozen=True, slots=True)
class RunResult:
    runKey: str
    status: str
    error: str | None
    reason: str | None
    trace: tuple[TransitionResult, ...]
    finalMarking: dict[str, tuple[Token, ...]]
