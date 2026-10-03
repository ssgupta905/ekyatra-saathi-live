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
from .base import ToolUnavailable
from .cache import DEFAULT_CACHE_PATH, ReferenceCache
from .geo import GeoTool

#: Nominatim's published rate limit.
POLITE_DELAY_SECONDS = 1.1

#: Public endpoints time out. Retry a couple of times, then move on and record
#: what we could not get rather than losing the whole run to one bad TLS
#: handshake — which is exactly what happened the first time this ran.
ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 3.0

#: Write the cache every this many successful fetches. A long run that dies
#: two-thirds through should keep the two-thirds.
SAVE_EVERY = 10


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
    # Destinations include the day-care centres, not only the hubs: without a
    # route to them, "is anywhere nearer?" has no answer and the nearer-centre
    # option silently never appears.
    destinations = sorted(set(hospitals.values()) | set(settings.centre_places))
    print(f"places: {len(places)} · hospitals: {len(destinations)} · cache: {args.cache}")

    fetched = 0
    failed: list[str] = []

    def attempt(label: str, fn):
        """Try a fetch a few times, then give up on it and keep going."""
        nonlocal fetched
        for tryno in range(1, ATTEMPTS + 1):
            try:
                result = fn()
            except ToolUnavailable as exc:
                if tryno == ATTEMPTS:
                    failed.append(label)
                    print(f"  {label:<44} UNAVAILABLE ({exc})")
                    return None
                time.sleep(RETRY_BACKOFF_SECONDS * tryno)
                continue
            fetched += 1
            if fetched % SAVE_EVERY == 0:
                cache.save()
            return result
        return None

    try:
        for name in [*places, *destinations]:
            if not args.refresh and cache.get(f"geocode:{name}|India") is not None:
                continue
            found = attempt(f"geocode {name}", lambda n=name: geo.geocode(n))
            print(f"  geocode {name:<16} {'ok' if found else 'not found'}")
            time.sleep(POLITE_DELAY_SECONDS)

        for origin in places:
            for destination in destinations:
                if origin == destination:
                    continue
                if not args.refresh and cache.get(f"route:{origin}->{destination}") is not None:
                    continue
                label = f"route   {origin} -> {destination}"
                result = attempt(label, lambda o=origin, d=destination: geo.journey(o, d))
                if result is not None:
                    j = result.value
                    print(
                        f"  route   {origin:<16} -> {destination:<14} "
                        f"{j.distance_km:>7.0f} km  {j.hours:>5.1f} h"
                    )
                time.sleep(POLITE_DELAY_SECONDS)
    except KeyboardInterrupt:
        print("\ninterrupted — saving what was fetched so far")
    finally:
        # Always. A public service timing out must not cost us the work that
        # already succeeded.
        cache.save()

    print(f"\nwrote {len(cache)} facts ({len(cache) - before} new) to {args.cache}")
    if failed:
        print(f"{len(failed)} could not be fetched; re-run to pick them up:")
        for label in failed[:10]:
            print(f"  - {label}")
    print("every entry carries the URL it came from and when it was fetched.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
