"""Worker side of the PevenTransport IPC contract.

PevenTransport.jl src/ipc.jl is the wire authority. Builders mirror it
field for field, including error text.
"""

from __future__ import annotations

import msgpack

from peven.marking import Token
from peven.worker.context import Bundle, ExecutionContext, RunResult, TransitionResult


maxPayloadBytes = 8 * 1024 * 1024
protocolVersion = 1


class IpcError(Exception):
    pass


def encode(message: dict) -> bytes:
    payload = msgpack.packb(message)
    if len(payload) > maxPayloadBytes:
        raise IpcError(f"IPC payload exceeds {maxPayloadBytes} bytes")
    return payload


def decode(payload: bytes) -> object:
    if len(payload) > maxPayloadBytes:
        raise IpcError(f"IPC payload exceeds {maxPayloadBytes} bytes")
    return msgpack.unpackb(payload)


def workerHello(workerId: str) -> dict:
    requireNonEmptyString(workerId, "workerId")
    return {"kind": "workerHello", "workerId": workerId, "protocol": protocolVersion}


def workerGoodbye(workerId: str) -> dict:
    requireNonEmptyString(workerId, "workerId")
    return {"kind": "workerGoodbye", "workerId": workerId}


def assign(runKey: str, workerId: str) -> dict:
    requireNonEmptyString(runKey, "runKey")
    requireNonEmptyString(workerId, "workerId")
    return {"kind": "assign", "runKey": runKey, "workerId": workerId}


def release(runKey: str) -> dict:
    requireNonEmptyString(runKey, "runKey")
    return {"kind": "release", "runKey": runKey}


def executorResult(callId: int, outputs: dict) -> dict:
    requireCallId(callId)
    if type(outputs) is not dict:
        raise IpcError("outputs must be a map")
    return {"kind": "executorResult", "callId": callId, "outputs": outputs}


def executorError(callId: int, error: str) -> dict:
    requireCallId(callId)
    requireNonEmptyString(error, "error")
    return {"kind": "executorError", "callId": callId, "error": error}


def decodeExecutorCall(message: object) -> tuple[int, str, ExecutionContext]:
    map = requireKind(message, "executorCall")
    callId = requireCallId(map.get("callId"))
    executorName = requireNonEmptyField(map, "executorName")
    return callId, executorName, decodeContext(requireMapField(map, "ctx"))


def decodeWorkerReady(message: object) -> str:
    map = requireKind(message, "workerReady")
    return requireNonEmptyField(map, "workerId")


def decodeWorkerGone(message: object) -> str:
    map = requireKind(message, "workerGone")
    return requireNonEmptyField(map, "workerId")


def decodeAssigned(message: object) -> tuple[str, str]:
    map = requireKind(message, "assigned")
    runKey = requireNonEmptyField(map, "runKey")
    workerId = requireNonEmptyField(map, "workerId")
    return runKey, workerId


def decodeReleased(message: object) -> str:
    map = requireKind(message, "released")
    return requireNonEmptyField(map, "runKey")


def decodeGatewayError(message: object) -> str:
    map = requireKind(message, "gatewayError")
    return requireNonEmptyField(map, "error")


def loadNet(net: dict) -> dict:
    return {"kind": "loadNet", "net": requireMap(net, "net")}


def fire(
    fireId: str,
    net: str,
    marking: dict,
    fuse: int | None = None,
    maxConcurrency: int | None = None,
) -> dict:
    requireNonEmptyString(fireId, "fireId")
    requireNonEmptyString(net, "net")
    message = {
        "kind": "fire",
        "fireId": fireId,
        "net": net,
        "marking": requireMap(marking, "marking"),
    }
    if fuse is not None:
        message["fuse"] = fuse
    if maxConcurrency is not None:
        message["maxConcurrency"] = maxConcurrency
    return message


def decodeNetLoaded(message: object) -> str:
    map = requireKind(message, "netLoaded")
    return requireNonEmptyField(map, "name")


def decodeRunFinished(message: object) -> tuple[str, RunResult]:
    map = requireKind(message, "runFinished")
    fireId = requireNonEmptyField(map, "fireId")
    return fireId, decodeRunResult(requireMapField(map, "result"))


def decodeFireFinished(message: object) -> tuple[str, str | None]:
    map = requireKind(message, "fireFinished")
    fireId = requireNonEmptyField(map, "fireId")
    if map.get("error") is None:
        return fireId, None
    return fireId, requireNonEmptyField(map, "error")


