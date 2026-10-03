"""What the hospital can actually offer, and when.

There is no public API for whether MRI-2 is working this morning. That fact
exists in exactly one place — the radiology desk — and the way it reaches this
system is a person pressing a button, which is already how `world.raise_disruption`
works. So this tool does not invent a feed; it reads the records the hospital's
own staff have entered, and adds the one thing they imply but do not state: the
dates and times a step can actually be booked into.

Two sources, both real, neither authored here:

* **Availability** comes from the desks. A resource is down because somebody at
  that desk said so, with their name on it.
* **Slot times** come from `HospitalPolicy`, which the admin console owns. "The
  MRI runs at 08:00, 11:00 and 15:00" is a fact about this hospital, and if it
  is wrong the fix is an admin changing it, not a developer editing a module.

When `SAATHI_HOSPITAL_FEED_URL` is configured the status question goes there
first, because a live feed beats a desk's memory. Without it, the desks are the
feed — which is exactly the pilot's stated starting point: "the pilot runs on
staff entering status in the console".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from ..domain.enums import SourceSystem, StepKind
from ..domain.models import Disruption, Resource
from ..domain.policy import HospitalPolicy
from .base import PROVIDER_LIVE, PROVIDER_LOCAL, ToolResult, ToolUnavailable

logger = logging.getLogger(__name__)

#: How far ahead a slot search looks before giving up. A step that cannot be
#: placed inside a month is not a scheduling problem, it is a conversation.
SLOT_HORIZON_DAYS = 45


@dataclass(frozen=True)
class ResourceStatus:
    resource_id: str
    display_name: str
    up: bool
    down_from: date | None = None
    down_until: date | None = None
    note: str = ""
    #: Who reported it, so the console can say "per the radiology desk".
    reported_by: str = ""

    def to_json(self) -> dict:
        return {
            "resource_id": self.resource_id,
            "display_name": self.display_name,
            "up": self.up,
            "down_from": self.down_from.isoformat() if self.down_from else None,
            "down_until": self.down_until.isoformat() if self.down_until else None,
            "note": self.note,
            "reported_by": self.reported_by,
        }


@dataclass(frozen=True)
class Slot:
    """A bookable moment: the day a resource is free and a time it runs at."""

    day: date
    time: str | None
    resource_id: str | None

    @property
    def label(self) -> str:
        return f"{self.day:%a %d %b}" + (f", {self.time}" if self.time else "")

    def to_json(self) -> dict:
        return {
            "day": self.day.isoformat(),
            "time": self.time,
            "resource_id": self.resource_id,
            "label": self.label,
        }


class HospitalTool:
    """Resource status and bookable slots, from the desks and the admin rules."""

    name = "hospital.status"

    def __init__(
        self,
        *,
        feed_url: str | None = None,
        allow_network: bool = False,
        timeout: float = 5.0,
    ) -> None:
        self._feed_url = feed_url.rstrip("/") if feed_url else None
        self._allow_network = allow_network
        self._timeout = timeout

    @property
    def live(self) -> bool:
        return bool(self._feed_url and self._allow_network)

    # ---------------- status ----------------

    def resource_status(
        self,
        resource: Resource,
        disruptions: tuple[Disruption, ...],
        on_day: date,
    ) -> ToolResult[ResourceStatus] | None:
        """Is this resource working on `on_day`, and if not, until when."""
        if self.live:
            live = self._from_feed(resource, on_day)
            if live is not None:
                return live

        covering = [
            d
            for d in disruptions
            if d.resource_id == resource.id
            and d.unavailable_from <= on_day
            and (d.unavailable_to is None or on_day <= d.unavailable_to)
        ]
        if covering:
            worst = max(
                covering,
                key=lambda d: d.unavailable_to or date.max,
            )
            status = ResourceStatus(
                resource_id=resource.id,
                display_name=resource.display_name,
                up=False,
                down_from=worst.unavailable_from,
                down_until=worst.unavailable_to,
                note=worst.note,
                reported_by=worst.raised_by.value,
            )
        else:
            status = ResourceStatus(
                resource_id=resource.id, display_name=resource.display_name, up=True
            )
        return self._status_result(status, PROVIDER_LOCAL)

    def _from_feed(self, resource: Resource, on_day: date) -> ToolResult[ResourceStatus] | None:
        url = f"{self._feed_url}/resources/{resource.id}"
        try:
            response = httpx.get(url, params={"on": on_day.isoformat()}, timeout=self._timeout)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolUnavailable(f"hospital feed: {exc}") from exc

        status = ResourceStatus(
            resource_id=resource.id,
            display_name=resource.display_name,
            up=bool(body.get("up", True)),
            down_from=_maybe_date(body.get("down_from")),
            down_until=_maybe_date(body.get("down_until")),
            note=str(body.get("note", "")),
            reported_by="hospital feed",
        )
        return self._status_result(status, PROVIDER_LIVE)

    # ---------------- slots ----------------

    def slots(
        self,
        kind: StepKind,
        policy: HospitalPolicy,
        disruptions: tuple[Disruption, ...],
        *,
        resource_id: str | None,
        not_before: date,
        limit: int = 6,
    ) -> ToolResult[tuple[Slot, ...]] | None:
        """The next bookable moments for a step, soonest first.

        A day is offered when the hospital's rules allow the step that day and
        no desk has reported its resource down. Times come from the admin's slot
        template; a step with none configured returns days without times rather
        than inventing an hour.
        """
        times = policy.step(kind).slot_times if policy.step(kind) else ()
        found: list[Slot] = []
        day = policy.next_slot(kind, not_before)
        horizon = not_before + timedelta(days=SLOT_HORIZON_DAYS)

        while day <= horizon and len(found) < limit:
            blocked = any(
                d.resource_id == resource_id
                and d.unavailable_from <= day
                and (d.unavailable_to is None or day <= d.unavailable_to)
                for d in disruptions
            )
            if not blocked:
                if times:
                    for clock in times:
                        found.append(Slot(day=day, time=clock, resource_id=resource_id))
                        if len(found) >= limit:
                            break
                else:
                    found.append(Slot(day=day, time=None, resource_id=resource_id))
            day = policy.next_slot(kind, day + timedelta(days=1))

        if not found:
            return None

        offered = tuple(found[:limit])
        return ToolResult(
            value=offered,
            tool="hospital.slots",
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=f"slots:{resource_id or kind.value}:{not_before.isoformat()}",
            claim=(
                f"next opening for {kind.value.replace('_', ' ')}"
                + (f" on {resource_id}" if resource_id else "")
                + f" is {offered[0].label}"
            ),
            provider=PROVIDER_LIVE if self.live else PROVIDER_LOCAL,
            detail={"slots": [s.to_json() for s in offered]},
        )

    # ---------------- plumbing ----------------

    def _status_result(self, status: ResourceStatus, provider: str) -> ToolResult[ResourceStatus]:
        if status.up:
            claim = f"{status.display_name} is working"
        else:
            until = (
                f" until {status.down_until:%d %b}" if status.down_until else " indefinitely"
            )
            claim = f"{status.display_name} is out of service{until}"
        return ToolResult(
            value=status,
            tool=self.name,
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=f"resource:{status.resource_id}",
            claim=claim,
            provider=provider,
            detail=status.to_json(),
        )


def _maybe_date(raw: str | None) -> date | None:
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None
