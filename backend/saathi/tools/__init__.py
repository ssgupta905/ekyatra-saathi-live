"""The toolbox: fact sources the deterministic layer calls.

Collected here so there is one place to answer "what can this system find out,
and from where". Every tool in this package follows the same four rules — see
`base.py` — and the `Toolbox` adds the one thing they share at runtime: every
call is timed, written to the evidence ledger, and published to the console.

That last part matters more than it sounds. A number on a navigator's screen is
only checkable if the call that produced it left a trace, so a tool result is not
something the planner quietly consumes — it is a ledger row with a source, and it
appears in the activity strip with its own latency beside the planner's and the
model's. If a figure cannot be traced back to one of these calls, it should not
be on the screen.

Nothing in here is reachable from the language layer. Tools are called by code.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from .base import ToolResult, ToolUnavailable, call
from .cache import ReferenceCache
from .centres import CentreOption, CentreTool
from .geo import GeoTool, Journey
from .hospital import HospitalTool, ResourceStatus, Slot
from .lab import LabStatus, LabTool, ReportStatus
from .schemes import Entitlement, Holding, SchemeTool

logger = logging.getLogger(__name__)

__all__ = [
    "CentreOption",
    "CentreTool",
    "Entitlement",
    "GeoTool",
    "Holding",
    "HospitalTool",
    "Journey",
    "LabStatus",
    "LabTool",
    "ReportStatus",
    "ResourceStatus",
    "SchemeTool",
    "Slot",
    "ToolResult",
    "ToolUnavailable",
    "Toolbox",
    "build_toolbox",
    "call",
]


@dataclass
class Toolbox:
    """Every fact source, plus the hook that records what they said."""

    geo: GeoTool
    centres: CentreTool
    hospital: HospitalTool
    lab: LabTool
    schemes: SchemeTool
    cache: ReferenceCache
    #: Set by the runner. Receives every timed result so it can write the ledger
    #: row and publish the event. Left unset in tests and scripts, where a tool
    #: is just a function.
    on_result: Callable[[ToolResult[Any]], None] | None = None
    #: Count of calls per tool this run, surfaced in `GET /api/live` so an
    #: unexpected volume of lookups is visible rather than silent.
    counts: dict[str, int] = field(default_factory=dict)

    def run(self, fn: Callable[[], ToolResult[Any] | None]) -> ToolResult[Any] | None:
        """Call a tool, time it, record it. Never raises."""
        result = call(fn, on_result=self._record)
        return result

    def _record(self, result: ToolResult[Any]) -> None:
        self.counts[result.tool] = self.counts.get(result.tool, 0) + 1
        if self.on_result is not None:
            self.on_result(result)

    @property
    def providers(self) -> dict[str, str]:
        """Which tools are talking to something live, for the console to show."""
        return {
            "geo": "live" if self.geo._allow_network else "cache",  # noqa: SLF001
            "hospital": "live" if self.hospital.live else "desks",
            "schemes": "live" if self.schemes.live else "ledger",
            "lab": "observed",
            "centres": "configured",
        }

    def snapshot(self) -> dict:
        return {
            "providers": self.providers,
            "calls": dict(self.counts),
            "cached_facts": len(self.cache),
        }


def build_toolbox(settings: Settings) -> Toolbox:
    """Assemble the toolbox from configuration.

    Network access is off unless explicitly enabled: a demo makes far too many
    lookups for a public geocoder, so the cache is filled deliberately by
    `make fetch-reference` and read from thereafter. Each tool independently
    reports whether it has a live source, so the console can say so rather than
    implying everything is live.
    """
    cache = ReferenceCache(settings.reference_cache_path).load()
    geo = GeoTool(
        cache,
        geocoder_url=settings.geocoder_url,
        router_url=settings.router_url,
        allow_network=settings.tools_allow_network,
    )
    return Toolbox(
        geo=geo,
        centres=CentreTool(geo),
        hospital=HospitalTool(
            feed_url=settings.hospital_feed_url,
            allow_network=settings.tools_allow_network,
        ),
        lab=LabTool(),
        schemes=SchemeTool(
            feed_url=settings.scheme_feed_url,
            allow_network=settings.tools_allow_network,
        ),
        cache=cache,
    )
