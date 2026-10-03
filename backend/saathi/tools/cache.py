"""A cache that remembers where every answer came from.

The point of this file is a distinction that is easy to lose: there is a large
difference between

    CORRIDORS = {("Gaya", "Mumbai"): Corridor("train", 30.0, 700.0)}

and a record saying *we asked OpenStreetMap at 14:02 on 3 October 2026 and it
said 1,612 km*. The first is a number somebody chose, and a plan built on it
cannot be wrong in any interesting way because the answer was the input. The
second is evidence, and it can be checked, re-fetched, and found to have changed.

So nothing in this package ships with facts about the world baked in. Tools
fetch from real services, and every fetched value is stored here with its
source URL, the time it was fetched and a hash of the raw response. A cached
answer is still real data really fetched — it just says so, and says when.

A cold cache with no network is not a licence to invent. The tool returns None,
the planner sees an unknown, and the decision is UNCERTAIN until somebody can
answer. That is the correct failure: a family told "we don't know yet" has lost
nothing, and a family told a number we made up may lose a journey.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Where the fetched-facts cache lives. A plain JSON file so it can be read,
#: diffed and argued with — if a number in here is wrong, that should be
#: visible in a pull request, not buried in a binary store.
DEFAULT_CACHE_PATH = Path("data/reference_cache.json")

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CachedFact:
    """One answer from a real service, and everything needed to re-check it."""

    key: str
    value: Any
    #: The service that answered, e.g. "nominatim" or "osrm".
    provider: str
    #: The exact request that produced it, so anyone can repeat it.
    source_url: str
    fetched_at: datetime
    #: SHA-256 of the raw response body. Two caches claiming the same fact with
    #: different hashes means the upstream data moved.
    response_hash: str

    def to_json(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "provider": self.provider,
            "source_url": self.source_url,
            "fetched_at": self.fetched_at.isoformat(),
            "response_hash": self.response_hash,
        }

    @classmethod
    def from_json(cls, raw: dict) -> CachedFact:
        return cls(
            key=raw["key"],
            value=raw["value"],
            provider=raw["provider"],
            source_url=raw["source_url"],
            fetched_at=datetime.fromisoformat(raw["fetched_at"]),
            response_hash=raw["response_hash"],
        )

    @property
    def age_days(self) -> float:
        return (datetime.now(UTC) - self.fetched_at).total_seconds() / 86400


def response_hash(body: str | bytes) -> str:
    payload = body.encode("utf-8") if isinstance(body, str) else body
    return hashlib.sha256(payload).hexdigest()


class ReferenceCache:
    """Fetched facts, on disk, with provenance. Safe across threads."""

    def __init__(self, path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.path = Path(path)
        self._facts: dict[str, CachedFact] = {}
        self._lock = threading.Lock()
        self._loaded = False

    # ---------------- disk ----------------

    def load(self) -> ReferenceCache:
        with self._lock:
            if not self.path.exists():
                self._loaded = True
                return self
            try:
                raw = json.loads(self.path.read_text())
            except (OSError, json.JSONDecodeError):
                logger.warning("reference cache at %s is unreadable; starting cold", self.path)
                self._loaded = True
                return self
            if raw.get("schema") != SCHEMA_VERSION:
                logger.warning("reference cache schema mismatch; starting cold")
                self._loaded = True
                return self
            self._facts = {
                entry["key"]: CachedFact.from_json(entry) for entry in raw.get("facts", [])
            }
            self._loaded = True
        return self

    def save(self) -> None:
        with self._lock:
            facts = sorted(self._facts.values(), key=lambda f: f.key)
            payload = {
                "schema": SCHEMA_VERSION,
                "written_at": datetime.now(UTC).isoformat(),
                "note": (
                    "Fetched from the named services; not authored by hand. "
                    "Re-run `make fetch-reference` to refresh."
                ),
                "facts": [f.to_json() for f in facts],
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")

    # ---------------- use ----------------

    def get(self, key: str) -> CachedFact | None:
        if not self._loaded:
            self.load()
        with self._lock:
            return self._facts.get(key)

    def put(
        self,
        key: str,
        value: Any,
        *,
        provider: str,
        source_url: str,
        raw_body: str | bytes,
    ) -> CachedFact:
        fact = CachedFact(
            key=key,
            value=value,
            provider=provider,
            source_url=source_url,
            fetched_at=datetime.now(UTC),
            response_hash=response_hash(raw_body),
        )
        with self._lock:
            self._facts[key] = fact
        return fact

    def __len__(self) -> int:
        if not self._loaded:
            self.load()
        return len(self._facts)

    def keys(self) -> tuple[str, ...]:
        if not self._loaded:
            self.load()
        with self._lock:
            return tuple(sorted(self._facts))