def decodeRunResult(result: dict) -> RunResult:
    return RunResult(
        runKey=requireNonEmptyField(result, "runKey"),
        status=requireNonEmptyField(result, "status"),
        error=result.get("error"),
        reason=result.get("reason"),
        trace=tuple(
            decodeTransitionResult(entry)
            for entry in requireListField(result, "trace")
        ),
        finalMarking=decodeTokenBuckets(
            requireMapField(requireMapField(result, "finalMarking"), "tokensByPlace")
        ),
    )


def decodeTransitionResult(value: object) -> TransitionResult:
    entry = requireMap(value, "trace entry")
    return TransitionResult(
        bundle=decodeBundle(requireMapField(entry, "bundle")),
        firingId=requireInt(entry, "firingId"),
        status=requireNonEmptyField(entry, "status"),
        outputs=tuple(
            decodeToken(token) for token in requireListField(entry, "outputs")
        ),
        error=entry.get("error"),
        attempts=requireInt(entry, "attempts"),
    )


def decodeContext(ctx: dict) -> ExecutionContext:
    return ExecutionContext(
        bundle=decodeBundle(requireMapField(ctx, "bundle")),
        firingId=requireInt(ctx, "firingId"),
        attempt=requireInt(ctx, "attempt"),
        inputs=decodeTokenBuckets(requireMapField(ctx, "inputs")),
    )


def decodeBundle(bundle: dict) -> Bundle:
    return Bundle(
        transitionId=requireString(bundle, "transitionId"),
        runKey=requireString(bundle, "runKey"),
        selectedKey=bundle.get("selectedKey"),
    )


def decodeTokenBuckets(buckets: dict) -> dict[str, tuple[Token, ...]]:
    decoded: dict[str, tuple[Token, ...]] = {}
    for placeId, bucket in buckets.items():
        if type(placeId) is not str:
            raise IpcError("place ids must be strings")
        if type(bucket) is not list:
            raise IpcError("token buckets must be lists")
        decoded[placeId] = tuple(decodeToken(token) for token in bucket)
    return decoded


def tokenMessage(token: Token) -> dict:
    return {
        "color": token.color,
        "runKey": token.runKey,
        "payload": token.payload,
    }


def decodeToken(value: object) -> Token:
    token = requireMap(value, "token")
    return Token(
        color=requireNonEmptyField(token, "color"),
        runKey=requireNonEmptyField(token, "runKey"),
        payload=token.get("payload"),
    )


def requireKind(message: object, expected: str) -> dict:
    map = requireMap(message, "message")
    kind = requireString(map, "kind")
    if kind != expected:
        raise IpcError(f"expected kind {expected!r}")
    return map


def requireMapField(message: dict, key: str) -> dict:
    if key not in message:
        raise IpcError(f"missing required field {key!r}")
    return requireMap(message[key], key)


def requireMap(value: object, context: str) -> dict:
    if type(value) is not dict:
        raise IpcError(f"{context} must be a map")
    return value


def requireString(message: dict, key: str) -> str:
    if key not in message:
        raise IpcError(f"missing required field {key!r}")
    value = message[key]
    if type(value) is not str:
        raise IpcError(f"{key} must be a string")
    return value


def requireNonEmptyField(message: dict, key: str) -> str:
    value = requireString(message, key)
    if not value:
        raise IpcError(f"{key} must be non-empty")
    return value


def requireListField(message: dict, key: str) -> list:
    if key not in message:
        raise IpcError(f"missing required field {key!r}")
    value = message[key]
    if type(value) is not list:
        raise IpcError(f"{key} must be a list")
    return value


def requireInt(message: dict, key: str) -> int:
    if key not in message:
        raise IpcError(f"missing required field {key!r}")
    value = message[key]
    if type(value) is not int:
        raise IpcError(f"{key} must be an integer")
    return value


def requireCallId(value: object) -> int:
    if type(value) is not int:
        raise IpcError("callId must be an integer")
    if value <= 0:
        raise IpcError("callId must be positive")
    return value


def requireNonEmptyString(value: object, key: str) -> str:
    if type(value) is not str:
        raise IpcError(f"{key} must be a string")
    if not value:
        raise IpcError(f"{key} must be non-empty")
    return value
