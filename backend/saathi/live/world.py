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
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from ..domain.enums import REPORT_STEPS, StepStatus
from ..domain.models import CareStep, Patient
from ..synthetic.generate import GroundTruth, SyntheticCohort, generate_cohort
from .clock import SimulationClock

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

    clock: SimulationClock
    cohort: SyntheticCohort
    #: Mutable per patient. The `CareStep`s themselves stay frozen and are
    #: replaced wholesale, so nothing ever holds a half-updated record.
    steps: dict[str, list[CareStep]] = field(default_factory=dict)
    desk: dict[str, DeskCandidate] = field(default_factory=dict)
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
    ) -> LiveWorld:
        start = start or date.today()
        cohort = generate_cohort(n_patients=n_patients, seed=seed, today=start)
        world = cls(
            clock=SimulationClock(start=start, seconds_per_day=seconds_per_day),
            cohort=cohort,
            seed=seed,
            n_patients=n_patients,
            n_watched=n_watched,
            auto_confirm_ticks=auto_confirm_ticks,
        )
        world._load_cohort(cohort)
        return world

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
        start = start or self.clock.start
        self.clock.reset(start)
        self._load_cohort(
            generate_cohort(n_patients=self.n_patients, seed=self.seed, today=start)
        )

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
            return updated
        return None

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
