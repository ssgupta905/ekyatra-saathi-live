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

from ..domain.affordability import Means
from ..domain.budget import TOPIC_NEED, BudgetAnswer, BudgetTopic
from ..domain.enums import (
    REPORT_STEPS,
    AlertKind,
    Channel,
    Decision,
    DisruptionKind,
    FamilyMemberRole,
    Language,
    Role,
    SourceSystem,
    StepKind,
    StepStatus,
)
from ..domain.models import (
    Alert,
    ApprovalDecision,
    CaregiverMessage,
    CareStep,
    Disruption,
    FamilyMember,
    Patient,
    PlanOption,
    VisitPlan,
)
from ..domain.places import PlaceKind
from ..domain.requests import PatientRequest, RequestIntent
from ..language import guard
from ..language.advice import already_travelling, leave_later
from ..language.guard import InboundCategory
from ..language.holding import render_holding_message
from ..language.process_answers import render_process_answer
from ..language.questions import (
    AskReason,
    AskTopic,
    compose_proposal,
    compose_question,
)
from ..money import JourneyCost, cost_of_journey, load_rates
from ..planner import options as options_module
from ..planner.graph import VisitPlanner
from ..planner.process_facts import resolve_process_fact
from ..planner.search import Search
from ..ports.fhir import prioritise_task
from ..ports.ledger import EvidenceLedger
from ..ports.records import StoredOptionSet
from ..readiness.conformal import TurnaroundSample
from ..synthetic.generate import evaluate
from .dialogue import Conversation, OpenQuestion
from .events import EventBus, EventKind
from .world import DeskCandidate, LiveWorld

logger = logging.getLogger(__name__)


def _as_intent(raw: object) -> RequestIntent:
    """An intent the system knows, or `unclear`.

    An unrecognised label becomes `unclear` rather than an error: `unclear`
    already means "a person reads this themselves", which is exactly the right
    handling for a reading nobody can interpret.
    """
    try:
        return RequestIntent(str(raw))
    except ValueError:
        return RequestIntent.UNCLEAR


def _as_step_kind(raw: object) -> StepKind | None:
    """A step this hospital has, or None.

    `extract_request` already drops a step the patient has not booked. This is
    the second half of that: a name that is not in our own vocabulary at all.
    """
    if not raw:
        return None
    try:
        return StepKind(str(raw))
    except ValueError:
        return None

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


def _describe_options(options) -> str:
    """What each option costs the family, in one line per option.

    Nights, trips and dose delay — the same vocabulary the panel uses, and
    deliberately not a rupee figure: the backend will not report a fare it was
    not given, and this text goes into another organisation's record where a
    number nobody can source is worse than no number.
    """
    lines = []
    for index, option in enumerate(options, start=1):
        parts = [f"{option.nights_added:+d} nights", f"{option.extra_trips:+d} trips"]
        if option.dose_delay_days:
            parts.append(f"{option.dose_delay_days}d dose delay")
        on = f" on {option.target_on:%a %d %b}" if option.target_on else ""
        lines.append(f"{index}.{on} — " + ", ".join(parts))
    return "Options offered:\n" + "\n".join(lines)


