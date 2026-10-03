"""Where places are and how long it takes to get between them — fetched, not assumed.

`Patient.home_distance_km` is one number, and one number cannot answer the
question the option table asks. Shambhu is ~1,700 km from Mumbai; Anita is ~50 km
from her hub. Both are distances, but one means a day and a half on a train and
the other means a bus after breakfast, and that difference decides whether "go
home and come back" is a kindness or a cruelty.

So this tool returns a `Journey` with a **fetched duration**, and that duration is
what `itinerary.gap_days_for` reads instead of a kilometre threshold.

Nothing here knows where Gaya is. Coordinates come from a geocoder, distances and
durations from a routing service, and both are cached with the URL that produced
them and the time they were fetched (`cache.py`). If neither the service nor the
cache can answer, the tool returns None, the step's prerequisite has no window,
and the decision is UNCERTAIN. That is the correct failure: "we don't know yet"
costs a family nothing, and a distance we made up can cost them a journey.

One honesty note on mode. A routing service answers for roads. Most of these
families travel by train, and this tool does not pretend to know train timings —
it reports what it fetched and labels it `road`. When a transport endpoint is
configured (`SAATHI_TRANSPORT_URL`) that answers for rail instead, and the label
changes with it. No fare is reported at all unless a service provides one; the
cost figures in this project come from the cited study in `synthetic/generate.py`,
not from a per-kilometre rate somebody invented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from ..domain.enums import SourceSystem
from .base import PROVIDER_LIVE, ToolResult, ToolUnavailable
from .cache import ReferenceCache

logger = logging.getLogger(__name__)

#: Public endpoints that need no key. Both are rate-limited and are meant for
#: filling the cache (`make fetch-reference`), not for per-request traffic.
DEFAULT_GEOCODER = "https://nominatim.openstreetmap.org"
DEFAULT_ROUTER = "https://router.project-osrm.org"

#: Nominatim's usage policy requires an identifying User-Agent.
USER_AGENT = "ekyatra-saathi/0.1 (hackathon prototype; contact: project maintainer)"


@dataclass(frozen=True)
class Place:
    name: str
    lat: float
    lon: float
    display_name: str


@dataclass(frozen=True)
class Journey:
    """One leg, home to a centre, as some service actually reported it."""

    origin: str
    destination: str
    distance_km: float
    hours: float
    #: What the duration describes: "road" from a routing service, "rail" from a
    #: transport service. Never a guess at a different mode.
    mode: str
    provider: str
    fetched_at: str

    @property
    def round_trip_hours(self) -> float:
        return self.hours * 2

    def to_json(self) -> dict:
        return {
            "origin": self.origin,
            "destination": self.destination,
            "distance_km": round(self.distance_km, 1),
            "hours": round(self.hours, 1),
            "round_trip_hours": round(self.round_trip_hours, 1),
            "mode": self.mode,
            "provider": self.provider,
            "fetched_at": self.fetched_at,
        }


class GeoTool:
    """Geocoding and routing, cached, with the provenance kept."""

    name = "geo.journey"

    def __init__(
        self,
        cache: ReferenceCache,
        *,
        geocoder_url: str = DEFAULT_GEOCODER,
        router_url: str = DEFAULT_ROUTER,
        allow_network: bool = False,
        timeout: float = 8.0,
    ) -> None:
        self._cache = cache
        self._geocoder = geocoder_url.rstrip("/")
        self._router = router_url.rstrip("/")
        #: Off during a live run by default. Serving a demo means dozens of
        #: lookups a second, and a public geocoder is not for that — the cache
        #: is filled deliberately by `make fetch-reference` and read from here.
        self._allow_network = allow_network
        self._timeout = timeout

    # ---------------- geocoding ----------------

    def geocode(self, place: str, *, country: str = "India") -> Place | None:
        """Coordinates for a named place. Cache first, then the geocoder."""
        key = f"geocode:{place}|{country}"
        cached = self._cache.get(key)
        if cached is not None:
            v = cached.value
            return Place(place, v["lat"], v["lon"], v["display_name"])

        if not self._allow_network:
            return None

        url = f"{self._geocoder}/search"
        params = {"q": f"{place}, {country}", "format": "json", "limit": 1}
        try:
            response = httpx.get(
                url, params=params, timeout=self._timeout, headers={"User-Agent": USER_AGENT}
            )
            response.raise_for_status()
            hits = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolUnavailable(f"geocoder: {exc}") from exc
        if not hits:
            return None

        hit = hits[0]
        value = {
            "lat": float(hit["lat"]),
            "lon": float(hit["lon"]),
            "display_name": hit.get("display_name", place),
        }
        self._cache.put(
            key,
            value,
            provider="nominatim",
            source_url=str(response.url),
            raw_body=response.text,
        )
        return Place(place, value["lat"], value["lon"], value["display_name"])

    # ---------------- routing ----------------

    def journey(self, origin: str, destination: str) -> ToolResult[Journey] | None:
        """Travel from `origin` to `destination`, one way.

        Returns None when neither the cache nor a configured service can
        answer. The planner reads that as unknown, not as zero.
        """
        if origin == destination:
            journey = Journey(origin, destination, 0.0, 0.0, "none", "same-place", "")
            return self._result(journey)

        key = f"route:{origin}->{destination}"
        cached = self._cache.get(key)
        if cached is None:
            # A road route is near enough symmetric that fetching both
            # directions is a waste of somebody else's rate limit. The reverse
            # leg is the same evidence, and keeps its original provenance.
            cached = self._cache.get(f"route:{destination}->{origin}")
        if cached is not None:
            v = cached.value
            return self._result(
                Journey(
                    origin=origin,
                    destination=destination,
                    distance_km=v["distance_km"],
                    hours=v["hours"],
                    mode=v["mode"],
                    provider=cached.provider,
                    fetched_at=cached.fetched_at.isoformat(),
                )
            )

        if not self._allow_network:
            return None

        a, b = self.geocode(origin), self.geocode(destination)
        if a is None or b is None:
            return None

        url = f"{self._router}/route/v1/driving/{a.lon},{a.lat};{b.lon},{b.lat}"
        try:
            response = httpx.get(
                url, params={"overview": "false"}, timeout=self._timeout
            )
            response.raise_for_status()
            payload = response.json()
            route = payload["routes"][0]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ToolUnavailable(f"router: {exc}") from exc

        value = {
            "distance_km": route["distance"] / 1000.0,
            "hours": route["duration"] / 3600.0,
            "mode": "road",
        }
        fact = self._cache.put(
            key,
            value,
            provider="osrm",
            source_url=str(response.url),
            raw_body=response.text,
        )
        return self._result(
            Journey(
                origin=origin,
                destination=destination,
                distance_km=value["distance_km"],
                hours=value["hours"],
                mode="road",
                provider=fact.provider,
                fetched_at=fact.fetched_at.isoformat(),
            )
        )

    # ---------------- plumbing ----------------

    def _result(self, journey: Journey) -> ToolResult[Journey]:
        return ToolResult(
            value=journey,
            tool=self.name,
            source=SourceSystem.DERIVED,
            source_record_id=f"journey:{journey.origin}->{journey.destination}",
            claim=(
                f"{journey.origin} to {journey.destination}: about "
                f"{journey.distance_km:.0f} km, roughly {journey.hours:.0f} hours "
                f"by {journey.mode} (per {journey.provider})"
            ),
            provider=PROVIDER_LIVE if journey.provider != "same-place" else journey.provider,
            detail=journey.to_json(),
        )
