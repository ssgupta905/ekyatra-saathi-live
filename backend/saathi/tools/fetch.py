"""Fill the reference cache from real services.

    python -m saathi.tools.fetch

This is the only place in the project that is allowed to reach out and ask the
world how far apart two places are. It runs deliberately, from a command
somebody types, and writes what it got — with the URL and the timestamp — into
`data/reference_cache.json`. During a live run the tools read that file and do
not call out at all, because serving a demo means dozens of lookups a second and
a public geocoder is not for that.

The place names are read out of the cohort and the hospital configuration rather
than listed here. If somebody adds a district to `synthetic/generate.py`, the
next fetch picks it up; there is no second list to keep in step.

Nominatim asks for one request a second and an identifying User-Agent, and this
honours both. Be a good citizen: the services are free and somebody pays for them.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..config import get_settings
from .cache import DEFAULT_CACHE_PATH, ReferenceCache
from .geo import GeoTool

#: Nominatim's published rate limit.
POLITE_DELAY_SECONDS = 1.1


def cohort_places() -> list[str]:
    """Every district the synthetic cohort and the scripted families live in."""
    from ..synthetic.generate import DISTRICTS

    names = {district for district, _lang, _km in DISTRICTS}
    # The scripted families' districts, read off the seeds rather than retyped.
    from datetime import date

    from ..synthetic.scripted import seed_anita_devi, seed_shambhu_prasad

    today = date.today()
    for seed in (seed_shambhu_prasad, seed_anita_devi):
        result = seed(today)
        names.add(result[0].home_district)
    return sorted(names)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fill the reference cache from real services.")
    parser.add_argument(
        "--hospital",
        action="append",
        default=[],
        metavar="ID=PLACE",
        help="Where a hospital is, e.g. TMH-MUM=Mumbai. Repeatable.",
    )
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    parser.add_argument("--geocoder", default=None)
    parser.add_argument("--router", default=None)
    parser.add_argument(
        "--refresh", action="store_true", help="Re-fetch entries already cached."
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    hospitals: dict[str, str] = {}
    for pair in args.hospital or settings.hospital_places:
        hospital_id, _, place = pair.partition("=")
        if not place:
            parser.error(f"--hospital needs ID=PLACE, got {pair!r}")
        hospitals[hospital_id.strip()] = place.strip()

    if not hospitals:
        parser.error(
            "no hospital locations. Pass --hospital TMH-MUM=Mumbai, or set "
            "SAATHI_HOSPITAL_PLACES in the environment."
        )

    cache = ReferenceCache(Path(args.cache)).load()
    before = len(cache)
    geo = GeoTool(
        cache,
        geocoder_url=args.geocoder or settings.geocoder_url,
        router_url=args.router or settings.router_url,
        allow_network=True,
    )

    places = cohort_places()
    destinations = sorted(set(hospitals.values()))
    print(f"places: {len(places)} · hospitals: {len(destinations)} · cache: {args.cache}")

    for name in [*places, *destinations]:
        if not args.refresh and cache.get(f"geocode:{name}|India") is not None:
            continue
        found = geo.geocode(name)
        print(f"  geocode {name:<16} {'ok' if found else 'NOT FOUND'}")
        time.sleep(POLITE_DELAY_SECONDS)

    for origin in places:
        for destination in destinations:
            if origin == destination:
                continue
            if not args.refresh and cache.get(f"route:{origin}->{destination}") is not None:
                continue
            result = geo.journey(origin, destination)
            if result is None:
                print(f"  route   {origin:<16} -> {destination:<12} UNAVAILABLE")
            else:
                j = result.value
                print(
                    f"  route   {origin:<16} -> {destination:<12} "
                    f"{j.distance_km:>7.0f} km  {j.hours:>5.1f} h"
                )
            time.sleep(POLITE_DELAY_SECONDS)

    cache.save()
    print(f"\nwrote {len(cache)} facts ({len(cache) - before} new) to {args.cache}")
    print("every entry carries the URL it came from and when it was fetched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
