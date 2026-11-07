"""The network answering a journey: asking the right organisation, and hearing back.

When a family's care steps say they can go, the parties the journey leans on (a
scheme desk, a pharmacy, a cab, a room) are each asked once, through whichever
organisation the directory says fits. A simulated organisation answers by itself
after its delay, so the chain moves in a demonstration; one that waits for people
is never answered here. Real organisations plug into the same readiness items.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from ..domain.affordability import Means, means_from
from ..domain.directory import Organisation, PartnerMode
from ..domain.enums import ReadinessKind, ReadinessStatus, SourceSystem, StepStatus
from ..domain.models import Patient, ReadinessItem
from ..domain.policy import HospitalPolicy
from ..orchestrator import DEFAULT_STAY_HOURS, choose_organisation, missing_needs, needs_for
from ..planner import tools
from ..ports.onboarding import OnboardingStore
from ..ports.registry import RegistryStore
from .world import LiveWorld

logger = logging.getLogger(__name__)

#: Needs met near the hospital rather than near home: a room, a pharmacy, a scheme desk.
_AT_THE_HOSPITAL = frozenset(
    {
        ReadinessKind.STAY,
        ReadinessKind.MEDICINE,
        ReadinessKind.INSURANCE,
        ReadinessKind.SLOT,
        ReadinessKind.DOCTOR,
        ReadinessKind.BED,
    }
)

_CHOICE_KEYS = {
    ReadinessKind.TRANSPORT: "transport",
    ReadinessKind.STAY: "stay",
    ReadinessKind.MEDICINE: "medicine",
    ReadinessKind.INSURANCE: "insurance",
}


class PartnerDesk:
    def __init__(
        self,
        *,
        world: LiveWorld,
        registry: RegistryStore,
        onboarding: OnboardingStore | None,
        graph_for: Callable[[Patient], object],
        rules_for: Callable[[str], HospitalPolicy | None],
        journey_hours: Callable[[Patient], float | None],
        auto: bool = True,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._world = world
        self._registry = registry
        self._onboarding = onboarding
        self._graph_for = graph_for
        self._rules_for = rules_for
        self._journey_hours = journey_hours
        self._now = now
        #: Whether the desk asks for a journey's needs by itself. Staff can always ask.
        self.auto = auto

    # ---------------- asking ----------------

    def _organisations(self) -> tuple[Organisation, ...]:
        return self._registry.organisations()

    def _preferred(self, patient_id: str, kind: ReadinessKind) -> str | None:
        """The organisation staff chose for this family and this need, if they did."""
        if self._onboarding is None or kind not in _CHOICE_KEYS:
            return None
        saved = self._onboarding.section(patient_id, "partners")
        return (saved[0].get(_CHOICE_KEYS[kind]) or None) if saved else None

    def means_for(self, patient_id: str) -> Means:
        """What this family can carry, read fresh from what onboarding was told.

        Derived here and thrown away again. Nothing stores it: a column holding
        how poor a family is would be sorted by sooner or later.
        """
        if self._onboarding is None:
            return Means.NOT_STATED
        saved = self._onboarding.section(patient_id, "background")
        if not saved:
            return Means.NOT_STATED
        answers = saved[0]
        return means_from(
            ration_card=str(answers.get("ration_card") or ""),
            income_band=str(answers.get("income_band") or ""),
        )

    def _care_steps_say_go(self, patient: Patient) -> bool:
        """The prerequisites are all done, whatever the parties have or have not said yet."""
        steps = self._world.steps_for(patient.id)
        target = tools.find_step(steps, self._world.target_kind_for(patient.id))
        if target is None or target.status is StepStatus.CANCELLED:
            return False
        graph = self._graph_for(patient)
        return not tools.unmet_prerequisites(target, steps, graph) and not (
            tools.missing_prerequisite_kinds(target, steps, graph)
        )

    def _request(self, patient: Patient, kind: ReadinessKind, org: Organisation) -> ReadinessItem:
        alternate = next(
            (o for o in self._organisations() if o.id == org.alternate_id and o.active), None
        )
        now = self._now()
        item = ReadinessItem(
            id=f"{patient.id}-{kind.value}",
            patient_id=patient.id,
            kind=kind,
            party=org.name,
            status=ReadinessStatus.PENDING,
            detail=f"asked at {now:%H:%M}",
            alternative_available=alternate is not None,
            source=SourceSystem.PARTNER,
            partner_id=org.id,
            due_at=now + timedelta(seconds=org.delay_seconds)
            if org.mode is PartnerMode.SIMULATED
            else None,
        )
        return self._world.set_readiness_item(item)

    async def ask_for_needs(self, patient_id: str) -> bool:
        """Ask for whatever this journey needs and nobody has been asked about. True if it asked."""
        patient = self._world.patient(patient_id)
        if not self.auto or patient is None or not self._care_steps_say_go(patient):
            return False
        pathway_target = self._world.target_kind_for(patient_id)
        from ..domain.pathway import get_pathway

        hours = await asyncio.to_thread(self._journey_hours, patient)
        policy = self._rules_for(patient.hospital_id)
        threshold = policy.stay_rather_than_travel_hours if policy else DEFAULT_STAY_HOURS
        needs = needs_for(
            get_pathway(patient.pathway_id),
            pathway_target,
            round_trip_hours=hours,
            stay_threshold_hours=threshold,
        )
        organisations = self._organisations()
        hospital = next(
            (h for h in self._registry.hospitals() if h.id == patient.hospital_id), None
        )
        means = self.means_for(patient_id)
        asked = False
        for kind in missing_needs(needs, self._world.readiness_for(patient_id)):
            near_hospital = hospital is not None and kind in _AT_THE_HOSPITAL
            place = hospital.place if near_hospital else patient.home_district
            org = choose_organisation(
                kind,
                district=place,
                hospital_id=patient.hospital_id,
                organisations=organisations,
                preferred_id=self._preferred(patient_id, kind),
                means=means,
            )
            if org is None:
                logger.info("nobody in the directory for %s of %s", kind.value, patient_id)
                continue
            self._request(patient, kind, org)
            asked = True
        return asked

    # ---------------- hearing back ----------------

    def due(self) -> list[tuple[str, ReadinessItem]]:
        """Pending requests whose simulated organisation should have answered by now."""
        now = self._now()
        found = []
        for patient in self._world.patients():
            for item in self._world.readiness_for(patient.id):
                if (
                    item.status is ReadinessStatus.PENDING
                    and item.partner_id
                    and item.due_at is not None
                    and item.due_at <= now
                ):
                    found.append((patient.id, item))
        return found

    def settle(self, item: ReadinessItem) -> ReadinessItem | None:
        """A simulated organisation's answer. None for one that is not simulated."""
        org = next((o for o in self._organisations() if o.id == item.partner_id), None)
        if org is None or org.mode is not PartnerMode.SIMULATED:
            return None
        if org.answer == "ready":
            answered = item.model_copy(
                update={
                    "status": ReadinessStatus.READY,
                    "detail": f"confirmed by {org.name}",
                    "due_at": None,
                }
            )
        else:
            alternate = next(
                (o for o in self._organisations() if o.id == org.alternate_id and o.active), None
            )
            answered = item.model_copy(
                update={
                    "status": ReadinessStatus.BLOCKED,
                    "detail": f"{org.name} cannot do it",
                    "alternative_available": alternate is not None,
                    "due_at": None,
                }
            )
        return self._world.set_readiness_item(answered)

    def ask(self, patient_id: str, kind: ReadinessKind, organisation_id: str) -> ReadinessItem:
        """Staff ask a particular organisation for a need, replacing what was there."""
        patient = self._world.patient(patient_id)
        org = next((o for o in self._organisations() if o.id == organisation_id), None)
        if patient is None:
            raise LookupError(patient_id)
        if org is None or not org.active:
            raise ValueError("that organisation is not in the directory, or is not active")
        return self._request(patient, kind, org)

    def rebook(self, patient_id: str, item_id: str) -> ReadinessItem:
        """Ask the alternate of a party that could not. A person decides this, not the desk."""
        item = next((i for i in self._world.readiness_for(patient_id) if i.id == item_id), None)
        if item is None:
            raise LookupError(item_id)
        patient = self._world.patient(patient_id)
        if patient is None:
            raise LookupError(patient_id)
        org = next((o for o in self._organisations() if o.id == item.partner_id), None)
        alternate = next(
            (o for o in self._organisations() if org and o.id == org.alternate_id and o.active),
            None,
        )
        if alternate is None:
            raise ValueError("there is no alternative to ask")
        return self._request(patient, item.kind, alternate)
