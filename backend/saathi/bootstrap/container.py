"""The composition root.

Built once at startup and handed to routes. Keeping it in one object makes the
degraded modes explicit: if no language credentials are present the planner
still runs and still decides, it just returns plans without rendered text; if
the live runner is never started, the world simply stands still and the console
behaves as a snapshot viewer.

This is the only module that chooses adapters. Everything else receives what it
needs through its constructor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from ..adapters.clock import SystemClock
from ..adapters.ledger import SqlEvidenceLedger
from ..adapters.records import SqlRecordStore
from ..config import Settings, get_settings
from ..graph.dependencies import InMemoryDependencyGraph
from ..language.claude import ClaudeLanguageLayer
from ..ledger.evidence import InMemoryEvidenceLedger
from ..live.events import EventBus
from ..live.runner import LiveRunner
from ..live.world import LiveWorld
from ..planner.graph import VisitPlanner
from ..ports.clock import Clock
from ..ports.language import LanguageLayer
from ..ports.ledger import EvidenceLedger
from ..readiness.conformal import ConformalReadinessPredictor, TurnaroundSample
from ..synthetic.generate import SyntheticCohort
from ..tools import build_toolbox

logger = logging.getLogger(__name__)


@dataclass
class Container:
    settings: Settings
    clock: Clock
    planner: VisitPlanner
    ledger: EvidenceLedger
    world: LiveWorld
    bus: EventBus
    runner: LiveRunner
    alerts: list = field(default_factory=list)

    @property
    def cohort(self) -> SyntheticCohort:
        return self.world.cohort

    def steps_for(self, patient_id: str):
        return self.world.steps_for(patient_id)

    def patient(self, patient_id: str):
        return self.world.patient(patient_id)


def build_language_layer(settings: Settings) -> LanguageLayer | None:
    """Pick the language backend. Groq first — the live demo needs its latency.

    Neither is required. With both unset the planner decides exactly as it does
    in CI and in `make demo`, and the console says the layer is off.
    """
    if settings.groq_api_key:
        from ..language.groq_layer import GroqLanguageLayer

        return GroqLanguageLayer(api_key=settings.groq_api_key, model=settings.groq_model)
    if settings.anthropic_api_key:
        return ClaudeLanguageLayer(model=settings.claude_model, api_key=settings.anthropic_api_key)
    logger.warning("no GROQ_API_KEY or ANTHROPIC_API_KEY — planner will decide but not compose")
    return None


def build_actors(settings: Settings, world: LiveWorld):
    """The Groq actors, or None. Every caller guards on None."""
    if not settings.groq_api_key:
        return None
    from ..live.actors import GroqActors

    return GroqActors(
        api_key=settings.groq_api_key,
        model=settings.groq_actor_model,
        world=world,
    )


def build_container(settings: Settings | None = None, today: date | None = None) -> Container:
    settings = settings or get_settings()

    predictor = ConformalReadinessPredictor(alpha=settings.conformal_alpha)
    if settings.real_world:
        # The real world is whatever the store holds, on the hospital's calendar.
        # Its forecast is calibrated only on releases it has actually seen: until
        # a queue has enough of them the planner says it does not know, which is
        # the true answer.
        store = SqlRecordStore(settings.records_url)
        world = LiveWorld.build_real(
            store,
            SystemClock(settings.hospital_timezone),
            tick_seconds=settings.real_tick_seconds,
        )
        predictor.fit(
            [TurnaroundSample(queue=o.queue, days=o.days) for o in store.load().turnaround]
        )
    else:
        world = LiveWorld.build(
            start=today or date.today(),
            seconds_per_day=settings.live_seconds_per_day,
            n_watched=settings.live_watched,
            auto_confirm_ticks=settings.live_auto_confirm_ticks,
            scripted=settings.live_scripted,
        )
        predictor.fit(world.cohort.turnaround)

    # The audit trail outlives the process in the real world; the demo's does not.
    ledger = (
        SqlEvidenceLedger(settings.records_url) if settings.real_world else InMemoryEvidenceLedger()
    )
    planner = VisitPlanner(
        dependency_graph=InMemoryDependencyGraph(),
        predictor=predictor,
        ledger=ledger,
        language_layer=build_language_layer(settings),
    )

    bus = EventBus()
    alerts: list = []
    toolbox = build_toolbox(settings)
    runner = LiveRunner(
        world=world,
        bus=bus,
        planner=planner,
        ledger=ledger,
        alerts=alerts,
        actors=build_actors(settings, world),
        tools=toolbox,
        inbound_every_seconds=settings.live_inbound_every_seconds,
    )
    # Close the loop the toolbox was built for: every fact it fetches becomes a
    # ledger row and an event with its measured latency. Without this the tools
    # work and nobody can see that they did.
    toolbox.on_result = runner.on_tool_result

    return Container(
        settings=settings,
        clock=world.clock.source,
        planner=planner,
        ledger=ledger,
        world=world,
        bus=bus,
        runner=runner,
        alerts=alerts,
    )
