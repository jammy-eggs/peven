from __future__ import annotations

from dataclasses import dataclass

from peven.key import RunKey


@dataclass(frozen=True, slots=True)
class Token:
    color: str
    runKey: str
    payload: object = None

    def __post_init__(self) -> None:
        if type(self.color) is not str:
            raise TypeError("token color must be a string")
        if not self.color:
            raise ValueError("token color must be non-empty")
        if type(self.runKey) is not str:
            raise TypeError("token runKey must be a string")
        if not self.runKey:
            raise ValueError("token runKey must be non-empty")


@dataclass(frozen=True, slots=True)
class Marking:
    tokensByPlace: dict[str, tuple[Token, ...]]

    def lower(self) -> dict[str, object]:
        return {
            "tokensByPlace": {
                place: [
                    {
                        "color": token.color,
                        "runKey": token.runKey,
                        "payload": token.payload,
                    }
                    for token in tokens
                ]
                for place, tokens in self.tokensByPlace.items()
            }
        }


def token(*, color: str, runKey: str, payload: object = None) -> Token:
    return Token(color=color, runKey=runKey, payload=payload)


def mark(*markings: Marking) -> Marking:
    if not markings:
        raise ValueError("mark requires at least one marking")

    tokensByPlace: dict[str, list[Token]] = {}
    for marking in markings:
        if type(marking) is not Marking:
            raise TypeError("mark arguments must be markings")
        for place, tokens in marking.tokensByPlace.items():
            tokensByPlace.setdefault(place, []).extend(tokens)

    return Marking(
        tokensByPlace={
            place: tuple(placeTokens)
            for place, placeTokens in tokensByPlace.items()
        }
    )


def initialMarking(
    *,
    runKey: RunKey,
    tokens: list[tuple[str, str, object]],
) -> Marking:
    if type(runKey) is not RunKey:
        raise TypeError("marking runKey must be created by peven.runKey()")
    if type(tokens) is not list:
        raise TypeError("marking tokens must be a list")
    if not tokens:
        raise ValueError("marking tokens must be non-empty")

    tokensByPlace: dict[str, list[Token]] = {}
    for row in tokens:
        if type(row) is not tuple:
            raise TypeError("marking token rows must be tuples")
        if len(row) != 3:
            raise ValueError("marking token rows must be (place, color, payload)")

        place, color, payload = row
        if type(place) is not str:
            raise TypeError("marking token place must be a string")
        if not place:
            raise ValueError("marking token place must be non-empty")

        token = Token(color=color, runKey=runKey.value, payload=payload)
        tokensByPlace.setdefault(place, []).append(token)

    return Marking(
        tokensByPlace={
            place: tuple(placeTokens)
            for place, placeTokens in tokensByPlace.items()
        }
    )
