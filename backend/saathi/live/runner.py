"""The runner: one simulated day at a time, with real work in between.

This is the loop the demo is built on. Every tick it advances the clock, lets
the day's finished reports become desk candidates, confirms the ones nobody
got to, re-plans **every** patient through the real LangGraph planner, renders
messages for the families whose answer actually changed, and re-scores the
cohort against planted ground truth.

Nothing here is scripted. There is no table of "things that happen at 0:30".
The only inputs are the clock and the planted ready-dates; everything a viewer
sees is the output of code that just ran, and every duration published to the
console was measured around the call that produced it.

Threading: the planner and the language layer are synchronous, so each batch of
work crosses into a worker thread via `asyncio.to_thread` and the event loop
stays free to serve the stream. The runner is the only writer to the world;
console-initiated changes (confirming a candidate, injecting a message) go
through it too, under one lock.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from time import perf_counter

from ..domain.enums import (
    AlertKind,
    Channel,
    Decision,
    DisruptionKind,
    FamilyMemberRole,
    Language,
    Role,
    SourceSystem,
    StepKind,
)
from ..domain.models import (
    Alert,
    ApprovalDecision,
    CaregiverMessage,
    Disruption,
    FamilyMember,
    Patient,
    PlanOption,
    VisitPlan,
)
from ..language import guard
from ..language.guard import InboundCategory
from ..language.holding import render_holding_message
from ..language.process_answers import render_process_answer
from ..ledger.evidence import InMemoryEvidenceLedger
from ..planner import options as options_module
from ..planner.graph import VisitPlanner
from ..planner.process_facts import resolve_process_fact
from ..synthetic.generate import evaluate
from .events import EventBus, EventKind
from .world import DeskCandidate, LiveWorld

logger = logging.getLogger(__name__)

STEP_LABELS = {
    "pathology_report": "Pathology report",
    "radiology_report": "Radiology report",
}

LANGUAGE_NAMES = {
    Language.HINDI: "Hindi",
    Language.BENGALI: "Bengali",
    Language.ODIA: "Odia",
    Language.ENGLISH: "English",
}


def _message_key(plan: VisitPlan | None) -> tuple:
    """Everything the family's wording depends on.

    When this changes the cached message is about a plan that no longer exists,
    so it is dropped and re-rendered rather than shown. The decision alone is
    too narrow a test: under GO the planner recomputes the travel date from the
    current day, so a message can go stale without the answer changing.
    """
    if plan is None:
        return ()
    return (
        plan.decision,
        plan.travel_on,
        tuple(sorted(b.kind.value for b in plan.blocked_by)),
        plan.where_to_go_first,
        plan.what_to_bring,
    )


@dataclass
class PlanRun:
    """The latest real planning run for one patient.

    The console reads these rather than triggering planning itself: in a live
    world the interface must reflect the world, not cause it.
    """

    patient_id: str
    plan: VisitPlan | None
    decision: Decision | None
    escalation: str | None
    computed_at: datetime
    sim_date: str
    plan_ms: float
    message: CaregiverMessage | None = None
    render_ms: float | None = None
    rendered_by: str | None = None
    #: Decision this run replaced, when it replaced one.
    previous_decision: Decision | None = None
    #: True when anything the family's wording depends on moved, which is a
    #: wider test than the decision changing — a GO whose travel date slid by a
    #: day needs new words just as much as a WAIT that became a GO.
    plan_changed: bool = False

    @property
    def changed(self) -> bool:
        return self.previous_decision is not None and self.previous_decision is not self.decision


@dataclass
class InboundRecord:
    """A message a family actually sent, and what the guard did with it."""

    id: str
    patient_id: str
    text: str
    gloss: str | None
    language: str
    answerable: bool
    reason: str | None
    triggers: tuple[str, ...]
    received_at: datetime
    sim_date: str
    origin: str = "actor"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "text": self.text,
            "gloss": self.gloss,
            "language": self.language,
            "answerable": self.answerable,
            "reason": self.reason,
            "triggers": list(self.triggers),
            "received_at": self.received_at.isoformat(),
            "sim_date": self.sim_date,
            "origin": self.origin,
        }


@dataclass
class OptionSet:
    """Ranked options waiting for a navigator or doctor to pick one."""

    patient_id: str
    disruption_id: str
    options: tuple[PlanOption, ...]
    created_at: datetime

    def to_json(self) -> dict:
        return {
            "patient_id": self.patient_id,
            "disruption_id": self.disruption_id,
            "created_at": self.created_at.isoformat(),
            "options": [o.model_dump(mode="json") for o in self.options],
        }


@dataclass
class IVRConfirmation:
    """A pending "press 1" — the family's own confirmation, logged like any
    other fact. In the credential-free live demo, resolved by a simulated
    digit press rather than a real Exotel callback."""

    id: str
    patient_id: str
    message_summary: str
    opened_at: datetime
    confirmed: bool = False
    digit: str | None = None


#: A target step this far along the pathway requires a doctor's approval,
#: not a navigator's — the same split the brief draws between "a navigator
#: or doctor picks one" and the dose-timing option specifically.
_DOCTOR_GATED_KINDS = frozenset({StepKind.TREATMENT, StepKind.MAINTENANCE_DOSE})


@dataclass
class LiveRunner:
    world: LiveWorld
    bus: EventBus
    planner: VisitPlanner
    ledger: InMemoryEvidenceLedger
    alerts: list[Alert]
    #: Set when Groq credentials are present. Every use is guarded; with it
    #: unset the world still ticks and every decision is still made.
    actors: object | None = None
    #: Seconds of real time between caregiver messages. Actors are the only
    #: unbounded cost in the loop, so their cadence is explicit.
    inbound_every_seconds: float = 15.0

    plans: dict[str, PlanRun] = field(default_factory=dict)
    inbound: list[InboundRecord] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    #: Ranked options awaiting a human, keyed by patient id — one pending
    #: disruption response per patient at a time.
    options: dict[str, OptionSet] = field(default_factory=dict)
    approvals: list[ApprovalDecision] = field(default_factory=list)
    ivr_confirmations: dict[str, IVRConfirmation] = field(default_factory=dict)
    #: "press advance" progress per scripted story — see `advance_story`.
    story_progress: dict[str, int] = field(default_factory=dict)

    _task: asyncio.Task | None = None
    _inbound_task: asyncio.Task | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _rng: random.Random = field(default_factory=lambda: random.Random(7))

    # ---------------- lifecycle ----------------

    async def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="saathi-live")
        if self._inbound_task is None or self._inbound_task.done():
            self._inbound_task = asyncio.create_task(
                self._inbound_loop(), name="saathi-inbound"
            )
        # Plan once up front so a console that connects before the first tick
        # still sees real decisions rather than an empty page.
        await self.plan_all()
        await self.update_metrics()

    async def stop(self) -> None:
        for task in (self._task, self._inbound_task):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = None
        self._inbound_task = None

    def _publish_state(self) -> None:
        self.bus.publish(
            EventKind.RUNNER_STATE,
            self.world.today.isoformat(),
            summary="running" if self.world.clock.running else "paused",
            **self.snapshot(),
        )

    async def play(self) -> None:
        self.world.clock.running = True
        self._publish_state()

    async def pause(self) -> None:
        self.world.clock.running = False
        self._publish_state()

    async def set_speed(self, seconds_per_day: float) -> None:
        self.world.clock.seconds_per_day = max(0.5, min(60.0, seconds_per_day))
        self._publish_state()

    async def reset(self, start: date | None = None) -> None:
        async with self._lock:
            self.world.reset(start)
            self.plans.clear()
            self.inbound.clear()
            self.alerts.clear()
            self.counters.clear()
            self.options.clear()
            self.approvals.clear()
            self.ivr_confirmations.clear()
            self.story_progress.clear()
        self.bus.publish(
            EventKind.WORLD_RESET,
            self.world.today.isoformat(),
            summary=f"World reset to {self.world.today}",
        )
        await self.plan_all()
        await self.update_metrics()

    # ---------------- the loop ----------------

    async def _loop(self) -> None:
        while True:
            try:
                if self.world.clock.running:
                    await self.tick()
                await asyncio.sleep(max(0.25, self.world.clock.seconds_per_day))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the world must not stop on one bad day
                logger.exception("tick failed; continuing")
                await asyncio.sleep(1.0)

    async def tick(self) -> None:
        async with self._lock:
            day = self.world.clock.advance()
        self.bus.publish(
            EventKind.CLOCK_TICK,
            day.isoformat(),
            summary=f"Day {self.world.clock.day} — {day:%a %d %b}",
            pending_reports=self.world.pending_report_count(),
        )

        await self._raise_desk_candidates()
        await self._auto_confirm()
        await self.plan_all()
        await self.update_metrics()

    # ---------------- the desk ----------------

    async def _raise_desk_candidates(self) -> None:
        for step in self.world.due_releases():
            label = STEP_LABELS.get(step.kind.value, step.kind.value.replace("_", " "))
            note = f"{label} for {step.patient_id} released today, {self.world.today:%d %b}."
            drafted_by = "template"
            duration: float | None = None

            if self.actors is not None:
                started = perf_counter()
                drafted = await self.actors.draft_ward_note(step, self.world.today)
                duration = (perf_counter() - started) * 1000
                if drafted is not None:
                    note, drafted_by = drafted, "groq"
                    self._bump("actor_calls")

            parsed = await self._parse_note(note, step.id)
            async with self._lock:
                candidate = self.world.open_candidate(step, note, parsed, drafted_by)

            self.bus.publish(
                EventKind.DESK_CANDIDATE,
                self.world.today.isoformat(),
                patient_id=step.patient_id,
                summary=f"Desk: {label} for {step.patient_id} awaiting confirmation",
                duration_ms=duration,
                candidate=candidate.to_json(),
            )

    async def _parse_note(self, note: str, step_id: str) -> dict:
        """Turn the ward's free text back into a structured update.

        With an actor present this is a second model call, so the loop is the
        real one: a human writes prose, a machine proposes a record, a human
        confirms it. Without one it falls back to the fact we already hold —
        which is the same shape, just not derived from the prose.
        """
        if self.actors is not None:
            parsed = await self.actors.parse_ward_note(note, step_id)
            if parsed is not None:
                self._bump("actor_calls")
                return parsed
        return {
            "step_id": step_id,
            "new_status": "result_available",
            "released_on": self.world.today.isoformat(),
            "source": "fallback",
        }

    async def _auto_confirm(self) -> None:
        async with self._lock:
            expired = self.world.age_candidates()
        for candidate in expired:
            await self.confirm(candidate.id, automatic=True)

    async def confirm(self, candidate_id: str, *, automatic: bool = False) -> bool:
        async with self._lock:
            candidate: DeskCandidate | None = self.world.desk.get(candidate_id)
            step = self.world.confirm(candidate_id, automatic=automatic)
        if step is None or candidate is None:
            return False

        before = self.ledger_size()
        entry = self.ledger.record_once(
            patient_id=step.patient_id,
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=step.id,
            claim=f"{step.kind.value} is {step.status.value}",
            metadata={
                "released_on": self.world.today.isoformat(),
                "confirmed_by": "auto" if automatic else "desk staff",
                "note": candidate.note,
            },
        )
        appended = self.ledger_size() - before
        if appended:
            started = perf_counter()
            intact = self.ledger.verify()
            verify_ms = (perf_counter() - started) * 1000
            self.bus.publish(
                EventKind.LEDGER_APPENDED,
                self.world.today.isoformat(),
                patient_id=step.patient_id,
                summary=(
                    f"Ledger +{appended} · chain {'intact' if intact else 'BROKEN'}"
                ),
                duration_ms=verify_ms,
                entries=appended,
                intact=intact,
                claim=entry.claim,
                ledger_id=entry.id,
            )

        label = STEP_LABELS.get(step.kind.value, step.kind.value.replace("_", " "))
        self.bus.publish(
            EventKind.DESK_CONFIRMED,
            self.world.today.isoformat(),
            patient_id=step.patient_id,
            summary=(
                f"{label} confirmed for {step.patient_id}"
                + (" (auto)" if automatic else " by desk staff")
            ),
            candidate_id=candidate_id,
            automatic=automatic,
            ledger_id=entry.id,
        )
        self.bus.publish(
            EventKind.STEP_RELEASED,
            self.world.today.isoformat(),
            patient_id=step.patient_id,
            summary=f"{label} now result ready",
            step_id=step.id,
        )
        # Re-plan immediately rather than waiting for the next tick: the whole
        # point is that the family's answer changes the moment the fact does.
        await self.plan_patient(step.patient_id, allow_render=True)
        await self.update_metrics()
        return True

    # ---------------- disruptions ----------------

    async def raise_disruption(
        self,
        *,
        resource_id: str,
        kind: DisruptionKind,
        unavailable_from: date,
        unavailable_to: date | None,
        note: str = "",
        raised_by: SourceSystem = SourceSystem.HOSPITAL_FEED,
    ) -> tuple[Disruption, list[str]]:
        """A desk's one-tap report. Returns the disruption and who it hit."""
        async with self._lock:
            disruption = self.world.raise_disruption(
                resource_id=resource_id,
                kind=kind,
                unavailable_from=unavailable_from,
                unavailable_to=unavailable_to,
                note=note,
                raised_by=raised_by,
            )
            affected = self.world.affected_patients(disruption)
        resource = self.world.resources.get(resource_id)
        self.bus.publish(
            EventKind.DISRUPTION_RAISED,
            self.world.today.isoformat(),
            summary=(
                f"{(resource.display_name if resource else resource_id)} "
                f"reported {kind.value.replace('_', ' ')} — {len(affected)} families affected"
            ),
            disruption_id=disruption.id,
            resource_id=resource_id,
            affected=affected,
        )
        await self.handle_disruption(disruption, affected)
        return disruption, affected

    async def handle_disruption(self, disruption: Disruption, affected: list[str]) -> None:
        """The 5-step loop's steps 2-3: hold every family first, then re-solve.

        The ordering here is literal and load-bearing: nothing computes a new
        date before every affected family has already been told not to travel.
        """
        for patient_id in affected:
            evidence = self._record_disruption_fact(patient_id, disruption)
            await self._send_holding_message(patient_id, disruption, evidence)

        for patient_id in affected:
            # Re-plan before re-solving. The booking on the broken resource has
            # stopped counting as a date, so this drops the family to UNCERTAIN
            # — which is the state the brief requires between the holding
            # message and the approval: told first, no new date promised yet.
            # Without it the console keeps showing a date the hospital can no
            # longer honour, which is the one thing a holding message exists to
            # prevent.
            await self.plan_patient(patient_id)
            await self._resolve_disruption_for_patient(patient_id, disruption)

        await self.update_metrics()

    def _record_disruption_fact(self, patient_id: str, disruption: Disruption) -> tuple:
        entry = self.ledger.record_once(
            patient_id=patient_id,
            source=disruption.raised_by,
            source_record_id=disruption.id,
            claim=(
                f"{disruption.kind.value} on {disruption.resource_id} "
                f"from {disruption.unavailable_from.isoformat()}"
            ),
            metadata={
                "unavailable_to": disruption.unavailable_to.isoformat()
                if disruption.unavailable_to
                else None,
                "note": disruption.note,
            },
        )
        return (entry.ref(),)

    async def _send_holding_message(
        self, patient_id: str, disruption: Disruption, evidence: tuple
    ) -> None:
        patient = self.world.patient(patient_id)
        if patient is None:
            return
        recipients = patient.family_members or ()
        targets = (
            [(fm.language, fm.channel) for fm in recipients]
            if recipients
            else [(patient.language, Channel.WHATSAPP)]
        )
        for language, channel in targets:
            message = render_holding_message(
                disruption, patient_id, language, channel, evidence
            )
            self.bus.publish(
                EventKind.HOLDING_MESSAGE_SENT,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Holding message sent to {patient_id} on {channel.value}",
                disruption_id=disruption.id,
                channel=channel.value,
            )
            if channel is Channel.IVR:
                self._open_ivr_confirmation(patient_id, message.body)

    def _enumerate_options_sync(
        self, patient: Patient, steps: list, disruption: Disruption, target_kind: StepKind, cycle
    ) -> tuple[PlanOption, ...]:
        direct = options_module.enumerate_candidates(
            patient, steps, disruption, target_kind, self.planner.graph,
            self.planner.predictor, self.world.today, cycle=cycle,
        )
        if direct:
            return direct
        return options_module.opportunistic_bundle_candidates(
            patient, steps, disruption, target_kind, self.planner.graph,
            self.planner.predictor, self.world.today, cycle=cycle,
        )

    async def _resolve_disruption_for_patient(
        self, patient_id: str, disruption: Disruption
    ) -> None:
        patient = self.world.patient(patient_id)
        if patient is None:
            return
        steps = self.world.steps_for(patient_id)
        target_kind = self.world.target_kind_for(patient_id)
        cycle = self.world.maintenance_cycles.get(patient_id)

        started = perf_counter()
        candidates = await asyncio.to_thread(
            self._enumerate_options_sync, patient, steps, disruption, target_kind, cycle
        )
        elapsed = (perf_counter() - started) * 1000

        if len(candidates) <= 1:
            # Simple case: nothing to choose between, so there is nothing for
            # a human to decide. Apply the only candidate's shift and re-plan
            # through the real pipeline, same as any other fact changing.
            if candidates:
                await self._apply_resolution(patient_id, disruption, candidates[0])
            await self.plan_patient(patient_id, allow_render=patient_id in self.world.watched)
            return

        async with self._lock:
            self.options[patient_id] = OptionSet(
                patient_id=patient_id,
                disruption_id=disruption.id,
                options=candidates,
                created_at=datetime.now(UTC),
            )
            self.world.pending_approval[patient_id] = disruption.id
        self.bus.publish(
            EventKind.OPTIONS_READY,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{len(candidates)} ranked options ready for {patient_id}",
            duration_ms=elapsed,
            disruption_id=disruption.id,
            options=[o.model_dump(mode="json") for o in candidates],
        )

    async def _apply_resolution(
        self, patient_id: str, disruption: Disruption, option: PlanOption
    ) -> None:
        resume_on = (disruption.unavailable_to or disruption.unavailable_from) + timedelta(days=1)
        steps = self.world.steps_for(patient_id)
        affected_ids = {
            s.id
            for s in steps
            if s.resource_id == disruption.resource_id
            and s.scheduled_for is not None
            and s.scheduled_for >= disruption.unavailable_from
            and (disruption.unavailable_to is None or s.scheduled_for <= disruption.unavailable_to)
        }
        if affected_ids:
            async with self._lock:
                self.world.reschedule_steps(affected_ids, resume_on)

    def touches_treatment(self, option: PlanOption) -> bool:
        step = self.world.step(option.target_step_id)
        return step is not None and step.kind in _DOCTOR_GATED_KINDS

    async def approve_option(
        self,
        *,
        patient_id: str,
        option_index: int,
        approved_by_role: Role,
        approved_by: str,
    ) -> ApprovalDecision:
        """The brief's single approval action: fans out to desks and family.

        Raises `PermissionError` when a navigator tries to approve a plan
        that touches treatment or dose timing — a structural check, not a UI
        nicety, the same way the model's travel decision is bound structurally
        rather than by instruction.
        """
        option_set = self.options.get(patient_id)
        if option_set is None or not (0 <= option_index < len(option_set.options)):
            raise LookupError("no such option")
        option = option_set.options[option_index]
        if self.touches_treatment(option) and approved_by_role is not Role.DOCTOR:
            raise PermissionError(
                "only a doctor may approve an option that touches treatment or dose timing"
            )
        disruption = self.world.disruptions.get(option_set.disruption_id)

        async with self._lock:
            del self.options[patient_id]
            self.world.pending_approval.pop(patient_id, None)
        if disruption is not None:
            await self._apply_resolution(patient_id, disruption, option)

        approval = ApprovalDecision(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            disruption_id=option_set.disruption_id,
            option_summary=option,
            approved_by_role=approved_by_role,
            approved_by=approved_by,
            approved_at=datetime.now(UTC),
            evidence=option.evidence,
        )
        self.approvals.append(approval)
        self.ledger.record_once(
            patient_id=patient_id,
            source=SourceSystem.NAVIGATOR,
            source_record_id=approval.id,
            claim=(
                f"{approved_by_role.value} approved option for "
                f"disruption {option_set.disruption_id}"
            ),
            metadata={"approved_by": approved_by, "decision": option.decision.value},
        )

        resource = self.world.resources.get(disruption.resource_id) if disruption else None
        self.bus.publish(
            EventKind.APPROVAL_RECORDED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=(
                f"{approved_by} ({approved_by_role.value}) approved a plan for {patient_id}"
                + (f" — {resource.department} desk updated" if resource else "")
            ),
            approval_id=approval.id,
            desk=resource.department if resource else None,
        )

        await self.plan_patient(patient_id, allow_render=True)
        await self._fan_out_approval_messages(patient_id, option)
        return approval

    async def _fan_out_approval_messages(self, patient_id: str, option: PlanOption) -> None:
        """Every family member hears the change, each on their own channel."""
        layer = self.planner.language_layer
        patient = self.world.patient(patient_id)
        if layer is None or patient is None:
            return
        option_fields = {"nights_added", "extra_trips", "dose_delay_days"}
        plan = VisitPlan(**option.model_dump(exclude=option_fields))
        recipients = patient.family_members or ()
        targets = recipients if recipients else [
            FamilyMember(
                id=f"{patient_id}-default",
                patient_id=patient_id,
                role=FamilyMemberRole.CAREGIVER_PRIMARY,
                name=patient_id,
                phone=patient.caregiver_phone,
                preferred_channel=Channel.WHATSAPP,
                language=patient.language,
            )
        ]
        for member in targets:
            started = perf_counter()
            message = await asyncio.to_thread(
                layer.render, plan, member.language, member.preferred_channel, self.ledger
            )
            elapsed = (perf_counter() - started) * 1000
            self._bump("renders")
            kind = (
                EventKind.MESSAGE_HELD
                if message.routed_to_care_team
                else EventKind.MESSAGE_RENDERED
            )
            self.bus.publish(
                kind,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=(
                    f"Approval message sent to {member.name} "
                    f"on {member.preferred_channel.value}"
                ),
                duration_ms=elapsed,
            )
            if member.preferred_channel is Channel.IVR:
                self._open_ivr_confirmation(patient_id, message.body)

    def _open_ivr_confirmation(self, patient_id: str, message_summary: str) -> IVRConfirmation:
        confirmation = IVRConfirmation(
            id=str(uuid.uuid4()),
            patient_id=patient_id,
            message_summary=message_summary[:200],
            opened_at=datetime.now(UTC),
        )
        self.ivr_confirmations[confirmation.id] = confirmation
        return confirmation

    async def confirm_ivr(self, confirmation_id: str, digit: str) -> bool:
        """The family's own confirmation — press 1 — logged like any other
        fact. In the credential-free live demo this is a simulated digit
        press rather than a real Exotel callback (invariant 9)."""
        confirmation = self.ivr_confirmations.get(confirmation_id)
        if confirmation is None or confirmation.confirmed:
            return False
        confirmation.confirmed = True
        confirmation.digit = digit
        self.ledger.record_once(
            patient_id=confirmation.patient_id,
            source=SourceSystem.CAREGIVER_REPLY,
            source_record_id=confirmation.id,
            claim=f"family confirmed by pressing {digit}",
            metadata={"message": confirmation.message_summary},
        )
        self.bus.publish(
            EventKind.CONFIRMATION_RECEIVED,
            self.world.today.isoformat(),
            patient_id=confirmation.patient_id,
            summary=f"{confirmation.patient_id} confirmed (pressed {digit})",
            confirmation_id=confirmation_id,
        )
        return True

    # ---------------- scripted demo ----------------

    async def advance_story(self, story: str) -> dict:
        """The demo's "press advance": the next beat of a scripted story,
        executed through the real runner methods a person would otherwise
        click through — `raise_disruption`, `approve_option`. Nothing here
        is a parallel, faked code path."""
        from ..synthetic.scripted import STORY_BEATS

        beats = STORY_BEATS.get(story)
        if beats is None:
            raise LookupError(f"unknown story {story!r}")
        index = self.story_progress.get(story, 0)
        if index >= len(beats):
            return {"story": story, "done": True, "beat": None}

        action, params = beats[index]
        if action == "disrupt":
            await self.raise_disruption(
                resource_id=params["resource_id"],
                kind=params["kind"],
                unavailable_from=self.world.today,
                unavailable_to=self.world.today + timedelta(days=params["days"]),
                note=params["note"],
            )
        elif action == "approve_first_option":
            option_set = self.options.get(params["patient_id"])
            if option_set is not None:
                await self.approve_option(
                    patient_id=params["patient_id"],
                    option_index=0,
                    approved_by_role=params["role"],
                    approved_by=params["approved_by"],
                )

        self.story_progress[story] = index + 1
        return {"story": story, "done": index + 1 >= len(beats), "beat": action}

    # ---------------- planning ----------------

    def _plan_sync(
        self,
        patient: Patient,
        steps: list,
        compose: bool,
        disruptions: tuple = (),
    ) -> dict:
        # `disruptions` is passed in rather than read off the world: this runs
        # on a worker thread and must not race the lock that owns it.
        return self.planner.plan_visit(
            patient=patient,
            steps=steps,
            target_kind=self.world.target_kind_for(patient.id),
            today=self.world.today,
            compose=compose,
            disruptions=disruptions,
        )

    def _plan_batch_sync(self, work: list[tuple[Patient, list]], disruptions: tuple) -> list[dict]:
        return [self._plan_sync(patient, steps, False, disruptions) for patient, steps in work]

    async def plan_all(self) -> None:
        disruptions = tuple(self.world.open_disruptions())
        work = [
            (patient, self.world.steps_for(patient.id)) for patient in self.world.patients()
        ]
        started = perf_counter()
        results = await asyncio.to_thread(self._plan_batch_sync, work, disruptions)
        batch_ms = (perf_counter() - started) * 1000

        changed: list[PlanRun] = []
        moved: list[PlanRun] = []
        for (patient, _), result in zip(work, results, strict=True):
            run = self._store(patient.id, result)
            if run.changed:
                changed.append(run)
            if run.plan_changed:
                moved.append(run)

        self.bus.publish(
            EventKind.PLAN_RECOMPUTED,
            self.world.today.isoformat(),
            summary=(
                f"Planner re-ran {len(work)} families"
                + (
                    f" · {len(changed)} answers changed"
                    if changed
                    else " · every answer unchanged"
                )
            ),
            duration_ms=batch_ms,
            changed=[r.patient_id for r in changed],
        )
        self._bump("plan_runs", len(work))

        for run in moved:
            if run.changed:
                summary = (
                    f"{run.patient_id}: "
                    f"{(run.previous_decision.value if run.previous_decision else '—').upper()}"
                    f" → {(run.decision.value if run.decision else '—').upper()}"
                )
            else:
                summary = (
                    f"{run.patient_id}: {(run.decision.value if run.decision else '—').upper()}"
                    f" restated — the plan moved, so the old wording no longer holds"
                )
            self.bus.publish(
                EventKind.PLAN_RECOMPUTED,
                self.world.today.isoformat(),
                patient_id=run.patient_id,
                summary=summary,
                duration_ms=run.plan_ms,
                decision=run.decision.value if run.decision else None,
            )
            if run.patient_id in self.world.watched:
                await self._render_for(run.patient_id)

    async def plan_patient(self, patient_id: str, *, allow_render: bool = False) -> PlanRun | None:
        patient = self.world.patient(patient_id)
        if patient is None:
            return None
        steps = self.world.steps_for(patient_id)
        disruptions = tuple(self.world.open_disruptions())
        before = self.ledger_size()
        result = await asyncio.to_thread(self._plan_sync, patient, steps, False, disruptions)
        run = self._store(patient_id, result)
        self._bump("plan_runs")

        appended = self.ledger_size() - before
        if appended:
            self.bus.publish(
                EventKind.LEDGER_APPENDED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Ledger +{appended} · chain {self._verify_label()}",
                entries=appended,
            )
        self.bus.publish(
            EventKind.PLAN_RECOMPUTED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{patient_id}: {(run.decision.value if run.decision else '—').upper()}",
            duration_ms=run.plan_ms,
            decision=run.decision.value if run.decision else None,
        )
        if allow_render and patient_id in self.world.watched:
            await self._render_for(patient_id)
        return run

    def _store(self, patient_id: str, result: dict) -> PlanRun:
        previous = self.plans.get(patient_id)
        plan = result.get("plan")
        moved = _message_key(plan) != _message_key(previous.plan if previous else None)
        run = PlanRun(
            patient_id=patient_id,
            plan=plan,
            decision=plan.decision if plan else None,
            escalation=result.get("escalation"),
            computed_at=datetime.now(UTC),
            sim_date=self.world.today.isoformat(),
            plan_ms=float(result.get("plan_ms") or 0.0),
            message=previous.message if previous else None,
            render_ms=previous.render_ms if previous else None,
            rendered_by=previous.rendered_by if previous else None,
            previous_decision=previous.decision if previous else None,
            plan_changed=bool(previous) and moved,
        )
        if previous is None or moved:
            # Any move invalidates the old wording, not just a change of answer.
            # A GO plan's travel date slides as the clock advances, and a message
            # still naming last week's date is worse than no message at all —
            # it is the one error that actually puts a family on a bus.
            run.message = None
            run.render_ms = None
            run.rendered_by = None
        self.plans[patient_id] = run
        return run

    # ---------------- speaking ----------------

    async def _render_for(self, patient_id: str) -> None:
        layer = self.planner.language_layer
        run = self.plans.get(patient_id)
        patient = self.world.patient(patient_id)
        if layer is None or run is None or run.plan is None or patient is None:
            return

        started = perf_counter()
        message = await asyncio.to_thread(
            layer.render, run.plan, patient.language, Channel.WHATSAPP, self.ledger
        )
        elapsed = (perf_counter() - started) * 1000
        run.message = message
        run.render_ms = elapsed
        run.rendered_by = getattr(layer, "describe", lambda: "language layer")()
        self._bump("renders")

        language = LANGUAGE_NAMES.get(patient.language, patient.language.value)
        if message.routed_to_care_team:
            self.bus.publish(
                EventKind.MESSAGE_HELD,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Guard held the {language} message for {patient_id}",
                duration_ms=elapsed,
                reason=message.routing_reason,
                rendered_by=run.rendered_by,
            )
        else:
            self.bus.publish(
                EventKind.MESSAGE_RENDERED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"{run.rendered_by} wrote {language} for {patient_id}",
                duration_ms=elapsed,
                rendered_by=run.rendered_by,
            )

    # ---------------- what the family says back ----------------

    async def _inbound_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.inbound_every_seconds)
                if not self.world.clock.running or self.actors is None:
                    continue
                if not self.world.watched:
                    continue
                patient_id = self._rng.choice(self.world.watched)
                await self.receive_inbound(patient_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("inbound actor failed; continuing")

    async def receive_inbound(
        self, patient_id: str, kind: str | None = None, text: str | None = None
    ) -> InboundRecord | None:
        """Take a caregiver message through the real guard.

        `text` is supplied when a human typed it; otherwise the caregiver actor
        writes one. Either way it hits `guard.screen_inbound`, and a clinical
        question raises a real alert rather than getting an answer.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None

        gloss: str | None = None
        origin = "typed" if text else "actor"
        duration: float | None = None

        if text is None:
            if self.actors is None:
                return None
            started = perf_counter()
            written = await self.actors.write_caregiver_message(
                patient, self.plans.get(patient_id), kind
            )
            duration = (perf_counter() - started) * 1000
            if written is None:
                return None
            text, gloss = written
            self._bump("actor_calls")

        verdict = guard.screen_inbound(text)
        record = InboundRecord(
            id=f"in-{patient_id}-{len(self.inbound)}",
            patient_id=patient_id,
            text=text,
            gloss=gloss,
            language=patient.language.value,
            answerable=verdict.allowed,
            reason=verdict.reason,
            triggers=verdict.triggers,
            received_at=datetime.now(UTC),
            sim_date=self.world.today.isoformat(),
            origin=origin,
        )
        self.inbound.append(record)
        self._bump("inbound")

        self.bus.publish(
            EventKind.INBOUND_RECEIVED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{patient_id} wrote in ({LANGUAGE_NAMES.get(patient.language, '')})",
            duration_ms=duration,
            record=record.to_json(),
        )

        if not verdict.allowed:
            alert = Alert(
                id=f"alert-{patient_id}-{len(self.alerts)}",
                patient_id=patient_id,
                kind=AlertKind.CLINICAL_QUESTION,
                raised_at=datetime.now(UTC),
                detail=text[:280],
            )
            self.alerts.append(alert)
            self.bus.publish(
                EventKind.GUARD_BLOCKED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Guard routed a clinical question from {patient_id} to a person",
                triggers=list(verdict.triggers),
            )
            self.bus.publish(
                EventKind.ALERT_RAISED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Alert: clinical question from {patient_id}",
                alert_kind=AlertKind.CLINICAL_QUESTION.value,
            )
        elif guard.classify_inbound(text) == InboundCategory.PROCESS:
            await self._answer_process_question(patient, record)
        return record

    async def _answer_process_question(self, patient: Patient, record: InboundRecord) -> None:
        """A process-only question gets a process-only answer — the family
        is told who decides and by when, never anything clinical. The
        existing clinical branch above is untouched; this is additive."""
        fact = resolve_process_fact(patient.id, self.world)
        if fact is None:
            return
        disruption = self.world.disruptions.get(fact.disruption_id)
        if disruption is None:
            return
        evidence = self._record_disruption_fact(patient.id, disruption)
        message = render_process_answer(
            fact, patient.id, patient.language, Channel.WHATSAPP, evidence
        )
        self.bus.publish(
            EventKind.PROCESS_ANSWERED,
            self.world.today.isoformat(),
            patient_id=patient.id,
            summary=f"Process-only answer sent to {patient.id}",
            held=message.routed_to_care_team,
        )

    # ---------------- scoring ----------------

    async def update_metrics(self) -> None:
        decisions: dict[str, date | None] = {}
        for patient_id, run in self.plans.items():
            plan = run.plan
            decisions[patient_id] = (
                plan.travel_on if plan and plan.decision is Decision.GO else None
            )
        started = perf_counter()
        scores = evaluate(self.world.cohort, decisions)
        elapsed = (perf_counter() - started) * 1000
        if scores == self.metrics:
            return
        self.metrics = scores
        self.bus.publish(
            EventKind.METRICS_UPDATED,
            self.world.today.isoformat(),
            summary=(
                f"Cohort rescored · {int(scores['wasted_trips_avoided'])} journeys not taken"
            ),
            duration_ms=elapsed,
            metrics=scores,
        )

    # ---------------- helpers ----------------

    def ledger_size(self) -> int:
        return self.ledger.size()

    def _verify_label(self) -> str:
        return "intact" if self.ledger.verify() else "BROKEN"

    def _bump(self, key: str, by: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + by

    def snapshot(self) -> dict:
        layer = self.planner.language_layer
        return {
            **self.world.snapshot(),
            "counters": dict(self.counters),
            "metrics": self.metrics,
            "language_layer": (
                getattr(layer, "describe", lambda: "language layer")() if layer else None
            ),
            "actors_enabled": self.actors is not None,
            "inbound_every_seconds": self.inbound_every_seconds,
            "alerts": len(self.alerts),
            "open_disruptions": len(self.world.open_disruptions()),
            "options_pending": len(self.options),
        }
