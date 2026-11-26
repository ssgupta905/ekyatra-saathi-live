"""Where a family boards, and gets off, a long-distance train.

No open service carries reserved intercity trains: IRCTC publishes no public
API, and Google's route data stops at city transit. So Saathi does not claim
to know train numbers, times or fares. It does know something that saves a
family a wrong turn in IRCTC's search box: which station is theirs and which
terminal is nearest the hospital, with the codes IRCTC asks for.

A district or hospital missing here gets no rail guidance rather than a
guess. Add it when it is known.
"""

from __future__ import annotations

from dataclasses import dataclass

IRCTC_SEARCH = "https://www.irctc.co.in/nget/train-search"
LIVE_STATUS = "https://enquiry.indianrail.gov.in/mntes/"


@dataclass(frozen=True)
class Station:
    name: str
    code: str
    #: What a map service resolves to this station, for the last leg.
    place: str


#: The main station for a home district, keyed by the district in lower case.
HOME_STATIONS: dict[str, Station] = {
    "darbhanga": Station("Darbhanga Jn", "DBG", "Darbhanga Junction railway station"),
    "gaya": Station("Gaya Jn", "GAYA", "Gaya Junction railway station"),
    "patna": Station("Patna Jn", "PNBE", "Patna Junction railway station"),
    "samastipur": Station("Samastipur Jn", "SPJ", "Samastipur Junction railway station"),
    "muzaffarpur": Station("Muzaffarpur Jn", "MFP", "Muzaffarpur Junction railway station"),
    "varanasi": Station("Varanasi Jn", "BSB", "Varanasi Junction railway station"),
    "begusarai": Station("Begusarai", "BGS", "Begusarai railway station"),
    "bhagalpur": Station("Bhagalpur Jn", "BGP", "Bhagalpur Junction railway station"),
}

_CSMT = Station("Mumbai CSMT", "CSMT", "Chhatrapati Shivaji Maharaj Terminus, Mumbai")
_DADAR = Station("Dadar", "DR", "Dadar railway station, Mumbai")
_LTT = Station("Lokmanya Tilak Terminus", "LTT", "Lokmanya Tilak Terminus, Mumbai")

#: The terminals nearest each hospital, the closest first.
ARRIVAL_STATIONS: dict[str, tuple[Station, ...]] = {
    "TMH-MUM": (_CSMT, _DADAR, _LTT),
    "HBCH-MZP": (HOME_STATIONS["muzaffarpur"],),
}


@dataclass(frozen=True)
class RailHint:
    origin: Station
    arrival: tuple[Station, ...]

    @property
    def nearest(self) -> Station:
        return self.arrival[0]


def home_station(district: str) -> Station | None:
    return HOME_STATIONS.get((district or "").strip().lower())


def arrival_stations(hospital_id: str) -> tuple[Station, ...]:
    return ARRIVAL_STATIONS.get(hospital_id, ())


def rail_hint(district: str, hospital_id: str) -> RailHint | None:
    """Both ends of the train journey, or None when either is not known."""
    origin = home_station(district)
    arrival = arrival_stations(hospital_id)
    if origin is None or not arrival:
        return None
    # A hospital in the family's own station town needs no train.
    if arrival[0].code == origin.code:
        return None
    return RailHint(origin=origin, arrival=arrival)
