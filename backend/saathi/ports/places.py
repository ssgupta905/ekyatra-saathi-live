"""Finding somewhere nearby: a shop, a lab, a clinic.

A place finder says what is around a point. It never says what is in stock, who
a family should see, or which place is best for them;
`orchestrator/nearby_needs.py` orders what it finds, with the reasons shown.
"""

from __future__ import annotations

from typing import Protocol

from ..domain.places import Place, PlaceKind


class PlacesUnavailable(RuntimeError):
    """The service could not be reached or refused. The screen says so and offers Maps."""


class PlaceFinder(Protocol):
    name: str

    async def nearby(
        self, kind: PlaceKind, latitude: float, longitude: float, *, radius_m: int = 3000, language: str = "en"
    ) -> list[Place]: ...

    async def close(self) -> None: ...
