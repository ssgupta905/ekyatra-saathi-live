"""The live world: a cohort that actually changes.

`synthetic/generate.py` produces a cohort frozen at one date. This wraps it in
the one thing a demo needs and a snapshot cannot give: time passing, and steps
changing status because time passed.

Two rules hold here.

**Ground truth is never consulted to decide anything.** The planted
`true_ready_on` dates say when a report *really* lands, which is exactly what
the hospital would know and Saathi would not. The world uses them to decide when
to release a report into the feed; the planner never sees them, and still has to
work the release out from the conformal model like it would in a hospital.

**The world does not release a report by itself.** A release becomes a desk
candidate — a draft a human confirms — because that is how a report actually
reaches a hospital system. `apply_release` is the only path that changes a step,
and something has to call it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta

from ..domain.enums import (
    REPORT_STEPS,
    DisruptionKind,
    Language,
    ResourceKind,
    SourceSystem,
    StepKind,
    StepStatus,
)
from ..domain.models import (
    CareStep,
    Disruption,
    MaintenanceCycle,
    Patient,
    ReadinessItem,
    Resource,
)
from ..domain.pathway import get_pathway
from ..ports.records import RecordStore, TurnaroundObservation
from ..synthetic.generate import GroundTruth, SyntheticCohort, generate_cohort
from ..synthetic.scripted import (
    ANITA_ID,
    DAY_CARE_PHARMACY,
    ECHO_CARDIOLOGIST,
    MRI_2,
    PET_CT_SCANNER,
    SHAMBHU_ID,
    build_scripted_cohort,
)
from .clock import SimulationClock, WallClock

#: Statuses a step can still be in when a disruption might touch it. A
#: completed or cancelled step is done — an outage announced afterwards
#: cannot affect it.
_DISRUPTIBLE = frozenset(
    {
        StepStatus.NOT_SCHEDULED,
        StepStatus.SCHEDULED,
        StepStatus.PENDING_RESULT,
    }
)

logger = logging.getLogger(__name__)


@dataclass
class DeskCandidate:
    """A report release waiting for a desk clerk to confirm it.

    `note` is what the ward actually sends — free text. `parsed` is the
    structured update derived from it. Nothing moves until `confirmed`.
    """

    id: str
    patient_id: str
    step_id: str
    step_kind: str
    note: str
    parsed: dict
    raised_on: str
    raised_at: datetime
    #: Ticks remaining before the desk is assumed to have confirmed it. An
    #: unattended demo must still progress; the event says it was automatic.
    ticks_until_auto: int
    #: "groq" when an actor drafted the note, "template" when it did not.
    drafted_by: str = "template"
    confirmed: bool = False
    confirmed_automatically: bool = False

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "step_id": self.step_id,
            "step_kind": self.step_kind,
            "note": self.note,
            "parsed": self.parsed,
            "raised_on": self.raised_on,
            "raised_at": self.raised_at.isoformat(),
            "ticks_until_auto": self.ticks_until_auto,
            "drafted_by": self.drafted_by,
        }


@dataclass
class LiveWorld:
    """Mutable cohort state plus the desk queue that gates changes to it."""

    clock: SimulationClock | WallClock
    cohort: SyntheticCohort
    #: Mutable per patient. The `CareStep`s themselves stay frozen and are
    #: replaced wholesale, so nothing ever holds a half-updated record.
    steps: dict[str, list[CareStep]] = field(default_factory=dict)
    desk: dict[str, DeskCandidate] = field(default_factory=dict)
    #: Bookable hospital things (machines, staff roles, supplies) a desk can
    #: report unavailable. Registered once, independent of cohort resets.
    resources: dict[str, Resource] = field(default_factory=dict)
    #: Every disruption ever raised, keyed by id, newest-affecting-state read
    #: via `open_disruptions`.
    disruptions: dict[str, Disruption] = field(default_factory=dict)
    #: Patients on a repeating maintenance schedule, by patient id.
    maintenance_cycles: dict[str, MaintenanceCycle] = field(default_factory=dict)
    #: What the other parties have said about each patient's journey, by patient
    #: id then item id. Held in memory until orchestration state is persisted.
    readiness_items: dict[str, dict[str, ReadinessItem]] = field(default_factory=dict)
    #: patient id -> disruption id, set while a patient has ranked options
    #: waiting on a human and cleared once approved. What a process-only
    #: inbound answer reads to say "the doctor decides" vs "still working it out".
    pending_approval: dict[str, str] = field(default_factory=dict)
    #: Which step kind each patient is currently planned towards. Everyone
    #: not listed targets `REVIEW_CONSULT`, the pathway's one terminal visit;
    #: a maintenance patient targets their next `MAINTENANCE_DOSE` instead.
    plan_targets: dict[str, StepKind] = field(default_factory=dict)
    #: step id -> patient id. Step ids are patient-prefixed by convention, but
    #: an index means nothing here depends on that convention holding.
    index: dict[str, str] = field(default_factory=dict)
    #: Patients whose messages are rendered live and whose actors run. All
    #: patients are still planned every tick — this caps API spend, not scope.
    watched: tuple[str, ...] = ()
    seed: int = 20260925
    n_patients: int = 50
    n_watched: int = 8
    auto_confirm_ticks: int = 2
    #: Where the treating hospital physically is, so a journey to it can be
    #: fetched. Configuration, not a constant: a pilot elsewhere changes it.
    hospital_place: str = "Mumbai"
    #: True when this world carries the two scripted demo families alongside
    #: the cohort — see `synthetic/scripted.py`. Drives resource registration
    #: and maintenance-cycle setup in `_load_cohort`.
    scripted: bool = False
    #: True when the records are a hospital's own, on the real calendar. Nothing
    #: is simulated, nothing is reset, and ground truth does not exist.
    real: bool = False
    #: Where changes are written through to. None in the demo, which should not
    #: leave files behind.
    store: RecordStore | None = None

    def target_kind_for(self, patient_id: str) -> StepKind:
        if patient_id in self.plan_targets:
            return self.plan_targets[patient_id]
        patient = self.patient(patient_id)
        # The pathway's own terminal visit: a review consult for oncology, a
        # session for dialysis.
        return get_pathway(patient.pathway_id if patient else None).default_target

    @classmethod
    def build(
        cls,
        *,
        start: date | None = None,
        seconds_per_day: float = 4.0,
        n_patients: int = 50,
        n_watched: int = 8,
        seed: int = 20260925,
        auto_confirm_ticks: int = 2,
        scripted: bool = False,
    ) -> LiveWorld:
        start = start or date.today()
        cohort = (
            build_scripted_cohort(n_patients=max(n_patients - 2, 0), seed=seed, today=start)[0]
            if scripted
            else generate_cohort(n_patients=n_patients, seed=seed, today=start)
        )
        world = cls(
            clock=SimulationClock(start=start, seconds_per_day=seconds_per_day),
            cohort=cohort,
            seed=seed,
            n_patients=n_patients,
            n_watched=n_watched,
            auto_confirm_ticks=auto_confirm_ticks,
            scripted=scripted,
        )
        world._load_cohort(cohort)
        if scripted:
            world._wire_scripted_demo(start)
        return world

    @classmethod
    def build_real(
        cls, store: RecordStore, clock_source, *, tick_seconds: float = 300.0
    ) -> LiveWorld:
        """A world made of whatever the store holds, on the real calendar."""
        records = store.load()
        world = cls(
            clock=WallClock(clock_source, tick_seconds=tick_seconds),
            cohort=SyntheticCohort(
                patients=records.patients, steps={}, turnaround=(), ground_truth={}
            ),
            real=True,
            store=store,
            auto_confirm_ticks=0,
        )
        world.steps = {pid: list(rows) for pid, rows in records.steps.items()}
        for patient in records.patients:
            world.steps.setdefault(patient.id, [])
        world.index = {row.id: pid for pid, rows in world.steps.items() for row in rows}
        world.resources = {r.id: r for r in records.resources}
        world.plan_targets = dict(records.plan_targets)
        # Every family is watched: with no actors there is no per-family cost to
        # cap, and a family the hospital entered should hear from it.
        world.watched = tuple(p.id for p in records.patients)
        return world

    # ---------------- entering records (real world) ----------------

    def add_patient(self, patient: Patient, plan_target: StepKind | None = None) -> Patient:
        if self.patient(patient.id) is not None:
            raise ValueError(f"patient {patient.id} already exists")
        self.cohort = replace(self.cohort, patients=(*self.cohort.patients, patient))
        self.steps[patient.id] = []
        if plan_target is not None:
            self.plan_targets[patient.id] = plan_target
        if self.real:
            self.watched = (*self.watched, patient.id)
        if self.store is not None:
            self.store.save_patient(patient, plan_target)
        return patient

    def update_patient(self, patient_id: str, **changes) -> Patient:
        patient = self.patient(patient_id)
        if patient is None:
            raise LookupError(patient_id)
        updated = patient.model_copy(update=changes)
        self._replace_patient(updated)
        return updated

    def set_plan_target(self, patient_id: str, kind: StepKind) -> None:
        patient = self.patient(patient_id)
        if patient is None:
            raise LookupError(patient_id)
        self.plan_targets[patient_id] = kind
        if self.store is not None:
            self.store.save_patient(patient, kind)

    def add_family_member(self, patient_id: str, member) -> Patient:
        patient = self.patient(patient_id)
        if patient is None:
            raise LookupError(patient_id)
        if any(m.id == member.id for m in patient.family_members):
            raise ValueError(f"family member {member.id} already exists")
        return self.update_patient(
            patient_id, family_members=(*patient.family_members, member)
        )

    def add_step(self, step: CareStep) -> CareStep:
        if step.patient_id not in self.steps:
            raise LookupError(step.patient_id)
        if step.id in self.index:
            raise ValueError(f"step {step.id} already exists")
        self.steps[step.patient_id].append(step)
        self.index[step.id] = step.patient_id
        self._persist_step(step)
        return step

    def update_step(self, step_id: str, **changes) -> CareStep:
        patient_id = self.index.get(step_id)
        if patient_id is None:
            raise LookupError(step_id)
        rows = self.steps[patient_id]
        for position, row in enumerate(rows):
            if row.id == step_id:
                updated = row.model_copy(update=changes)
                rows[position] = updated
                self._persist_step(updated)
                return updated
        raise LookupError(step_id)

    def record_turnaround(self, queue: str, days: float, hospital_id: str = "") -> None:
        """A released report becomes one more observation for the forecast."""
        if self.store is not None:
            self.store.add_turnaround(
                TurnaroundObservation(
                    queue=queue, days=days, observed_on=self.today, hospital_id=hospital_id
                )
            )

    def _replace_patient(self, updated: Patient) -> None:
        patients = self.cohort.patients
        for position, patient in enumerate(patients):
            if patient.id == updated.id:
                self.cohort = replace(
                    self.cohort,
                    patients=patients[:position] + (updated,) + patients[position + 1 :],
                )
                if self.store is not None:
                    self.store.save_patient(updated, self.plan_targets.get(updated.id))
                return
        raise LookupError(updated.id)

    def _persist_step(self, step: CareStep) -> None:
        if self.store is not None:
            self.store.save_step(step)

    def _wire_scripted_demo(self, start: date) -> None:
        from ..synthetic.scripted import seed_anita_devi

        self.register_resource(
            Resource(id=MRI_2, kind=ResourceKind.MACHINE, display_name="MRI machine 2",
                     hospital_id="TMH-MUM", department="radiology")
        )
        self.register_resource(
            Resource(id=ECHO_CARDIOLOGIST, kind=ResourceKind.STAFF,
                     display_name="Echo cardiologist", hospital_id="HBCH-MZP",
                     department="cardiology")
        )
        self.register_resource(
            Resource(id=DAY_CARE_PHARMACY, kind=ResourceKind.SUPPLY,
                     display_name="Day-care pharmacy stock", hospital_id="HBCH-MZP",
                     department="day_care")
        )
        self.register_resource(
            Resource(id=PET_CT_SCANNER, kind=ResourceKind.MACHINE,
                     display_name="PET-CT scanner", hospital_id="TMH-MUM",
                     department="radiology")
        )
        # Shambhu's story is anchored on the consultants' meeting, not the
        # review consult: the joint clinic is the visit his whole stay is
        # booked around, so it is the visit the option table is measured against.
        self.plan_targets[SHAMBHU_ID] = StepKind.JOINT_CLINIC
        self.plan_targets[ANITA_ID] = StepKind.MAINTENANCE_DOSE
        _, _, _, cycle = seed_anita_devi(start)
        self.maintenance_cycles[ANITA_ID] = cycle
        # The two scripted families are the point of this world — put them
        # where a viewer looks first.
        rest = [p for p in self.watched if p not in (SHAMBHU_ID, ANITA_ID)]
        self.watched = (SHAMBHU_ID, ANITA_ID, *rest)[: self.n_watched]

    # ---------------- state ----------------

    def _load_cohort(self, cohort: SyntheticCohort) -> None:
        self.cohort = cohort
        self.steps = {pid: list(rows) for pid, rows in cohort.steps.items()}
        self.index = {row.id: pid for pid, rows in self.steps.items() for row in rows}
        self.desk.clear()
        # Watch the families with something still outstanding first — those are
        # the ones whose plan will visibly change while anyone is looking.
        pending_first = sorted(
            cohort.patients,
            key=lambda p: (
                not self._has_pending_report(p.id),
                -p.home_distance_km,
            ),
        )
        self.watched = tuple(p.id for p in pending_first[: self.n_watched])

    def _has_pending_report(self, patient_id: str) -> bool:
        return any(
            s.status is StepStatus.PENDING_RESULT for s in self.steps.get(patient_id, ())
        )

    def reset(self, start: date | None = None) -> None:
        """Rebuild from the same seed. The demo is reproducible on purpose."""
        if self.real:
            raise RuntimeError("real records cannot be reset")
        start = start or self.clock.start
        self.clock.reset(start)
        self.disruptions.clear()
        self.resources.clear()
        self.maintenance_cycles.clear()
        self.readiness_items.clear()
        self.plan_targets.clear()
        self.pending_approval.clear()
        if self.scripted:
            cohort, _ = build_scripted_cohort(
                n_patients=max(self.n_patients - 2, 0), seed=self.seed, today=start
            )
        else:
            cohort = generate_cohort(n_patients=self.n_patients, seed=self.seed, today=start)
        self._load_cohort(cohort)
        if self.scripted:
            self._wire_scripted_demo(start)

    @property
    def today(self) -> date:
        return self.clock.current

    def patients(self) -> tuple[Patient, ...]:
        return self.cohort.patients

    def patient(self, patient_id: str) -> Patient | None:
        for patient in self.cohort.patients:
            if patient.id == patient_id:
                return patient
        return None

    def set_language(self, patient_id: str, language: Language) -> Patient | None:
        """Change the language this family is written to, permanently.

        A family asking for Bengali is not asking the screen to be translated —
        they are telling the hospital which language to use, and every message
        after this one obeys. So it is a change to the record, not to a view.
        `Patient` is frozen and the cohort tuple is replaced wholesale, so no
        reader ever sees a patient half-switched.
        """
        patients = self.cohort.patients
        for patient in patients:
            if patient.id != patient_id:
                continue
            if patient.language is language:
                return patient
            updated = patient.model_copy(update={"language": language})
            self._replace_patient(updated)
            return updated
        return None

    def readiness_for(self, patient_id: str) -> tuple[ReadinessItem, ...]:
        """A snapshot: planning runs on a worker thread and must not see a tear."""
        return tuple(self.readiness_items.get(patient_id, {}).values())

    def set_readiness_item(self, item: ReadinessItem) -> ReadinessItem:
        if self.patient(item.patient_id) is None:
            raise LookupError(item.patient_id)
        self.readiness_items.setdefault(item.patient_id, {})[item.id] = item
        return item

    def remove_readiness_item(self, patient_id: str, item_id: str) -> bool:
        return self.readiness_items.get(patient_id, {}).pop(item_id, None) is not None

    def steps_for(self, patient_id: str) -> list[CareStep]:
        """A copy: planning runs on a worker thread and must not see a tear."""
        return list(self.steps.get(patient_id, ()))

    def step(self, step_id: str) -> CareStep | None:
        patient_id = self.index.get(step_id)
        if patient_id is None:
            return None
        for row in self.steps.get(patient_id, ()):
            if row.id == step_id:
                return row
        return None

    def ground_truth(self, patient_id: str) -> GroundTruth | None:
        return self.cohort.ground_truth.get(patient_id)

    # ---------------- the day's releases ----------------

    def due_releases(self) -> list[CareStep]:
        """Report steps whose planted ready date has arrived but which the
        hospital system has not been told about yet.

        This is the only place ground truth is read, and it stands in for the
        lab finishing the work — not for anyone knowing it in advance.
        """
        due: list[CareStep] = []
        pending_desk = {c.step_id for c in self.desk.values() if not c.confirmed}
        for patient_id, rows in self.steps.items():
            truth = self.cohort.ground_truth.get(patient_id)
            if truth is None:
                continue
            for row in rows:
                if row.kind not in REPORT_STEPS:
                    continue
                if row.status is not StepStatus.PENDING_RESULT:
                    continue
                if row.id in pending_desk:
                    continue
                ready_on = truth.true_ready_on.get(row.id)
                if ready_on is not None and ready_on <= self.today:
                    due.append(row)
        return due

    def open_candidate(
        self,
        step: CareStep,
        note: str,
        parsed: dict,
        drafted_by: str = "template",
    ) -> DeskCandidate:
        candidate = DeskCandidate(
            id=str(uuid.uuid4()),
            patient_id=step.patient_id,
            step_id=step.id,
            step_kind=step.kind.value,
            note=note,
            parsed=parsed,
            raised_on=self.today.isoformat(),
            raised_at=datetime.now(UTC),
            ticks_until_auto=self.auto_confirm_ticks,
            drafted_by=drafted_by,
        )
        self.desk[candidate.id] = candidate
        return candidate

    def pending_candidates(self) -> list[DeskCandidate]:
        return [c for c in self.desk.values() if not c.confirmed]

    def age_candidates(self) -> list[DeskCandidate]:
        """Count down the unconfirmed ones; return those that just ran out."""
        expired: list[DeskCandidate] = []
        for candidate in self.pending_candidates():
            candidate.ticks_until_auto -= 1
            if candidate.ticks_until_auto <= 0:
                expired.append(candidate)
        return expired

    def confirm(self, candidate_id: str, *, automatic: bool = False) -> CareStep | None:
        """Apply a desk candidate. Returns the updated step, or None if it was
        already confirmed or names something that is not there."""
        candidate = self.desk.get(candidate_id)
        if candidate is None or candidate.confirmed:
            return None
        candidate.confirmed = True
        candidate.confirmed_automatically = automatic
        return self.apply_release(candidate.step_id)

    def apply_release(self, step_id: str) -> CareStep | None:
        """Mark a report available. The only path that changes a step."""
        patient_id = self.index.get(step_id)
        rows = self.steps.get(patient_id) if patient_id else None
        if rows is None:
            return None
        for index, row in enumerate(rows):
            if row.id != step_id:
                continue
            if row.status is StepStatus.RESULT_AVAILABLE:
                return row
            updated = row.model_copy(
                update={
                    "status": StepStatus.RESULT_AVAILABLE,
                    "result_available_on": self.today,
                }
            )
            rows[index] = updated
            self._persist_step(updated)
            return updated
        return None

    # ---------------- disruptions ----------------

    def register_resource(self, resource: Resource) -> None:
        """Make a named machine/staff role/supply reportable.

        A no-op convenience for seeding; raising a disruption against an
        unregistered resource id still works, it just has no display metadata.
        """
        self.resources[resource.id] = resource
        if self.store is not None:
            self.store.save_resource(resource)

    def raise_disruption(
        self,
        *,
        resource_id: str,
        kind: DisruptionKind,
        unavailable_from: date,
        unavailable_to: date | None = None,
        note: str = "",
        raised_by: SourceSystem = SourceSystem.HOSPITAL_FEED,
    ) -> Disruption:
        """A desk's one-tap report. Does not touch any patient's steps —
        `affected_patients` reads this afterwards; nothing here decides
        anything, it only records that a desk said a resource is down."""
        disruption = Disruption(
            id=str(uuid.uuid4()),
            resource_id=resource_id,
            kind=kind,
            raised_by=raised_by,
            raised_at=datetime.now(UTC),
            unavailable_from=unavailable_from,
            unavailable_to=unavailable_to,
            note=note,
        )
        self.disruptions[disruption.id] = disruption
        return disruption

    def open_disruptions(self) -> list[Disruption]:
        return [
            d
            for d in self.disruptions.values()
            if d.unavailable_to is None or d.unavailable_to >= self.today
        ]

    def affected_patients(self, disruption: Disruption) -> list[str]:
        """Every patient with an unresolved step booked against the down
        resource, within the outage window.

        Matches by exact `resource_id` first (a specific machine), and falls
        back to resource-kind + department when the resource is a role or a
        supply that many steps share rather than booking individually.
        """
        resource = self.resources.get(disruption.resource_id)
        affected: list[str] = []
        for patient_id, rows in self.steps.items():
            for row in rows:
                if row.status not in _DISRUPTIBLE:
                    continue
                if not self._step_uses_resource(row, disruption, resource, patient_id):
                    continue
                if not self._step_in_window(row, disruption):
                    continue
                affected.append(patient_id)
                break
        return affected

    def _step_uses_resource(
        self,
        step: CareStep,
        disruption: Disruption,
        resource: Resource | None,
        patient_id: str,
    ) -> bool:
        if step.resource_id == disruption.resource_id:
            return True
        if resource is None:
            return False
        patient = self.patient(patient_id)
        pathway = get_pathway(patient.pathway_id if patient else None)
        required_kind = pathway.resource_requirements.get(step.kind)
        return (
            required_kind is not None
            and required_kind is resource.kind
            and step.queue == resource.department
        )

    def reschedule_steps(self, step_ids: set[str], new_date: date) -> list[CareStep]:
        """Move a set of steps to a new date. The only path that resolves a
        disruption's effect on a step, mirroring `apply_release` for reports."""
        updated: list[CareStep] = []
        for rows in self.steps.values():
            for index, row in enumerate(rows):
                if row.id not in step_ids:
                    continue
                new_row = row.model_copy(update={"scheduled_for": new_date})
                rows[index] = new_row
                self._persist_step(new_row)
                updated.append(new_row)
        return updated

    def _step_in_window(self, step: CareStep, disruption: Disruption) -> bool:
        when = step.scheduled_for
        if when is None:
            return False
        if when < disruption.unavailable_from:
            return False
        return disruption.unavailable_to is None or when <= disruption.unavailable_to

    # ---------------- reporting ----------------

    def pending_report_count(self) -> int:
        return sum(
            1
            for rows in self.steps.values()
            for row in rows
            if row.status is StepStatus.PENDING_RESULT
        )

    def snapshot(self) -> dict:
        return {
            **self.clock.snapshot(),
            "world": "real" if self.real else "demo",
            "patients": len(self.cohort.patients),
            "watched": list(self.watched),
            "pending_reports": self.pending_report_count(),
            "desk_queue": len(self.pending_candidates()),
        }


def default_start(offset_days: int = 3) -> date:
    """Start the world a few days back so reports land while anyone is watching.

    With no offset, the generator has already released most reports by t0 and
    the first minute of the demo is a still image.
    """
    return date.today() - timedelta(days=offset_days)
