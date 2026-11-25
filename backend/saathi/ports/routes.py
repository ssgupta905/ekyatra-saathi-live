"""Where the buses and trains actually go.

A route service answers one question: from here to there, by this kind of
vehicle, what are the ways, step by step. It never decides which one a family
should take; `orchestrator/trip_options.py` does that, with the family's
money in view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..domain.itinerary import RouteOption


class RoutesUnavailable(RuntimeError):
    """The service could not be reached or refused. The screen says so and offers Maps."""


@dataclass(frozen=True)
class Place:
    #: A name a person would say, or "lat,lng".
    text: str


class RoutePlanner(Protocol):
    name: str

    async def options(
        self,
        origin: Place,
        destination: Place,
        *,
        mode: str,
        arrive_by: datetime | None = None,
        depart_at: datetime | None = None,
    ) -> list[RouteOption]:
        """`mode` is "transit" or "driving". Empty when there is no way."""
        ...

    async def close(self) -> None: ...
