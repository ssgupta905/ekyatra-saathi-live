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
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from time import perf_counter

from ..domain.enums import AlertKind, Channel, Decision, Language, SourceSystem, StepKind
from ..domain.models import Alert, CaregiverMessage, Patient, VisitPlan
from ..language import guard
from ..ledger.evidence import InMemoryEvidenceLedger
from ..planner.graph import VisitPlanner
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

    # ---------------- planning ----------------

    def _plan_sync(self, patient: Patient, steps: list, compose: bool) -> dict:
        return self.planner.plan_visit(
            patient=patient,
            steps=steps,
            target_kind=StepKind.REVIEW_CONSULT,
            today=self.world.today,
            compose=compose,
        )

    def _plan_batch_sync(self, work: list[tuple[Patient, list]]) -> list[dict]:
        return [self._plan_sync(patient, steps, False) for patient, steps in work]

    async def plan_all(self) -> None:
        work = [
            (patient, self.world.steps_for(patient.id)) for patient in self.world.patients()
        ]
        started = perf_counter()
        results = await asyncio.to_thread(self._plan_batch_sync, work)
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
        before = self.ledger_size()
        result = await asyncio.to_thread(self._plan_sync, patient, steps, False)
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
        return record

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
        }
