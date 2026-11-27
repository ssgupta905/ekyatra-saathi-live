"""Published rates, and what a journey costs when you add them up.

Money is held in **paise**, as integers, everywhere. A journey costed in floats
drifts by a rupee or two over an itemisation and a family reading the total
finds it does not match the parts, which is exactly the kind of small wrongness
that makes people stop trusting a screen.

Every `Rate` carries where it came from. Nothing in here is a quote, and
`Estimate.low`/`high` exist because a single number implies a precision we do
not have: a sleeper berth on a Tuesday and a Saturday are not the same fare,
and a room near a hospital ranges by a factor of two.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

from saathi.domain.places import PlaceKind

#: Where the shipped table lives. A deployment may point `load_rates` somewhere
#: else; nothing here reaches the network, because a rate that changes under a
#: demo is worse than one that is three months old and says so.
RATES_FILE = Path(__file__).with_name("rates.json")


@dataclass(frozen=True)
class Rate:
    """One published figure, with the publication it came from."""

    #: Paise. Per kilometre, per night, or flat — `unit` says which.
    paise: int
    unit: str
    source: str
    as_of: date
    #: Spread either side, as a fraction. 0.25 means "give or take a quarter".
    spread: float = 0.0

    def over(self, quantity: float) -> tuple[int, int]:
        """Low and high paise for this much of whatever the unit measures."""
        middle = self.paise * quantity
        return (
            max(0, round(middle * (1 - self.spread))),
            max(0, round(middle * (1 + self.spread))),
        )


@dataclass(frozen=True)
class Estimate:
    """A cost we worked out, and everything needed to argue with it."""

    label: str
    low_paise: int
    high_paise: int
    basis: str
    source: str
    as_of: date
    #: True when the family told us this figure themselves. Their number is not
    #: an estimate and must not be rendered as one.
    stated: bool = False
    said: str = ""

    @property
    def is_range(self) -> bool:
        return self.high_paise != self.low_paise

    def rupees(self) -> str:
        low, high = self.low_paise // 100, self.high_paise // 100
        return f"₹{low}" if low == high else f"₹{low}–{high}"

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "low_paise": self.low_paise,
            "high_paise": self.high_paise,
            "rupees": self.rupees(),
            "basis": self.basis,
            "source": self.source,
            "as_of": self.as_of.isoformat(),
            "stated": self.stated,
            "said": self.said,
            "is_estimate": not self.stated,
        }


@dataclass(frozen=True)
class JourneyCost:
    """What a whole trip comes to, itemised.

    Itemised rather than totalled, because "₹2,400" tells a family nothing they
    can act on and "₹1,600 train, two of you, plus one night ₹800" tells them
    which part to push back on — which is the conversation we want.
    """

    items: tuple[Estimate, ...] = ()

    @property
    def low_paise(self) -> int:
        return sum(i.low_paise for i in self.items)

    @property
    def high_paise(self) -> int:
        return sum(i.high_paise for i in self.items)

    @property
    def any_stated(self) -> bool:
        return any(i.stated for i in self.items)

    def rupees(self) -> str:
        low, high = self.low_paise // 100, self.high_paise // 100
        return f"₹{low}" if low == high else f"₹{low}–{high}"

    def to_json(self) -> dict:
        return {
            "items": [i.to_json() for i in self.items],
            "low_paise": self.low_paise,
            "high_paise": self.high_paise,
            "rupees": self.rupees(),
            # One stated figure in the list means the total is not purely ours.
            "has_stated": self.any_stated,
        }


@dataclass(frozen=True)
class RateTable:
    """Every published rate we hold, keyed by what it prices."""

    travel: dict[str, Rate] = field(default_factory=dict)
    stay: dict[str, Rate] = field(default_factory=dict)
    note: str = ""

    # ------------------------------------------------------------------ travel

    def travel_cost(self, mode: str, km: float, people: int = 1) -> Estimate | None:
        """What `people` travelling `km` by `mode` is likely to cost, one way.

        None when we hold no published rate for that mode — the honest answer
        for an app cab, whose price is set by demand at the moment of booking
        and is not published anywhere we can read.
        """
        rate = self.travel.get(mode)
        if rate is None or km <= 0:
            return None
        per_person_low, per_person_high = rate.over(km)
        # A metered vehicle is hired once, not per passenger; a ticket is each.
        heads = 1 if rate.unit.endswith("vehicle") else max(1, people)
        return Estimate(
            label=_TRAVEL_LABEL.get(mode, mode),
            low_paise=per_person_low * heads,
            high_paise=per_person_high * heads,
            basis=(
                f"{round(km)} km"
                + (f" × {heads}" if heads > 1 else "")
                + f" at {rate.paise / 100:.2f}/{rate.unit}"
            ),
            source=rate.source,
            as_of=rate.as_of,
        )

    # ------------------------------------------------------------------- stay

    def stay_cost(self, kind: PlaceKind | str, nights: int = 1) -> Estimate | None:
        """A night in this kind of place, as a band.

        Keyed on the *kind* of place, never on a named business. We hold no
        access to any hotel's prices and will not put a figure beside one.
        """
        key = kind.value if isinstance(kind, PlaceKind) else str(kind)
        rate = self.stay.get(key)
        if rate is None or nights <= 0:
            return None
        low, high = rate.over(nights)
        return Estimate(
            label=_STAY_LABEL.get(key, key.replace("_", " ")),
            low_paise=low,
            high_paise=high,
            basis=f"{nights} night{'s' if nights > 1 else ''}, typical for this kind of place",
            source=rate.source,
            as_of=rate.as_of,
        )


#: How each mode reads to a family. Kept beside the rates so the API, the
#: Console and the app cannot describe the same figure three different ways.
_TRAVEL_LABEL: dict[str, str] = {
    "rail_local": "Local train",
    "rail_sleeper": "Train, sleeper",
    "rail_3ac": "Train, 3AC",
    "bus_state": "State bus",
    "bus_deluxe": "Deluxe bus",
    "auto": "Auto",
    "taxi": "Taxi",
}

_STAY_LABEL: dict[str, str] = {
    "dharamshala": "Dharamshala bed",
    "guest_house": "Guest house room",
    "hotel": "Budget hotel room",
}


@lru_cache(maxsize=4)
def load_rates(path: Path | None = None) -> RateTable:
    """Read the shipped table. Cached: it is a file, and it does not change."""
    raw = json.loads((path or RATES_FILE).read_text(encoding="utf-8"))

    def rates_of(section: str) -> dict[str, Rate]:
        return {
            key: Rate(
                paise=int(row["paise"]),
                unit=str(row["unit"]),
                source=str(row["source"]),
                as_of=date.fromisoformat(str(row["as_of"])),
                spread=float(row.get("spread", 0.0)),
            )
            for key, row in raw.get(section, {}).items()
        }

    return RateTable(
        travel=rates_of("travel"),
        stay=rates_of("stay"),
        note=str(raw.get("note", "")),
    )
