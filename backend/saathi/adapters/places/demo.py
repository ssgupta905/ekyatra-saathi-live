"""Invented shops, so the screen can be shown without a key.

Every place says `source="demo"` and the screen says so. Refused in production
(config). The names, phones and hours are made up and must never be read as real.
"""

from __future__ import annotations

from datetime import time

from ...domain.places import Period, Place, PlaceKind

_ALL_WEEK = tuple(Period(open_day=d, open_at=time(9), close_day=d, close_at=time(21)) for d in range(7))
_ROUND_THE_CLOCK = (Period(open_day=0, open_at=time(0)),)

#: (kind, name, dlat, dlng, hours)
_SHOPS = [
    (PlaceKind.JAN_AUSHADHI, "Demo Jan Aushadhi Kendra", 0.004, 0.003, _ALL_WEEK[:6]),
    (PlaceKind.PHARMACY, "Demo 24-hour Medical", -0.003, 0.002, _ROUND_THE_CLOCK),
    (PlaceKind.PHARMACY, "Demo Day Pharmacy", 0.006, -0.004, _ALL_WEEK),
    (PlaceKind.LAB, "Demo Diagnostics", 0.002, 0.007, _ALL_WEEK),
    (PlaceKind.EQUIPMENT, "Demo Surgical & Mobility", -0.005, -0.006, _ALL_WEEK),
    (PlaceKind.CLINIC, "Demo Care Clinic", 0.001, -0.002, _ALL_WEEK),
    (PlaceKind.PHYSIO, "Demo Physio Centre", -0.004, 0.005, _ALL_WEEK),
]


class DemoPlaces:
    name = "demo"

    async def nearby(
        self, kind: PlaceKind, latitude: float, longitude: float, *, radius_m: int = 3000, language: str = "en"
    ) -> list[Place]:
        return [
            Place(
                id=f"demo-{i}",
                name=name,
                kind=kind,
                address="Demo address — not a real place",
                latitude=latitude + dlat,
                longitude=longitude + dlng,
                phone="+91 00000 00000",
                periods=hours,
                source="demo",
            )
            for i, (k, name, dlat, dlng, hours) in enumerate(_SHOPS)
            if k is kind
        ]

    async def close(self) -> None:
        pass
