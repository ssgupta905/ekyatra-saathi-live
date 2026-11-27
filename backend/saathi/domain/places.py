"""Somewhere a family could go for something the journey needs, near where they will be.

These are *suggestions from a map service*, not partners: Saathi has not asked
the shop whether it has the medicine, and says so. Nothing here ranks doctors,
takes a rating into account, or says who to see — a doctor's chamber appears
only when the hospital's team has put it in the directory.

Only the place's own id is meant to be kept; its hours and phone are read when
needed, which is also what the map service's terms ask.
"""

from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import Field

from .models import Base

IST = ZoneInfo("Asia/Kolkata")


class PlaceKind(StrEnum):
    PHARMACY = "pharmacy"
    #: Government generic-medicine stores; cheaper, so offered first when money is tight.
    JAN_AUSHADHI = "jan_aushadhi"
    LAB = "lab"
    EQUIPMENT = "equipment"
    CLINIC = "clinic"
    PHYSIO = "physio"
    #: Somewhere to sleep. A family travelling two days each way needs this as
    #: concretely as they need a pharmacy, and nothing in here answered it.
    #:
    #: Three kinds and not one, for the same reason Jan Aushadhi is its own
    #: kind rather than a pharmacy: a dharamshala is free or nearly so and is
    #: the right first answer for a family counting bus fares, and burying it
    #: among hotels would hide the only one many of them can use. Cancer
    #: centres in India are ringed by them precisely because of who travels.
    DHARAMSHALA = "dharamshala"
    GUEST_HOUSE = "guest_house"
    HOTEL = "hotel"


#: What a journey need asks for, in the order a family would want them.
KINDS_FOR_NEED: dict[str, tuple[PlaceKind, ...]] = {
    "medicine": (PlaceKind.JAN_AUSHADHI, PlaceKind.PHARMACY),
    "tests": (PlaceKind.LAB,),
    "equipment": (PlaceKind.EQUIPMENT,),
    "clinic": (PlaceKind.CLINIC, PlaceKind.PHYSIO),
    #: Cheapest first, deliberately — the same order `medicine` uses.
    "stay": (PlaceKind.DHARAMSHALA, PlaceKind.GUEST_HOUSE, PlaceKind.HOTEL),
}


class Period(Base):
    """Open from (day, hh:mm) to (day, hh:mm). Day 0 is Sunday, as the map service has it."""

    open_day: int = Field(ge=0, le=6)
    open_at: time
    close_day: int | None = Field(default=None, ge=0, le=6)
    close_at: time | None = None


class Place(Base):
    id: str
    name: str
    kind: PlaceKind
    address: str = ""
    latitude: float
    longitude: float
    phone: str | None = None
    #: The map service's own "open right now" — only true of now.
    open_now: bool | None = None
    periods: tuple[Period, ...] = ()
    #: A link a phone opens in its map app.
    maps_uri: str | None = None
    #: Where the entry came from, so a demo is never mistaken for the real thing.
    source: str = "google"

    @property
    def is_24h(self) -> bool:
        return any(p.close_at is None for p in self.periods)

    def open_at(self, when: datetime) -> bool | None:
        """Whether it is open at `when` (IST). None when hours are not known."""
        if self.is_24h:
            return True
        if not self.periods:
            return None
        local = when.astimezone(IST)
        day = (local.weekday() + 1) % 7  # Monday=0 in Python; Sunday=0 for the map service
        now = local.time()
        for p in self.periods:
            if p.close_at is None:
                return True
            if p.open_day == day and p.close_day in (None, day) and p.open_at <= now < p.close_at:
                return True
            # Open past midnight: opened yesterday, closes today.
            if p.open_day == (day - 1) % 7 and p.close_day == day and now < p.close_at:
                return True
        return False


class Ranked(Base):
    place: Place
    #: Straight-line metres from where the family will be. A rough guide, said so.
    metres: int
    #: Open at the time they need it. None when hours are not known.
    open_then: bool | None = None
    #: Why it is where it is in the list, as codes the screen puts in the family's language.
    reasons: tuple[str, ...] = ()


__all__ = ["IST", "KINDS_FOR_NEED", "Period", "Place", "PlaceKind", "Ranked"]
