"""Which centre can do this step, and which of those is nearest home.

The deck makes a standing promise — "Saathi offers options such as a nearer
centre; staff confirm them" — and the brief turns on it twice: Anita's echo at
Darbhanga instead of the hub, and whether her radiotherapy could later happen at
Muzaffarpur rather than Mumbai.

Two inputs, and neither is written here. *Which centres exist and what each can
do* is `HospitalPolicy.centres`, configuration a health system owns. *How far
each one is* comes from the geo tool, fetched. This module only puts the two
together and sorts by what the journey costs the family.

It offers; it does not move anybody. Changing where treatment happens is a
clinical decision, so a nearer centre becomes a `PlanOption` for a person to
approve, exactly like every other option. An empty directory produces no
options, which is the right answer before anyone has configured one — better a
system that says nothing than one that invents a clinic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..domain.enums import SourceSystem, StepKind
from ..domain.policy import Centre, HospitalPolicy
from .base import PROVIDER_LOCAL, ToolResult
from .geo import GeoTool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CentreOption:
    """A centre that can do the step, and what reaching it costs."""

    centre: Centre
    hours: float
    distance_km: float
    provider: str

    @property
    def is_hub(self) -> bool:
        return self.centre.kind == "hub"

    def to_json(self) -> dict:
        return {
            "id": self.centre.id,
            "name": self.centre.name,
            "place": self.centre.place,
            "kind": self.centre.kind,
            "hours": round(self.hours, 1),
            "round_trip_hours": round(self.hours * 2, 1),
            "distance_km": round(self.distance_km, 1),
            "provider": self.provider,
        }


class CentreTool:
    """The configured centre network, ranked by fetched travel time."""

    name = "centres.nearest"

    def __init__(self, geo: GeoTool) -> None:
        self._geo = geo

    def options_for(
        self,
        home: str,
        kind: StepKind,
        policy: HospitalPolicy,
        *,
        limit: int = 5,
    ) -> ToolResult[tuple[CentreOption, ...]] | None:
        """Centres that can do `kind`, nearest first by travel time.

        Ranked by hours rather than kilometres: two centres the same distance
        away are not the same distance away when one is on a rail line and the
        other is across a river. A centre whose journey could not be fetched is
        left out rather than ranked on a guess.
        """
        capable = policy.centres_for(kind)
        if not capable:
            return None

        options: list[CentreOption] = []
        unreachable: list[str] = []
        for centre in capable:
            leg = self._geo.journey(home, centre.place)
            if leg is None:
                unreachable.append(centre.name)
                continue
            options.append(
                CentreOption(
                    centre=centre,
                    hours=leg.value.hours,
                    distance_km=leg.value.distance_km,
                    provider=leg.value.provider,
                )
            )
        if not options:
            return None

        options.sort(key=lambda o: (o.hours, o.distance_km))
        ranked = tuple(options[:limit])
        nearest = ranked[0]
        return ToolResult(
            value=ranked,
            tool=self.name,
            source=SourceSystem.DERIVED,
            source_record_id=f"centres:{home}:{kind.value}",
            claim=(
                f"{len(capable)} centres can do {kind.value.replace('_', ' ')}; "
                f"nearest to {home} is {nearest.centre.name}, about "
                f"{nearest.hours:.0f} hours away"
            ),
            provider=PROVIDER_LOCAL,
            detail={
                "options": [o.to_json() for o in ranked],
                "unreachable": unreachable,
            },
        )

    def nearer_than(
        self,
        home: str,
        kind: StepKind,
        current_centre_id: str,
        policy: HospitalPolicy,
    ) -> ToolResult[tuple[CentreOption, ...]] | None:
        """Only centres strictly closer than where the step is booked now.

        Returns None when nothing is nearer, which is the common case and must
        not be dressed up as a choice. An "alternative" that costs the family
        more is not an alternative, and offering one wastes the scarcest thing
        in this system: a navigator's attention.
        """
        ranked = self.options_for(home, kind, policy, limit=len(policy.centres) or 1)
        if ranked is None:
            return None

        current = next(
            (o for o in ranked.value if o.centre.id == current_centre_id), None
        )
        if current is None:
            return None

        nearer = tuple(o for o in ranked.value if o.hours < current.hours)
        if not nearer:
            return None

        best = nearer[0]
        saved_each_way = current.hours - best.hours
        return ToolResult(
            value=nearer,
            tool="centres.nearer",
            source=SourceSystem.DERIVED,
            source_record_id=f"nearer:{home}:{kind.value}:{current_centre_id}",
            claim=(
                f"{best.centre.name} can do {kind.value.replace('_', ' ')} and is "
                f"about {saved_each_way * 2:.0f} hours closer, round trip, than "
                f"{current.centre.name}"
            ),
            provider=PROVIDER_LOCAL,
            detail={
                "current": current.to_json(),
                "nearer": [o.to_json() for o in nearer],
                "round_trip_hours_saved": round(saved_each_way * 2, 1),
            },
        )