@dataclass
class LiveRunner:
    world: LiveWorld
    bus: EventBus
    planner: VisitPlanner
    ledger: EvidenceLedger
    alerts: list[Alert]
    #: Set when Groq credentials are present. Every use is guarded; with it
    #: unset the world still ticks and every decision is still made.
    actors: object | None = None
    #: The network answering journeys: asks the directory's organisations and hears
    #: back. None when partners are off.
    partners: object | None = None
    #: The family's books (`live/kharcha.py`). None where nothing is kept.
    kharcha: object | None = None
    #: Open networks (Beckn/ONDC) a LIVE organisation is reached through.
    network: object | None = None
    #: Vendors' own payment gateways.
    payments: object | None = None
    #: False until the first full plan has run. Learning the state of a
    #: hospital is not news to anybody in it: nothing has changed yet, so
    #: nothing is written. See `plan_all`.
    _has_planned: bool = False
    #: Fact sources — journeys, resource status, lab queues, entitlements.
    #: Every call is timed, written to the ledger and published, so a figure on
    #: screen can be traced back to the call that produced it.
    tools: object | None = None
    #: Seconds of real time between caregiver messages. Actors are the only
    #: unbounded cost in the loop, so their cadence is explicit.
    inbound_every_seconds: float = 15.0
    #: Which system to ask about each hospital, keyed by hospital id. A
    #: callable, not a dict: an unknown hospital answers with the desk adapter
    #: rather than raising, because "no system here" is an ordinary state.
    hospitals: object | None = None
    #: How often to re-read the appointment window. Bahmni has no change
    #: feed, so each cycle is a full read — see `live/hospital_sync.py`.
    hospital_poll_seconds: float = 3.0
    hospital_window_days: int = 30
    hospital_timezone: str = "Asia/Kolkata"
    #: patient id -> the approval `Task` filed in that hospital's own system,
    #: so it can be closed when a person decides. Absent when the hospital has
    #: no system, or when filing it failed — neither blocks the decision.
    approval_tasks: dict = field(default_factory=dict)
    #: One connector per hospital that has a system, keyed by hospital id.
    #: Each holds its own snapshot and cursor: two hospitals both running an
    #: "MRI-1" must not share a dictionary keyed on appointment reference.
    hospital_syncs: dict = field(default_factory=dict)

    #: Work that has started and not finished, keyed by id. Published so a
    #: console shows that something is happening instead of leaving a navigator
    #: watching an unchanged screen and guessing whether it is broken.
    active_work: dict[str, dict] = field(default_factory=dict)

    plans: dict[str, PlanRun] = field(default_factory=dict)
    #: The last journey guide each family was told about, to say only what changed.
    guides: dict[str, object] = field(default_factory=dict)
    inbound: list[InboundRecord] = field(default_factory=list)
    #: Everything actually sent to a family, in the order they received it.
    #: Kept because "the family hears first" is a claim about what reached a
    #: phone, and an event saying a message was published is not the same as a
    #: record of what it said.
    outbound: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    #: Ranked options awaiting a human, keyed by patient id — one pending
    #: disruption response per patient at a time.
    options: dict[str, OptionSet] = field(default_factory=dict)
    #: What families have said they can manage, keyed by patient then topic.
    #: Waiting on a person, exactly like `options`: a budget answer is a
    #: proposal until a navigator agrees it is what the family meant.
    budget: dict[str, dict[str, BudgetAnswer]] = field(default_factory=dict)
    #: Questions Saathi has asked a family and not had an answer to, plus the
    #: history of every one it asked. See `live/dialogue.py` — this is the
    #: first thing in the runner that remembers having spoken.
    conversation: Conversation = field(default_factory=Conversation)
    #: Readings of what families asked for, waiting on a navigator. A request
    #: is a proposal until `confirmed_by` is set; the planner never sees one
    #: before that. Keyed by patient id, newest last.
    requests: dict[str, list[PatientRequest]] = field(default_factory=dict)
    #: The last option search per patient — every candidate the planner tried
    #: and why each lived or died. Kept so the Console can answer "what else
    #: did you consider?" after the decision, which the plan alone cannot.
    searches: dict[str, Search] = field(default_factory=dict)
    approvals: list[ApprovalDecision] = field(default_factory=list)
    ivr_confirmations: dict[str, IVRConfirmation] = field(default_factory=dict)
    #: "press advance" progress per scripted story — see `advance_story`.
    story_progress: dict[str, int] = field(default_factory=dict)

    _task: asyncio.Task | None = None
    _inbound_task: asyncio.Task | None = None
    _partner_task: asyncio.Task | None = None
    _kharcha_task: asyncio.Task | None = None
    _hospital_tasks: list = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _rng: random.Random = field(default_factory=lambda: random.Random(7))
    _work_seq: int = 0

    # ---------------- lifecycle ----------------

    def restore(self) -> None:
        """Take back what a restart interrupted: options waiting on a human, and
        the approvals already given. Once; a second call finds nothing to take."""
        for stored in self.world.restored_option_sets:
            self.options[stored.patient_id] = OptionSet(
                patient_id=stored.patient_id,
                disruption_id=stored.disruption_id,
                options=stored.options,
                created_at=stored.created_at,
            )
            self.world.pending_approval[stored.patient_id] = stored.disruption_id
        self.approvals.extend(self.world.restored_approvals)
        # What each family was told, so a restart does not empty their thread.
        self.outbound.extend(self.world.restored_messages)
        self.world.restored_option_sets = ()
        self.world.restored_approvals = ()
        self.world.restored_messages = ()

    async def start(self) -> None:
        self.restore()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop(), name="saathi-live")
        if self._inbound_task is None or self._inbound_task.done():
            self._inbound_task = asyncio.create_task(
                self._inbound_loop(), name="saathi-inbound"
            )
        if self.partners is not None and (self._partner_task is None or self._partner_task.done()):
            self._partner_task = asyncio.create_task(self._partner_loop(), name="saathi-partners")
            # Said out loud because the failure is silent: without this task the
            # network's answers never land, no error is raised anywhere, and the
            # only symptom is a chain that stops halfway through a demonstration.
            logger.info("partner loop started: simulated organisations will answer")
        elif self.partners is None:
            logger.info("no partner desk: nothing will answer on the network's behalf")
        self._start_hospital_sync()
        run_books = getattr(self.kharcha, "run", None)
        if run_books is not None and (self._kharcha_task is None or self._kharcha_task.done()):
            self._kharcha_task = asyncio.create_task(run_books(), name="saathi-kharcha")
        # Plan once up front so a console that connects before the first tick
        # still sees real decisions rather than an empty page.
        await self.plan_all()
        await self.update_metrics()

    async def stop(self) -> None:
        for task in (
            self._task,
            self._inbound_task,
            self._partner_task,
            self._kharcha_task,
            *self._hospital_tasks,
        ):
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        self._task = None
        self._inbound_task = None
        self._partner_task = None
        self._kharcha_task = None
        self._hospital_tasks = []

    @contextlib.asynccontextmanager
    async def working(self, task: str, *, patient_id: str | None = None, detail: str = ""):
        """Announce a piece of work, run it, then say what it cost.

        The `started` event is the point. A system that only reports finished
        work looks frozen while it is busy, and a navigator cannot tell a slow
        re-plan from a dead console. Saying "re-planning six families" before
        the six families are re-planned costs one event and removes the doubt.
        """
        work_id = f"w{self._work_seq}"
        self._work_seq += 1
        entry = {
            "id": work_id,
            "task": task,
            "detail": detail,
            "patient_id": patient_id,
            "started_at": datetime.now(UTC).isoformat(),
        }
        self.active_work[work_id] = entry
        self.bus.publish(
            EventKind.AGENT_STARTED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=task,
            work_id=work_id,
            detail=detail,
        )
        started = perf_counter()
        try:
            yield entry
        finally:
            self.active_work.pop(work_id, None)
            self.bus.publish(
                EventKind.AGENT_FINISHED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=task,
                duration_ms=(perf_counter() - started) * 1000,
                work_id=work_id,
            )

    def on_tool_result(self, result) -> None:
        """Called by the toolbox for every fact it fetches.

        Two things happen and both matter: the claim becomes a ledger row, so a
        number on a screen has a source a navigator can open; and an event is
        published with the measured latency, so the console shows the lookup
        happening rather than the answer simply appearing.
        """
        self.ledger.record_once(
            patient_id=getattr(result, "patient_id", "") or "cohort",
            source=result.source,
            source_record_id=result.source_record_id,
            claim=result.claim,
            metadata={"tool": result.tool, "provider": result.provider},
        )
        self.bus.publish(
            EventKind.TOOL_CALLED,
            self.world.today.isoformat(),
            summary=result.claim,
            duration_ms=result.duration_ms,
            tool=result.tool,
            provider=result.provider,
        )
        self._bump(f"tool:{result.tool}")

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

    async def forget_working_state(self) -> None:
        """Forget what has been asked, read and searched — and nothing else.

        `reset` refuses on real records, and rightly: it rewinds the world
        and would delete patients, steps and plans that somebody entered.
        But a rehearsal needs to get back to "nobody has been asked yet"
        without destroying anything, and the things in the way are not
        records at all — they are working state this process happens to be
        holding.

        So this clears the conversation, the readings waiting on a navigator,
        the last option search, and each connector's memory of what it has
        already acted on. It touches no patient, no step, no plan and no
        ledger entry, which is why it is safe on a real world where `reset`
        is not.

        Found the hard way: three takes of a film in a row produced three
        copies of the same family's request on screen, because the demo
        called `reset`, `reset` raised on a real world, and the caller had
        swallowed the error.
        """
        async with self._lock:
            self.conversation.reset()
            self.requests.clear()
            self.searches.clear()
            self.options.clear()
            for sync in self.hospital_syncs.values():
                sync.forget()
        self._bump("working_state_cleared")
        self.bus.publish(
            EventKind.RUNNER_STATE,
            self.world.today.isoformat(),
            summary="Cleared what had been asked and read; records untouched",
        )

    async def reset(self, start: date | None = None) -> None:
        if self.world.real:
            raise RuntimeError(
                "real records cannot be reset — use forget_working_state() to "
                "clear what has been asked and read without deleting anything"
            )
        async with self._lock:
            self.world.reset(start)
            self.plans.clear()
            self.inbound.clear()
            self.alerts.clear()
            self.counters.clear()
            self.options.clear()
            self.approvals.clear()
            self.conversation.reset()
            self.requests.clear()
            self.searches.clear()
            # The connectors too, or a rehearsed scenario shows nothing the
            # second time: they act once per leave and once per open order.
            for sync in self.hospital_syncs.values():
                sync.forget()
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
                pace = getattr(self.world.clock, "tick_seconds", None)
                await asyncio.sleep(max(0.25, pace or self.world.clock.seconds_per_day))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - the world must not stop on one bad day
                logger.exception("tick failed; continuing")
                await asyncio.sleep(1.0)

    def _start_hospital_sync(self) -> None:
        """Begin polling every connected hospital system, one task each.

        Separate tasks rather than one loop over all hospitals: a district
        hospital that goes unreachable must not stop the cancer centre's
        three-second poll, and on stage that difference is the whole demo.

        Said out loud either way. A connector that silently never starts looks
        exactly like a hospital that never changes anything, and the only
        symptom is a button press that does nothing.
        """
        if self._hospital_tasks:
            return
        configured = self.hospitals.all() if self.hospitals is not None else {}
        connected = {
            hospital_id: system
            for hospital_id, system in configured.items()
            if getattr(system, "live", False)
        }
        if not connected:
            logger.info("no hospital system connected: the desks are the feed")
            return

        from .hospital_sync import HospitalSync

        for hospital_id, system in connected.items():
            self.hospital_syncs[hospital_id] = HospitalSync(
                hospital=system,
                runner=self,
                hospital_id=hospital_id,
                window_days=self.hospital_window_days,
                timezone=self.hospital_timezone,
            )
            self._hospital_tasks.append(
                asyncio.create_task(
                    self._hospital_loop(hospital_id), name=f"saathi-hospital-{hospital_id}"
                )
            )
            logger.info(
                "connector started for %s: reading %s every %.1fs over a %d-day window",
                hospital_id,
                getattr(system, "name", "its hospital system"),
                self.hospital_poll_seconds,
                self.hospital_window_days,
            )

    async def _hospital_loop(self, hospital_id: str) -> None:
        """Re-read one hospital's appointment window, forever."""
        pace = max(1.0, self.hospital_poll_seconds)
        sync = self.hospital_syncs[hospital_id]
        while True:
            try:
                await sync.poll_once()
                await asyncio.sleep(pace)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad read must not stop the rest
                logger.exception("hospital poll failed for %s; continuing", hospital_id)
                await asyncio.sleep(pace)

    def sync_for(self, hospital_id: str):
        """The connector for one hospital, or None if it has no system."""
        return self.hospital_syncs.get(hospital_id)

    def sync_for_patient(self, patient_id: str):
        """The connector for the hospital treating this family.

        Write-back needs this: approving an option books a slot, and it must be
        booked in *that family's* hospital, not whichever system happens to be
        first in the dictionary.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None
        return self.hospital_syncs.get(patient.hospital_id)

    async def _partner_loop(self) -> None:
        """Every few seconds, hear back from any simulated organisation whose time has come."""
        while True:
            try:
                await self.settle_partners()
                await asyncio.sleep(5.0)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad answer must not stop the rest
                logger.exception("partner round failed; continuing")
                await asyncio.sleep(5.0)

    async def settle_partners(self) -> int:
        desk = self.partners
        if desk is None:
            return 0
        answered = 0
        for patient_id, item in desk.due():
            if desk.settle(item) is not None:
                answered += 1
                await self.plan_patient(patient_id, allow_render=True)
        for patient_id, item in desk.overdue():
            desk.expire(item)
            answered += 1
            await self.plan_patient(patient_id, allow_render=True)
        network = self.network
        if network is not None:
            for patient_id in await network.tick():
                answered += 1
                await self.plan_patient(patient_id, allow_render=True)
        return answered

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
        if self.world.real:
            # A person confirms every record in a real hospital; nothing is assumed.
            return
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
        await self._after_release(
            step,
            note=candidate.note,
            confirmed_by="auto" if automatic else "desk staff",
            candidate_id=candidate_id,
            automatic=automatic,
        )
        return True

    async def release_step(
        self, step_id: str, *, by: str = "desk staff", note: str = ""
    ) -> CareStep:
        """Mark a report released because a person said so.

        The real world's way in: there is no simulated candidate to confirm, so
        the person's statement is the record. Everything that follows is the same
        as a confirmed candidate — ledger row, events, an immediate re-plan.
        """
        async with self._lock:
            before = self.world.step(step_id)
            if before is None:
                raise LookupError(step_id)
            if before.kind not in REPORT_STEPS:
                raise ValueError("only a report can be released")
            if before.status is StepStatus.RESULT_AVAILABLE:
                return before
            step = self.world.apply_release(step_id)
        assert step is not None
        await self._after_release(
            step, note=note, confirmed_by=by, candidate_id=None, automatic=False
        )
        return step

    async def _after_release(
        self,
        step: CareStep,
        *,
        note: str,
        confirmed_by: str,
        candidate_id: str | None,
        automatic: bool,
    ) -> None:
        self._learn_turnaround(step)
        before = self.ledger_size()
        entry = self.ledger.record_once(
            patient_id=step.patient_id,
            source=SourceSystem.HOSPITAL_FEED,
            source_record_id=step.id,
            claim=f"{step.kind.value} is {step.status.value}",
            metadata={
                "released_on": self.world.today.isoformat(),
                "confirmed_by": confirmed_by,
                "note": note,
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
                + (" (auto)" if automatic else f" by {confirmed_by}")
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

    def _learn_turnaround(self, step: CareStep) -> None:
        """In the real world a release is also a measurement.

        Days from the sample being taken to the report landing is exactly what
        the forecast is calibrated on, so each release makes the next forecast
        for that queue a little better grounded. The demo's history is
        synthetic and is left alone.
        """
        if not self.world.real or not step.queue or step.completed_on is None:
            return
        days = (self.world.today - step.completed_on).days
        if days < 0:
            return
        patient = self.world.patient(step.patient_id)
        self.world.record_turnaround(
            step.queue, float(days), patient.hospital_id if patient else ""
        )
        self.planner.predictor.fit([TurnaroundSample(queue=step.queue, days=float(days))])

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
                f"reported {kind.value.replace('_', ' ')} — {len(affected)} "
                f"famil{'y' if len(affected) == 1 else 'ies'} affected"
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
        async with self.working(
            f"Telling {len(affected)} famil{'y' if len(affected) == 1 else 'ies'} not to travel",
            detail="before any new date is worked out",
        ):
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
            self._record_outbound(
                patient_id,
                kind="holding",
                body=message.body,
                language=language.value,
                channel=channel.value,
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

    # ---------------- what the family can manage ----------------

    def budget_answers_for(self, patient_id: str) -> dict[str, BudgetAnswer]:
        return dict(self.budget.get(patient_id, {}))

    def record_budget_answer(self, answer: BudgetAnswer) -> BudgetAnswer:
        """Take down what the family said. Nothing moves yet.

        Deliberately inert. The family has told us something about their own
        circumstances, and acting on it the instant it arrives would mean a
        mis-tap or a mis-transcription silently rebooking their journey.
        """
        self.budget.setdefault(answer.patient_id, {})[answer.topic.value] = answer
        return answer

    def confirm_budget_answer(
        self, patient_id: str, topic: BudgetTopic, by: str
    ) -> BudgetAnswer | None:
        """A navigator agrees this is what the family meant, and it takes effect.

        Two different outcomes, and only one of them is a plan change. A chosen
        organisation is written into the partners section and asked. "We cannot
        manage any of these" is not a cheaper booking — it is a family with no
        fare, which is a person and a scheme, so it raises an alert and leaves
        the journey exactly where it was.
        """
        answer = self.budget.get(patient_id, {}).get(topic.value)
        if answer is None:
            return None
        confirmed = answer.model_copy(update={"confirmed_by": by})
        self.budget[patient_id][topic.value] = confirmed

        if confirmed.needs_help:
            self.alerts.append(
                Alert(
                    id=f"alert-{patient_id}-budget-{topic.value}-{len(self.alerts)}",
                    patient_id=patient_id,
                    kind=AlertKind.NEEDS_HELP,
                    raised_at=datetime.now(UTC),
                    detail=(
                        f"the family says they cannot manage the {topic.value} for this "
                        f"journey" + (f": {confirmed.said}" if confirmed.said else "")
                    ),
                )
            )
            return confirmed

        desk = self.partners
        remember = getattr(desk, "remember_choice", None)
        if remember is not None and confirmed.organisation_id:
            remember(patient_id, TOPIC_NEED[topic], confirmed.organisation_id, by)
        return confirmed

    def means_for(self, patient_id: str) -> Means:
        """What this family can carry, when anybody has asked them.

        The partner desk is the only object here holding the onboarding store,
        so it is the only one that can answer. With partners switched off
        nobody has asked, and the option ranking falls back to the order it has
        always used — which is the right default, not a degraded one.
        """
        reader = getattr(self.partners, "means_for", None)
        return reader(patient_id) if reader is not None else Means.NOT_STATED

    def _enumerate_options_sync(
        self,
        patient: Patient,
        steps: list,
        disruption: Disruption,
        target_kind: StepKind,
        cycle,
        round_trip_hours: float | None = None,
        search: Search | None = None,
    ) -> tuple[PlanOption, ...]:
        direct = options_module.enumerate_candidates(
            patient, steps, disruption, target_kind, self.planner.graph_for(patient),
            self.planner.predictor, self.world.today, cycle=cycle,
            search=search,
            # The hospital's saved rules, when it has saved any; None keeps the
            # built-in behaviour.
            policy=self.planner.rules_for(patient.hospital_id),
            round_trip_hours=round_trip_hours,
            #: Which way round the nights-versus-trips trade goes for this
            #: household. See `domain/affordability.py`.
            means=self.means_for(patient.id),
        )
        if direct:
            return direct
        return options_module.opportunistic_bundle_candidates(
            patient, steps, disruption, target_kind, self.planner.graph_for(patient),
            self.planner.predictor, self.world.today, cycle=cycle, search=search,
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

        # How long this family's round trip is decides whether waiting in the
        # city beats going home — the difference between Shambhu's forty hours
        # and Anita's two. Fetched rather than inferred from kilometres, and
        # the lookup shows up in the activity strip with its own latency.
        async with self.working(
            f"Looking up the journey from {patient.home_district}",
            patient_id=patient_id,
            detail=f"to {self.world.hospital_place}",
        ):
            round_trip = await asyncio.to_thread(self.journey_hours, patient)

        search = Search(patient_id=patient_id, step_kind=target_kind.value)
        started = perf_counter()
        async with self.working(
            "Working out the options",
            patient_id=patient_id,
            detail="each one judged by the same rule as the live plan",
        ):
            candidates = await asyncio.to_thread(
                self._enumerate_options_sync,
                patient, steps, disruption, target_kind, cycle, round_trip, search,
            )
        elapsed = (perf_counter() - started) * 1000

        # What the planner looked at, not only what it chose. The filtering is
        # unchanged — a family is still never offered a date the rules would
        # then refuse — but the discarding is now on the record, which is the
        # only way to answer "what else did you consider?" after the fact.
        self.searches[patient_id] = search
        self.bus.publish(
            EventKind.PLAN_SEARCHED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{patient_id}: {search.summary()}",
            duration_ms=elapsed,
            search=search.to_json(),
        )

        if len(candidates) <= 1:
            # Simple case: nothing to choose between, so there is nothing for
            # a human to decide. Apply the only candidate's shift and re-plan
            # through the real pipeline, same as any other fact changing.
            if candidates:
                await self._apply_resolution(patient_id, disruption, candidates[0])
            await self.plan_patient(patient_id, allow_render=patient_id in self.world.watched)
            return

        async with self._lock:
            option_set = OptionSet(
                patient_id=patient_id,
                disruption_id=disruption.id,
                options=candidates,
                created_at=datetime.now(UTC),
            )
            self.options[patient_id] = option_set
            self.world.pending_approval[patient_id] = disruption.id
            if self.world.store is not None:
                self.world.store.save_option_set(
                    StoredOptionSet(
                        patient_id=patient_id,
                        disruption_id=disruption.id,
                        options=candidates,
                        created_at=option_set.created_at,
                    )
                )
        await self._file_approval_task(patient_id, option_set, disruption)
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

        # Before anything is recorded here and before any phone rings: put the
        # date into the hospital's own diary. If it refuses, this raises and
        # the rest of the method never runs — the option stays pending and no
        # family is told a time the hospital did not agree to.
        await self._write_back(patient_id, option)

        async with self._lock:
            del self.options[patient_id]
            self.world.pending_approval.pop(patient_id, None)
            if self.world.store is not None:
                self.world.store.delete_option_set(patient_id)
        if disruption is not None:
            await self._apply_resolution(patient_id, disruption, option)
        elif option.target_on is not None and self.world.step(option.target_step_id) is not None:
            # An option born of a family's own request has no disruption behind it,
            # so nothing else moves the step to the date a navigator just approved.
            async with self._lock:
                self.world.reschedule_steps({option.target_step_id}, option.target_on)

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
        if self.world.store is not None:
            self.world.store.add_approval(approval)
        await self._close_approval_task(patient_id, outcome="approved", by=approved_by)
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

    async def _file_approval_task(self, patient_id: str, option_set, disruption) -> None:
        """Put the request on the hospital's own record, as a FHIR Task.

        So that a change proposed to a hospital exists in that hospital's
        system — queryable and auditable by them, without asking us. The
        decision is still made in Saathi's panel, because Bahmni accepts a
        Task over its API and has no screen that shows one; writing it there
        alone would file the request where nobody looks.

        Never blocks. A hospital that refuses the task still gets the
        suggestion and the desk still decides: an audit convenience must not
        be able to stop a family being re-planned.
        """
        system = self.hospitals(self._hospital_of(patient_id)) if self.hospitals else None
        if system is None or not getattr(system, "live", False):
            return
        patient = self.world.patient(patient_id)
        if patient is None:
            return

        from ..ports.fhir import approval_task

        requires_doctor = any(self.touches_treatment(o) for o in option_set.options)
        resource = self.world.resources.get(disruption.resource_id) if disruption else None
        what = resource.display_name if resource else (disruption.resource_id if disruption else "")
        sync = self.hospital_syncs.get(patient.hospital_id)
        booking = None
        if sync is not None:
            step = self.world.step(option_set.options[0].target_step_id)
            if step is not None:
                booking = sync.booking_for(patient_id, step)

        task = approval_task(
            patient_ref=booking.patient_ref if booking else "",
            patient_display=patient.name or patient_id,
            summary=(
                f"Re-plan after {what} became unavailable"
                + (f" ({booking.starts_at:%d %b %H:%M})" if booking else "")
            ),
            description=_describe_options(option_set.options),
            requested_at=datetime.now(UTC),
            options=len(option_set.options),
            requires_doctor=requires_doctor,
        )
        try:
            ref = await asyncio.to_thread(system.create_task, task)
        except Exception as exc:  # noqa: BLE001 - an audit record must not block care
            logger.warning("could not file an approval task for %s: %s", patient_id, exc)
            self._bump("hospital:task_refused")
            return

        self.approval_tasks[patient_id] = (ref, task)
        self._bump("hospital:task_filed")
        logger.info("filed approval task %s for %s in the hospital's own system", ref, patient_id)

    async def _close_approval_task(self, patient_id: str, *, outcome: str, by: str) -> None:
        """Record on the hospital's own task what a person decided, and when."""
        held = self.approval_tasks.pop(patient_id, None)
        if held is None:
            return
        ref, task = held
        system = self.hospitals(self._hospital_of(patient_id)) if self.hospitals else None
        if system is None:
            return

        from ..ports.fhir import completed_task

        try:
            await asyncio.to_thread(
                system.update_task,
                ref,
                completed_task(task, outcome=outcome, by=by, at=datetime.now(UTC)),
            )
        except Exception as exc:  # noqa: BLE001 - as above
            logger.warning("could not close approval task %s: %s", ref, exc)
            return
        self._bump(f"hospital:task_{outcome}")

    def _hospital_of(self, patient_id: str) -> str:
        patient = self.world.patient(patient_id)
        return patient.hospital_id if patient else ""

    async def reject_options(
        self,
        *,
        patient_id: str,
        rejected_by_role: Role,
        rejected_by: str,
        reason: str = "",
    ) -> dict:
        """None of these will do; the desk takes this family on by hand.

        A real desk sometimes knows something the option table does not — a
        family already at the station, a consultant who will see them anyway.
        Without this verb that knowledge has nowhere to go and the only way to
        clear the queue is to approve something nobody believes in.

        Deliberately narrow. Nothing is written back to the hospital, nothing
        is sent to the family, and no new plan is promised: the options are
        cleared, the decision is recorded with a name against it, and the
        family drops back to whatever the planner honestly says — which, with
        their booking gone, is UNCERTAIN, and puts them on the list of people
        who need a person. That is the true state, and a desk that rejected
        every option has just said so.
        """
        option_set = self.options.get(patient_id)
        if option_set is None:
            raise LookupError("no options are waiting for this patient")

        async with self._lock:
            del self.options[patient_id]
            self.world.pending_approval.pop(patient_id, None)
            if self.world.store is not None:
                self.world.store.delete_option_set(patient_id)

        entry = self.ledger.record_once(
            patient_id=patient_id,
            source=SourceSystem.NAVIGATOR,
            source_record_id=f"rejection:{option_set.disruption_id}:{patient_id}",
            claim=(
                f"{rejected_by_role.value} turned down all "
                f"{len(option_set.options)} options for disruption "
                f"{option_set.disruption_id}"
            ),
            metadata={"rejected_by": rejected_by, "reason": reason},
        )
        self.bus.publish(
            EventKind.OPTIONS_REJECTED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=(
                f"{rejected_by} ({rejected_by_role.value}) turned down every option "
                f"for {patient_id} — taking it on by hand"
            ),
            disruption_id=option_set.disruption_id,
            reason=reason,
        )
        self._bump("options:rejected")
        await self._close_approval_task(patient_id, outcome="rejected", by=rejected_by)
        await self.plan_patient(patient_id)
        return {
            "patient_id": patient_id,
            "disruption_id": option_set.disruption_id,
            "rejected_by": rejected_by,
            "rejected_by_role": rejected_by_role.value,
            "reason": reason,
            "ledger_id": entry.id,
        }

    async def _write_back(self, patient_id: str, option: PlanOption):
        """Book the approved slot in the hospital system.

        Does nothing and says so quietly when there is no HMS connected, when
        the option carries no target date, or when the hospital holds no
        booking for this step — all three are ordinary states, not failures.
        Anything else raises `HospitalUnavailable` up through `approve_option`,
        which is the point: a write-back that failed silently would leave the
        hospital's diary and the family's plan disagreeing, with only the
        family finding out.
        """
        if option.target_on is None:
            return None
        step = self.world.step(option.target_step_id)
        if step is None:
            return None
        # The family's own hospital, not whichever system answered first. A
        # slot booked into the wrong hospital is worse than no slot at all.
        sync = self.sync_for_patient(patient_id)
        if sync is None:
            return None

        async with self.working(
            "Booking the new slot in the hospital system",
            patient_id=patient_id,
            detail=f"{step.kind.value.replace('_', ' ')} on {option.target_on:%a %d %b}",
        ):
            booked = await sync.rebook(
                patient_id=patient_id, step=step, target_on=option.target_on
            )

        if booked is not None:
            self.ledger.record_once(
                patient_id=patient_id,
                source=SourceSystem.HOSPITAL_FEED,
                source_record_id=f"appointment:{booked.ref}",
                claim=(
                    f"{booked.service_name or 'appointment'} booked for "
                    f"{booked.starts_at:%d %b %H:%M} in the hospital system"
                ),
                metadata={"written_back": True, "step_id": step.id},
            )
            self._bump("hospital:written_back")
        return booked

    async def _fan_out_approval_messages(self, patient_id: str, option: PlanOption) -> None:
        """Every family member hears the change, each on their own channel."""
        layer = self.planner.language_layer
        patient = self.world.patient(patient_id)
        if layer is None or patient is None:
            return
        # Derived, not listed. A hand-written set of option-only fields silently
        # rotted the moment `target_on` was added to `PlanOption`: approving an
        # option started raising `extra_forbidden` and the story simply stopped
        # advancing, with the failure visible only as a missing beat.
        option_only = set(PlanOption.model_fields) - set(VisitPlan.model_fields)
        plan = VisitPlan(**option.model_dump(exclude=option_only))
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

    # ---------------- what language this family reads ----------------

    async def set_language(self, patient_id: str, language: Language) -> dict | None:
        """The family picks their language, and the system obeys from then on.

        Not a translation of the screen. The preference is written to the
        patient's record, logged as a fact the family asserted, and the current
        plan is re-rendered through the same language layer and the same guard
        as every other outbound message — so what comes back is a real Groq
        render in the new language, not a lookup table. A guard-held render
        stays held; switching language is not a way to get past it.

        Returns None for an unknown patient. Returns the unchanged record when
        the family picks the language they already have, without re-rendering —
        a no-op must not cost an API call or a ledger row.
        """
        async with self._lock:
            before = self.world.patient(patient_id)
            if before is None:
                return None
            if before.language is language:
                return {"patient_id": patient_id, "language": language.value, "changed": False}

            patient = self.world.set_language(patient_id, language)
            if patient is None:  # pragma: no cover — guarded by the read above
                return None

            name = LANGUAGE_NAMES.get(language, language.value)
            self.ledger.record_once(
                patient_id=patient_id,
                source=SourceSystem.CAREGIVER_REPLY,
                source_record_id=f"language-{patient_id}",
                claim=f"family asked to be written to in {name}",
                metadata={"language": language.value, "previous": before.language.value},
            )
            self.bus.publish(
                EventKind.LANGUAGE_CHANGED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"{patient_id} switched to {name}",
                language=language.value,
                previous=before.language.value,
            )
            # A marker in the family's own thread, at the point the language
            # changed. Without it the history reads as a jumble of two scripts
            # with no explanation; with it, everything above the line is
            # plainly "before" and everything below is "after". The record is
            # still never rewritten — this explains the seam rather than
            # hiding it.
            self._record_outbound(
                patient_id,
                kind="language",
                body=name,
                language=language.value,
                channel=Channel.WHATSAPP.value,
            )
            # Re-render now rather than waiting for the next plan change: the
            # family is looking at the screen, and a message in the language
            # they just left is the one thing this must not leave behind.
            await self._render_for(patient_id)

        return {"patient_id": patient_id, "language": language.value, "changed": True}

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

        beat = beats[index]
        action, params = beat.action, beat.params
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
        elif action == "inbound":
            # No text here on purpose. The beat names the worry; the caregiver
            # actor writes the message in the family's own language, and the
            # real guard reads whatever it produced. Scripting the words would
            # make the guard's verdict a foregone conclusion, which is the one
            # thing this moment exists to demonstrate.
            await self.receive_inbound(params["patient_id"], kind=params.get("kind"))
        elif action == "confirm":
            pending = [
                c for c in self.ivr_confirmations.values()
                if c.patient_id == params["patient_id"] and not c.confirmed
            ]
            for confirmation in pending:
                await self.confirm_ivr(confirmation.id, "1")

        self.story_progress[story] = index + 1
        return {
            "story": story,
            "done": index + 1 >= len(beats),
            "beat": beat.to_json(),
            "index": index,
        }

    def story_state(self) -> dict:
        """Where each story has got to, and who acts next.

        The story bar reads this to say "next: Seema approves" before anybody
        presses anything — the brief's table, rendered from the beats rather
        than retyped into the console.
        """
        from ..synthetic.scripted import STORIES, STORY_BEATS

        stories = []
        for meta in STORIES:
            beats = STORY_BEATS[meta["id"]]
            index = self.story_progress.get(meta["id"], 0)
            stories.append(
                {
                    **meta,
                    "total": len(beats),
                    "index": index,
                    "done": index >= len(beats),
                    "next": beats[index].to_json() if index < len(beats) else None,
                    "beats": [b.to_json() for b in beats],
                }
            )
        return {"stories": stories, "scripted": self.world.scripted}

    # ---------------- planning ----------------

    def _plan_sync(
        self,
        patient: Patient,
        steps: list,
        compose: bool,
        disruptions: tuple = (),
        readiness_items: tuple = (),
    ) -> dict:
        # `disruptions` and `readiness_items` are passed in rather than read off
        # the world: this runs on a worker thread and must not race the lock
        # that owns it.
        return self.planner.plan_visit(
            patient=patient,
            steps=steps,
            target_kind=self.world.target_kind_for(patient.id),
            today=self.world.today,
            compose=compose,
            disruptions=disruptions,
            readiness_items=readiness_items,
        )

    def _plan_batch_sync(
        self,
        work: list[tuple[Patient, list]],
        disruptions: tuple,
        items: dict[str, tuple] | None = None,
    ) -> list[dict]:
        items = items or {}
        return [
            self._plan_sync(patient, steps, False, disruptions, items.get(patient.id, ()))
            for patient, steps in work
        ]

    def journey_hours(self, patient) -> float | None:
        """Round-trip travel time for this family, fetched and cached.

        Feeds `HospitalPolicy.gap_days`, which decides whether a family waits in
        the city between visits or goes home — the difference between Shambhu's
        40-hour round trip and Anita's two-hour one. Returns None when no
        journey is on record, and the policy then falls back to its cautious
        default rather than assuming anybody lives nearby.
        """
        if self.tools is None:
            return None
        result = self.tools.run(
            lambda: self.tools.geo.journey(patient.home_district, self.world.hospital_place)
        )
        return result.value.round_trip_hours if result else None

    async def plan_all(self) -> None:
        disruptions = tuple(self.world.open_disruptions())
        work = [
            (patient, self.world.steps_for(patient.id)) for patient in self.world.patients()
        ]
        started = perf_counter()
        async with self.working(
            f"Re-planning {len(work)} families",
            detail="walking the care-step graph for each one",
        ):
            items = {p.id: self.world.readiness_for(p.id) for p, _ in work}
            results = await asyncio.to_thread(self._plan_batch_sync, work, disruptions, items)
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
            # A message says something changed. On the first pass nothing has:
            # the planner is learning what the hospital already knew, and every
            # family's plan is "new" only because this process just started.
            #
            # Writing to all of them anyway cost a hundred and ten model calls
            # and a 429 from the provider, and every later call — including the
            # ones that move a family's journey along — queued behind that
            # burst. The network's answers arrived four minutes late instead of
            # the ninety seconds the demonstration promises.
            if run.patient_id in self.world.watched and self._has_planned:
                await self._render_for(run.patient_id)

        if self.partners is not None:
            for patient, _ in work:
                if await self.partners.ask_for_needs(patient.id):
                    await self.plan_patient(patient.id, allow_render=True)
        for patient, _ in work:
            await self._announce_guide(patient.id)
        # Everything from here on is a change, and changes are worth saying.
        self._has_planned = True

    async def _announce_guide(self, patient_id: str) -> None:
        """Tell a family what changed on their journey, in their language, in the thread."""
        from ..guide.update import guide_update
        from ..language.guide_messages import render_guide_message
        from .guides import compute_guide

        patient = self.world.patient(patient_id)
        if patient is None or not self.world.real:
            return
        now = await compute_guide(self, patient_id)
        before = self.guides.get(patient_id)
        self.guides[patient_id] = now
        if now is None or before is None:
            return  # the first guide is a baseline, not news
        update = guide_update(before, now)
        body = render_guide_message(patient.language, update) if update else None
        if body is None:
            return
        self._record_outbound(
            patient_id,
            kind="guide",
            body=body,
            language=patient.language.value,
            channel="whatsapp",
            rendered_by="template",
        )
        self.bus.publish(
            EventKind.MESSAGE_RENDERED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{patient_id}: journey update sent",
            message_kind="guide",
        )

    async def plan_patient(self, patient_id: str, *, allow_render: bool = False) -> PlanRun | None:
        patient = self.world.patient(patient_id)
        if patient is None:
            return None
        steps = self.world.steps_for(patient_id)
        disruptions = tuple(self.world.open_disruptions())
        before = self.ledger_size()
        items = self.world.readiness_for(patient_id)
        result = await asyncio.to_thread(
            self._plan_sync, patient, steps, False, disruptions, items
        )
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
        if self.partners is not None and await self.partners.ask_for_needs(patient_id):
            # The journey now has parties to wait on; plan again to say so.
            return await self.plan_patient(patient_id, allow_render=allow_render)
        await self._announce_guide(patient_id)
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
        async with self.working(
            f"Writing in {LANGUAGE_NAMES.get(patient.language, '')}",
            patient_id=patient_id,
            detail="rendered from the plan, then checked against it",
        ):
            message = await asyncio.to_thread(
                layer.render, run.plan, patient.language, Channel.WHATSAPP, self.ledger
            )
        elapsed = (perf_counter() - started) * 1000
        run.message = message
        run.render_ms = elapsed
        run.rendered_by = getattr(layer, "describe", lambda: "language layer")()
        self._bump("renders")

        language = LANGUAGE_NAMES.get(patient.language, patient.language.value)
        self._record_outbound(
            patient_id,
            kind="plan",
            body=message.body,
            language=patient.language.value,
            channel=Channel.WHATSAPP.value,
            held=message.routed_to_care_team,
            reason=message.routing_reason,
            rendered_by=run.rendered_by,
            duration_ms=elapsed,
        )
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
                if self.world.real or not self.world.clock.running or self.actors is None:
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
        else:
            # An answer to something Saathi asked takes precedence over the
            # process-question path: a family replying "nothing before the
            # 1st" to a question about dates is answering, not asking. When
            # the reply turns out to answer nothing, `_read_answer` says so
            # and the ordinary path still runs.
            answered = await self._read_answer(patient, record)
            if not answered and guard.classify_inbound(text) == InboundCategory.PROCESS:
                await self._answer_process_question(patient, record)
        return record

    async def advise_leave_later(
        self, patient_id: str, *, due_at: datetime, delay: timedelta
    ) -> str | None:
        """Tell a family to set out later, because the clinic is behind.

        Generic on purpose: any family with an appointment today who has not
        yet arrived, any delay the clinic's own timestamps show, any of the
        five languages. Nothing here knows which story it is in.

        Returns the message sent, or None when there was nothing worth saying
        — too small a delay, an unknown journey, or text the guard refused.
        None is a normal outcome and most of the time it is the right one.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None

        # When they would have had to set out, from the real routing estimate
        # rather than an assumption. Without it there is no "instead of", so
        # there is no advice — a family told to "leave a bit later" has been
        # given a guess to make, not an answer.
        hours = await asyncio.to_thread(self.journey_hours, patient)
        if not hours:
            logger.info("no journey estimate for %s; not advising a departure", patient_id)
            return None
        leaving_at = due_at - timedelta(hours=float(hours))

        # Which of the two true things to say depends on whether they could
        # still act on the first. A family six hours away from a morning slot
        # left before dawn; "leave later" would be nonsense to them, and the
        # useful fact is that a full corridor does not mean they missed their
        # turn.
        now_leave: datetime | None = None
        if leaving_at > datetime.now(leaving_at.tzinfo):
            advice = leave_later(
                language=patient.language, leaving_at=leaving_at, delay=delay
            )
            if advice is not None:
                body, now_leave = advice
            else:
                return None
        else:
            body = already_travelling(language=patient.language, delay=delay) or ""
            if not body:
                return None

        # The same guard every outbound message goes through. This one carries
        # clock times rather than dates, so there is no date for it to check —
        # what it is here for is the clinical and reassurance rules, which
        # apply to anything a family reads.
        verdict = guard.check_question(body, dates_given=())
        if not verdict.allowed:
            logger.error("refusing to advise %s: %s", patient_id, verdict.reason)
            self.bus.publish(
                EventKind.GUARD_BLOCKED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Guard held delay advice to {patient_id}: {verdict.reason}",
                triggers=list(verdict.triggers),
            )
            return None

        self._record_outbound(
            patient_id,
            kind="advice",
            body=body,
            language=patient.language.value,
            channel=Channel.WHATSAPP.value,
        )
        self._bump("advice_sent")
        minutes = int(delay.total_seconds() // 60)
        summary = (
            f"Told {patient_id} to leave at {now_leave:%H:%M} rather than "
            f"{leaving_at:%H:%M} — the clinic is {minutes} min behind"
            if now_leave is not None
            else (
                f"Told {patient_id} the clinic is {minutes} min behind; "
                "they had already set out"
            )
        )
        self.bus.publish(
            EventKind.ADVICE_SENT,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=summary,
            leave_at=now_leave.isoformat() if now_leave else None,
            was_leaving_at=leaving_at.isoformat(),
            delay_minutes=minutes,
        )
        return body

    def travel_already_paid_for(self, patient_id: str) -> PatientRequest | None:
        """The family's most recent statement that their travel cannot change.

        Only from a reading that carries the sentence it came from — the same
        attribution rule the Console applies. A claim that somebody's money is
        already spent, with nothing behind it, must not be what decides whether
        their visit moves.

        Returns the whole request rather than a bare flag so a caller can quote
        the family on it. "They said the bus cannot be changed" is a reason a
        navigator can act on; `refundable=False` is not.
        """
        for request in reversed(self.requests.get(patient_id, [])):
            if request.rejected_reason is not None:
                continue
            if request.travel.refundable is False and request.travel_is_attributable:
                return request
        return None

    async def escalate_pending_order(
        self,
        patient_id: str,
        *,
        order_ref: str,
        what: str,
        needed_by: date,
        because: str,
        patient_ref: str = "",
        system: object | None = None,
    ) -> str | None:
        """Ask the hospital to bring a report forward, in its own record.

        Returns the task reference, or None when there is no hospital to ask
        or it refused. None is survivable: the Console still shows the family
        as at risk and a navigator can pick up the phone, which is what
        happens today without any of this.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None
        # The caller's own hospital when it has one. A connector that read an
        # order from a hospital *is* holding that hospital, and asking it
        # directly is both simpler and more correct than looking the patient's
        # hospital id back up — those can differ while a family is being
        # transferred, and the order belongs to the one that published it.
        if system is None:
            # `hospitals` is a callable keyed on hospital id, not a dict: an
            # unknown hospital answers with the desk adapter rather than None.
            system = self.hospitals(patient.hospital_id) if self.hospitals else None
        if system is None or not getattr(system, "live", False):
            return None
        if not hasattr(system, "create_task"):
            # An adapter that cannot write a task is not a failure. It is a
            # hospital we can read and not ask, which the Console already says.
            return None

        # The hospital's own reference for this patient, which the caller has
        # because the order carries it. OpenEMR refuses a Task whose `for`
        # does not resolve — "Task.for must reference a Patient on this
        # server" — and our internal id means nothing to it.
        task = prioritise_task(
            patient_ref=patient_ref,
            patient_display=patient.name or patient_id,
            order_ref=order_ref,
            what=what,
            needed_by=needed_by.isoformat(),
            because=because,
            requested_at=datetime.now(UTC),
        )
        try:
            ref = await asyncio.to_thread(system.create_task, task)
        except Exception as exc:  # noqa: BLE001 — any failure is the same answer
            logger.warning("could not ask %s to prioritise %s: %s", patient.hospital_id, what, exc)
            return None

        self._bump("escalations")
        self.bus.publish(
            EventKind.ESCALATION_WRITTEN,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=(
                f"Asked {patient.hospital_id} to bring {what} forward for "
                f"{patient_id} — their travel cannot be changed"
            ),
            task_ref=ref,
            order_ref=order_ref,
        )
        return ref

    # ---------------- a person agreeing with a reading ----------------

    def confirm_request(
        self, patient_id: str, request_id: str, by: str
    ) -> PatientRequest | None:
        """A navigator agrees a reading is what the family meant.

        Returns None for an unknown request, and for one already decided —
        a second confirmation is not an error worth a 500, but it must not
        silently overwrite who decided or when.
        """
        found = self._pending_request(patient_id, request_id)
        if found is None:
            return None
        index, request = found
        confirmed = request.model_copy(
            update={"confirmed_by": by, "confirmed_at": datetime.now(UTC)}
        )
        self.requests[patient_id][index] = confirmed
        self._bump("requests_confirmed")
        self.bus.publish(
            EventKind.REQUEST_CONFIRMED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{by} agreed that {patient_id} {confirmed.summary()}",
            request=confirmed.model_dump(mode="json"),
        )
        return confirmed

    async def replan_for_request(self, patient_id: str, request: PatientRequest) -> Search | None:
        """Search for dates that fit what the family actually said.

        This is the step that was missing. `extract_request` read her sentence,
        a navigator agreed with the reading, and then nothing used it:
        `candidates_for_request` — which exists, is tested, and knows how to
        try what was asked for, the edge of the hospital's tolerance, and
        *earlier* — had no callers at all outside its own tests. So a family
        could state a constraint, have it confirmed, and get a re-plan that had
        never heard of it.

        Two things come out of this, for two audiences. The navigator gets
        options that respect her constraint, to approve or not. The Console and
        the reasoning log get the whole search — every date tried and the rule
        that killed it — which is the only way to answer "what else did you
        look at?" after the fact.

        Returns the search, or None when there was nothing to search: no
        patient, no target step, or a reading with no constraint in it. Those
        are ordinary outcomes and not errors — a family saying "thank you"
        should not produce a plan.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None
        if not request.actionable:
            return None

        steps = self.world.steps_for(patient_id)
        target_kind = request.step_kind or self.world.target_kind_for(patient_id)
        if target_kind is None:
            return None
        cycle = self.world.maintenance_cycles.get(patient_id)

        # Without the hospital's own rules there is no tolerance to search
        # inside, and no slot calendar to land on. Searching anyway would mean
        # inventing both, and a date this system made up is the one thing it
        # must never offer a family. So it says so and stops: the reading is
        # still confirmed and still on the record, and a navigator still sees
        # her words — they just do not become dates until the hospital's rules
        # are saved.
        policy = self.planner.rules_for(patient.hospital_id)
        if policy is None:
            self.bus.publish(
                EventKind.PLAN_SEARCHED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=(
                    f"{patient_id}: cannot search for dates — "
                    f"{patient.hospital_id} has no saved rules, so there is no "
                    "tolerance to search inside"
                ),
            )
            return None

        round_trip = await asyncio.to_thread(self.journey_hours, patient)

        search = Search(patient_id=patient_id, step_kind=target_kind.value)
        started = perf_counter()
        async with self.working(
            "Looking for dates that fit what the family said",
            patient_id=patient_id,
            detail=request.summary(),
        ):
            candidates = await asyncio.to_thread(
                options_module.candidates_for_request,
                patient,
                steps,
                request,
                target_kind,
                self.planner.graph_for(patient),
                self.planner.predictor,
                self.world.today,
                policy,
                disruptions=tuple(self.world.open_disruptions()),
                # A leave the hospital published never becomes a `Disruption`
                # — the connector asks the family about it and stops there —
                # so `open_disruptions()` does not contain it and the calendar
                # cannot refuse those days. Without this the planner offered a
                # family the very day their clinician was away, which is the
                # one answer the whole re-plan exists to avoid.
                days_away=frozenset(
                    day
                    for sync in self.hospital_syncs.values()
                    for day in getattr(sync, "away_days", ())
                ),
                cycle=cycle,
                round_trip_hours=round_trip,
                means=self.means_for(patient_id),
                search=search,
            )
        elapsed = (perf_counter() - started) * 1000

        self.searches[patient_id] = search
        self.bus.publish(
            EventKind.PLAN_SEARCHED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{patient_id}: {search.summary()}",
            duration_ms=elapsed,
            search=search.to_json(),
        )

        if candidates:
            async with self._lock:
                # Keyed to the request rather than a disruption, because a
                # family's own constraint is not a disruption — nothing at the
                # hospital went wrong. `approve_option` already tolerates an
                # id with no disruption behind it, and skips the resolution
                # step rather than inventing one.
                self.options[patient_id] = OptionSet(
                    patient_id=patient_id,
                    disruption_id=f"request:{request.id}",
                    options=candidates,
                    created_at=datetime.now(UTC),
                )
                self.world.pending_approval[patient_id] = f"request:{request.id}"

            # Put the best of them to the family, with what it would cost.
            #
            # A navigator still approves; this is not the family booking
            # anything. It is the difference between a system that decides and
            # then informs, and one that offers and then listens — and the
            # reply, if it is "no, after the 15th", is the next constraint.
            best = candidates[0]
            if best.target_on is not None:
                await self.propose_to_family(
                    patient_id,
                    on_day=best.target_on,
                    cost=self.cost_of_visit(
                        patient_id, people=1 + (request.travel.companions or 0)
                    ),
                    disruption_id=f"request:{request.id}",
                )
        return search

    def reject_request(
        self, patient_id: str, request_id: str, by: str, reason: str
    ) -> PatientRequest | None:
        """A navigator says the reading was wrong, with the correction.

        Recorded rather than deleted. A rejected reading is the most useful
        thing in this loop — it is the only evidence that the extractor got
        something wrong — and throwing it away would leave no way to tell a
        model that mishears dates from one that never ran.
        """
        found = self._pending_request(patient_id, request_id)
        if found is None:
            return None
        index, request = found
        rejected = request.model_copy(
            update={"rejected_reason": reason, "confirmed_by": None}
        )
        self.requests[patient_id][index] = rejected
        self._bump("requests_rejected")
        self.bus.publish(
            EventKind.REQUEST_REJECTED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"{by} read {patient_id}'s message differently: {reason[:120]}",
            request=rejected.model_dump(mode="json"),
        )
        return rejected

    def _pending_request(
        self, patient_id: str, request_id: str
    ) -> tuple[int, PatientRequest] | None:
        for index, request in enumerate(self.requests.get(patient_id, [])):
            if request.id != request_id:
                continue
            if request.confirmed_by is not None or request.rejected_reason is not None:
                return None
            return index, request
        return None

    # ---------------- asking a family, and reading the answer ----------------

    async def ask_family(
        self,
        patient_id: str,
        *,
        reason: AskReason,
        topics: tuple[AskTopic, ...],
        about_day: date,
        disruption_id: str | None = None,
    ) -> OpenQuestion | None:
        """Ask one question and remember having asked it.

        Returns None rather than raising when the question cannot be asked
        safely — an unknown patient, or text the guard refuses. A question that
        did not go out must not be recorded as open, or the next thing the
        family says would be read as an answer to it.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None

        text = compose_question(
            reason=reason, topics=topics, language=patient.language, on_day=about_day
        )
        # The same date the template was given is the only one it may contain.
        # A template that grew a second date is caught here rather than sent.
        verdict = guard.check_question(text, dates_given=(about_day,))
        if not verdict.allowed:
            logger.error(
                "refusing to ask %s: %s %s", patient_id, verdict.reason, verdict.triggers
            )
            self.bus.publish(
                EventKind.GUARD_BLOCKED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Guard held a question to {patient_id}: {verdict.reason}",
                triggers=list(verdict.triggers),
            )
            return None

        question = self.conversation.open_question(
            patient_id=patient_id,
            reason=reason,
            topics=topics,
            asked_text=text,
            language=patient.language,
            about_day=about_day.isoformat(),
            disruption_id=disruption_id,
        )
        # Into the family's own thread, not only into the event log. A question
        # that exists only in `questions/waiting` is a question the family
        # cannot see: both apps read the thread, and a family who was never
        # shown what they were asked will never answer it.
        self._record_outbound(
            patient_id,
            kind="question",
            body=text,
            language=patient.language.value,
            channel=Channel.WHATSAPP.value,
        )
        self._bump("questions_asked")
        self.bus.publish(
            EventKind.QUESTION_ASKED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"Asked {patient_id} about {', '.join(t.value for t in topics)}",
            question=question.model_dump(mode="json"),
        )
        return question

    def cost_of_visit(self, patient_id: str, *, people: int = 1) -> JourneyCost | None:
        """What coming in for one visit would likely cost this family.

        Built from what we actually hold about them: how far they live from
        the hospital, how long the round trip takes, how many are coming, and
        whether they have ever told us a figure themselves. A family who has
        told us one gets their own number back; everybody else gets published
        rates with the publication named.

        None when there is nothing honest to say — an unknown family, or a
        journey we hold no rate for. A missing cost line is better than a
        filled-in one.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None

        said = self.stated_fare_for(patient_id)
        costed = cost_of_journey(
            load_rates(),
            km=patient.home_distance_km,
            people=max(1, people),
            round_trip_hours=self.journey_hours(patient),
            # The bed we would actually offer them, not the dearest one. The
            # ordering families are promised in "Near you" has to hold here
            # too, or the figure contradicts the recommendation.
            stay_kind=PlaceKind.DHARAMSHALA,
            stated_paise=said[0] if said else None,
            stated_in=said[1] if said else "",
            as_of=self.world.today,
        )
        return costed if costed.items else None

    def stated_fare_for(self, patient_id: str) -> tuple[int, str] | None:
        """The last figure this family gave us for their journey, in paise.

        Theirs beats ours everywhere it exists — see `money/__init__.py`. The
        sentence comes back with it so a screen can show whose number it is.
        """
        for request in reversed(self.requests.get(patient_id, ())):
            rupees = getattr(request.travel, "stated_cost_inr", None)
            if rupees:
                return int(rupees) * 100, getattr(request.travel, "stated_in", "") or ""
        return None

    async def propose_to_family(
        self,
        patient_id: str,
        *,
        on_day: date,
        cost: JourneyCost | None = None,
        disruption_id: str | None = None,
    ) -> OpenQuestion | None:
        """Put a worked-out day to a family, with what it would likely cost.

        The turn that makes this a conversation rather than an interrogation.
        `ask_family` asks and waits; this offers something and asks whether it
        suits — so the reply is either agreement or the constraint that makes a
        better plan, and either way the loop continues.

        Nothing here commits anything. A family agreeing does not book a slot:
        a navigator still approves, and `approve_option` still writes to the
        hospital before anybody is told. What agreement changes is that the
        navigator is approving something the family has already said yes to,
        rather than deciding on their behalf and telling them afterwards.

        Returns None when it cannot be said safely, for the same reasons
        `ask_family` does — an unknown family, or text the guard refuses.
        """
        patient = self.world.patient(patient_id)
        if patient is None:
            return None

        # Their own figure beats our arithmetic, always. A family who told us
        # what the journey costs them should see that number, not a better-
        # researched one that contradicts them.
        rendered, theirs = "", False
        if cost is not None and cost.items:
            rendered, theirs = cost.rupees(), cost.any_stated

        text = compose_proposal(
            language=patient.language,
            on_day=on_day,
            cost=rendered,
            cost_is_theirs=theirs,
        )
        verdict = guard.check_question(text, dates_given=(on_day,))
        if not verdict.allowed:
            logger.error(
                "refusing to propose to %s: %s %s",
                patient_id, verdict.reason, verdict.triggers,
            )
            self.bus.publish(
                EventKind.GUARD_BLOCKED,
                self.world.today.isoformat(),
                patient_id=patient_id,
                summary=f"Guard held a proposal to {patient_id}: {verdict.reason}",
                triggers=list(verdict.triggers),
            )
            return None

        question = self.conversation.open_question(
            patient_id=patient_id,
            reason=AskReason.PLAN_PROPOSED,
            topics=(AskTopic.AGREEMENT,),
            asked_text=text,
            language=patient.language,
            about_day=on_day.isoformat(),
            disruption_id=disruption_id,
        )
        self._record_outbound(
            patient_id,
            kind="proposal",
            body=text,
            language=patient.language.value,
            channel=Channel.WHATSAPP.value,
        )
        self._bump("proposals_sent")
        self.bus.publish(
            EventKind.QUESTION_ASKED,
            self.world.today.isoformat(),
            patient_id=patient_id,
            summary=f"Put {on_day:%d %b} to {patient_id}"
            + (f", about {rendered}" if rendered else ""),
            question=question.model_dump(mode="json"),
            cost=cost.to_json() if cost is not None else None,
        )
        return question

    async def _read_answer(self, patient: Patient, record: InboundRecord) -> bool:
        """Try to read this message as the answer to an open question.

        Returns whether it was one. False covers every ordinary case — no
        question open, the question went stale, the extractor is not
        configured, or the reply simply did not answer what was asked — and in
        all of them the caller carries on with its normal handling.
        """
        question = self.conversation.pending(patient.id)
        if question is None or self.actors is None:
            return False

        started = perf_counter()
        reading = await self.actors.extract_request(
            patient,
            record.text,
            self.world.today,
            known_steps=tuple(step.kind.value for step in self.world.steps_for(patient.id)),
        )
        duration = (perf_counter() - started) * 1000
        self._bump("actor_calls")
        if reading is None:
            return False

        matched = self.conversation.record_answer(patient.id, reading, record.text)
        if matched is None:
            return False
        answered, answer = matched

        if answer.answers_nothing:
            # Not an answer. The question stays open and the message is handled
            # as whatever it actually is. Saying so in the log matters: a reply
            # that answered nothing looks identical to a reply never sent.
            self.bus.publish(
                EventKind.INBOUND_RECEIVED,
                self.world.today.isoformat(),
                patient_id=patient.id,
                summary=(
                    f"{patient.id} wrote in but did not answer "
                    f"{', '.join(t.value for t in question.topics)}; still waiting"
                ),
                duration_ms=duration,
            )
            return False

        self.bus.publish(
            EventKind.QUESTION_ANSWERED,
            self.world.today.isoformat(),
            patient_id=patient.id,
            summary=f"{patient.id} answered with {', '.join(answer.filled)}",
            duration_ms=duration,
            question=answered.model_dump(mode="json"),
            filled=list(answer.filled),
        )
        await self._raise_request(patient, record, reading, answer)
        return True

    async def _raise_request(
        self,
        patient: Patient,
        record: InboundRecord,
        reading: dict,
        answer,
    ) -> PatientRequest:
        """Record what the family asked for, for a navigator to agree with.

        `confirmed_by` is deliberately left empty. Mishearing "after the 20th"
        as "on the 20th" costs a family a journey, and the cost of asking a
        navigator is one tap — see `domain/requests.py`.
        """
        step_kind = reading.get("step_kind")
        queue = self.requests.setdefault(patient.id, [])
        request = PatientRequest(
            id=f"req-{patient.id}-{len(queue)}",
            patient_id=patient.id,
            raw_text=record.text,
            gloss=record.gloss,
            intent=_as_intent(reading.get("intent")),
            step_kind=_as_step_kind(step_kind),
            constraint=answer.constraint,
            travel=answer.travel,
            confidence=str(reading.get("confidence") or "low"),
        )
        queue.append(request)
        self._bump("requests_raised")
        self.bus.publish(
            EventKind.REQUEST_RAISED,
            self.world.today.isoformat(),
            patient_id=patient.id,
            summary=f"{patient.id} {request.summary()}",
            request=request.model_dump(mode="json"),
        )
        return request

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
        if self.world.real:
            # The score compares plans with planted ground truth. Real records
            # have none, and a number that looks like a result would be a lie.
            return
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

    def _record_outbound(
        self,
        patient_id: str,
        *,
        kind: str,
        body: str,
        language: str,
        channel: str,
        held: bool = False,
        reason: str | None = None,
        rendered_by: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Keep what was sent, so the family's own screen can show it back."""
        if kind == "plan":
            last = next((r for r in reversed(self.outbound) if r["patient_id"] == patient_id), None)
            if (
                last is not None
                and last["kind"] == "plan"
                and (last["body"], last["language"], last["held"]) == (body, language, held)
            ):
                return  # the same words again, after a restart say, are not news
        row = {
            "id": f"out-{patient_id}-{len(self.outbound)}",
            "patient_id": patient_id,
            "kind": kind,
            "body": body,
            "language": language,
            "channel": channel,
            "held": held,
            "reason": reason,
            "rendered_by": rendered_by,
            "duration_ms": duration_ms,
            "sim_date": self.world.today.isoformat(),
            "sent_at": datetime.now(UTC).isoformat(),
        }
        self.outbound.append(row)
        if self.world.store is not None:
            self.world.store.add_family_message(row)

    def forget_thread(self, patient_id: str) -> None:
        """Start a family's conversation again. Only the demo reset calls this."""
        self.outbound[:] = [row for row in self.outbound if row["patient_id"] != patient_id]
        self.inbound[:] = [record for record in self.inbound if record.patient_id != patient_id]
        if self.world.store is not None:
            self.world.store.clear_family_messages(patient_id)

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
