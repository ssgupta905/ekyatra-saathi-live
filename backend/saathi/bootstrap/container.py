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
from ..consent.registry import ConsentRegistry
from ..domain.enums import Role
from ..domain.policy import HospitalPolicy
from ..graph.dependencies import InMemoryDependencyGraph
from ..language.claude import ClaudeLanguageLayer
from ..ledger.evidence import InMemoryEvidenceLedger
from ..live.events import EventBus
from ..live.runner import LiveRunner
from ..live.world import LiveWorld
from ..planner.graph import VisitPlanner
from ..ports.clock import Clock
from ..ports.identity import IdentityProvider
from ..ports.language import LanguageLayer
from ..ports.ledger import EvidenceLedger
from ..ports.registry import RegistryStore
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
    #: None when login is off (the demo). Every access rule treats that as "open".
    identity: IdentityProvider | None = None
    #: Hospitals, centres, clinicians and each hospital's rules.
    registry: RegistryStore | None = None
    #: The planner's view of each hospital's saved rules; cleared when they change.
    rules: HospitalRules | None = None
    #: Who has agreed to share what. Kept across restarts in the real world.
    consent: ConsentRegistry | None = None

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


class _WorldPhones:
    """Which families a phone number is on, read from the live records."""

    def __init__(self, world: LiveWorld) -> None:
        self._world = world

    def families_for(self, phone: str) -> tuple[tuple[str, str], ...]:
        from ..adapters.identity.local import digits

        found: list[tuple[str, str]] = []
        for patient in self._world.patients():
            if digits(patient.caregiver_phone) == phone:
                greeting = next(
                    (m.name for m in patient.family_members if digits(m.phone) == phone),
                    patient.name or "Family",
                )
                found.append((patient.id, greeting))
            else:
                member = next((m for m in patient.family_members if digits(m.phone) == phone), None)
                if member is not None:
                    found.append((patient.id, member.name))
        return tuple(found)


def build_identity(settings: Settings, world: LiveWorld) -> IdentityProvider | None:
    """Local accounts, or an organisation's sign-in. None when login is off."""
    if not settings.auth_on:
        return None
    if settings.identity_provider == "oidc":
        from ..adapters.identity.oidc import OidcIdentity

        return OidcIdentity()
    from ..adapters.identity import LocalIdentity
    from ..adapters.records.sql import migrate

    migrate(settings.records_url)
    if settings.auth_secret.startswith("dev-only"):
        logger.warning("signing tokens with the built-in dev secret; set SAATHI_AUTH_SECRET")
    fixed = {}
    if settings.demo_otp and settings.seed_demo and settings.seed_demo_phone:
        fixed[settings.seed_demo_phone] = settings.demo_otp
        logger.warning("the demo phone signs in with a fixed code; not for real families")
    identity = LocalIdentity(
        settings.records_url,
        secret=settings.auth_secret,
        phones=_WorldPhones(world),
        fixed_codes=fixed,
    )
    _ensure_first_admin(identity, settings)
    return identity


def _ensure_first_admin(identity, settings: Settings) -> None:
    """Create the administrator named in configuration, once.

    A host with no shell cannot run `saathi.cli.users`. Existing accounts are
    left alone, so a password changed in the console survives a restart.
    """
    if not (settings.admin_username and settings.admin_password):
        return
    if any(u["username"] == settings.admin_username.lower() for u in identity.list_users()):
        return
    identity.add_user(
        settings.admin_username, settings.admin_username, Role.ADMIN, settings.admin_password
    )
    logger.info("created the first administrator %r from configuration", settings.admin_username)


class HospitalRules:
    """Each hospital's saved rules, as the planner reads them.

    Read on every plan, so cached; `invalidate` is called whenever an
    administrator saves a new version. A hospital with no saved rules returns
    None, and the planner then behaves exactly as it did before rules existed.
    A stored version that no longer validates is ignored rather than allowed to
    stop planning, and says so in the log.
    """

    def __init__(self, registry: RegistryStore) -> None:
        self._registry = registry
        self._cache: dict[str, HospitalPolicy | None] = {}

    def __call__(self, hospital_id: str) -> HospitalPolicy | None:
        if hospital_id not in self._cache:
            stored = self._registry.policy(hospital_id)
            policy = None
            if stored is not None:
                try:
                    policy = HospitalPolicy.model_validate(stored[0])
                except ValueError:
                    logger.exception("saved rules for %s do not validate; ignoring", hospital_id)
            self._cache[hospital_id] = policy
        return self._cache[hospital_id]

    def version(self, hospital_id: str) -> int | None:
        stored = self._registry.policy(hospital_id)
        return stored[1] if stored else None

    def invalidate(self) -> None:
        self._cache.clear()


def build_registry(settings: Settings) -> RegistryStore:
    """The network's reference data: in the database for real, in memory for the demo."""
    from .seed import seed_registry

    if settings.real_world:
        from ..adapters.records.sql import migrate
        from ..adapters.registry import SqlRegistryStore

        migrate(settings.records_url)
        store: RegistryStore = SqlRegistryStore(settings.records_url)
    else:
        from ..adapters.registry import MemoryRegistryStore

        store = MemoryRegistryStore()
    seed_registry(store, settings, demo=not settings.real_world)
    return store


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
        if settings.seed_demo:
            from .demo_records import seed_demo_records, seed_showcase

            today = SystemClock(settings.hospital_timezone).today()
            seed_demo_records(store, today, settings)
            seed_showcase(store, today)
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

    consent = (
        ConsentRegistry.restored(ledger, world.store)
        if world.store is not None
        else ConsentRegistry(ledger=ledger)
    )

    registry = build_registry(settings)
    rules = HospitalRules(registry)
    planner.rules_for = rules

    return Container(
        settings=settings,
        clock=world.clock.source,
        planner=planner,
        ledger=ledger,
        world=world,
        bus=bus,
        runner=runner,
        alerts=alerts,
        identity=build_identity(settings, world),
        registry=registry,
        rules=rules,
        consent=consent,
    )
