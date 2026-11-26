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
from datetime import date, timedelta
from pathlib import Path

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
from ..ports.hospital import HospitalSystem
from ..ports.identity import IdentityProvider
from ..ports.language import LanguageLayer
from ..ports.ledger import EvidenceLedger
from ..ports.onboarding import OnboardingStore
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
    #: A family's background, documents and admissions. Never read by the planner.
    onboarding: OnboardingStore | None = None
    #: Which system to ask about each hospital, keyed by hospital id. Called,
    #: not indexed: an unknown hospital gets the desk adapter rather than a
    #: KeyError, because "this hospital has no system" is an ordinary state.
    hospitals: HospitalSystems | None = None
    #: Where buses and trains go. None when no route service is set up.
    routes: object | None = None
    #: What is around a point. None when no map service is set up.
    places: object | None = None

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

    def families_for_email(self, email: str) -> tuple[tuple[str, str], ...]:
        return tuple(
            (patient.id, patient.name or "Family")
            for patient in self._world.patients()
            if patient.caregiver_email and patient.caregiver_email.lower() == email
        )


def _email_sender(settings: Settings):
    from ..adapters.identity import BrevoEmailSender, LogEmailSender

    if settings.brevo_api_key and settings.email_from:
        return BrevoEmailSender(
            settings.brevo_api_key, settings.email_from, settings.email_from_name
        )
    return LogEmailSender()


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
    fixed: dict[str, str] = {}
    fixed_email: dict[str, str] = {}
    if settings.demo_otp and settings.seed_demo:
        if settings.seed_demo_phone:
            fixed[settings.seed_demo_phone] = settings.demo_otp
        if settings.seed_demo_email:
            fixed_email[settings.seed_demo_email] = settings.demo_otp
        if fixed or fixed_email:
            logger.warning("the demo contact signs in with a fixed code; not for real families")
    identity = LocalIdentity(
        settings.records_url,
        secret=settings.auth_secret,
        phones=_WorldPhones(world),
        email_sender=_email_sender(settings),
        fixed_codes=fixed,
        fixed_email_codes=fixed_email,
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
    from .seed import seed_registry, top_up_entrances

    if settings.real_world:
        from ..adapters.records.sql import migrate
        from ..adapters.registry import SqlRegistryStore

        migrate(settings.records_url)
        store: RegistryStore = SqlRegistryStore(settings.records_url)
    else:
        from ..adapters.registry import MemoryRegistryStore

        store = MemoryRegistryStore()
    seed_registry(store, settings, demo=not settings.real_world)
    if settings.seed_demo or not settings.real_world:
        top_up_entrances(store)
        from .demo_directory import seed_directory

        seed_directory(store)
    return store


def _geocoder(runner):
    """A place name to (lat, lng), through the same cached geocoder the journeys use."""

    def geocode(place: str) -> tuple[float, float] | None:
        tools = runner.tools
        if tools is None:
            return None
        try:
            hit = tools.geo.geocode(place)
        except Exception:  # noqa: BLE001 - an unplaceable journey is UNKNOWN, not a crash
            logger.exception("could not geocode %r", place)
            return None
        return (hit.lat, hit.lon) if hit else None

    return geocode


def build_routes(settings: Settings, geocode=None):
    """The route planner the family's "how do I get there" reads, or None."""
    kind = settings.routes_provider.strip().lower()
    if kind == "google":
        if not settings.google_maps_api_key:
            logger.error("SAATHI_ROUTES_PROVIDER=google but SAATHI_GOOGLE_MAPS_API_KEY is not set")
            return None
        from ..adapters.routes import GoogleRoutes

        return GoogleRoutes(settings.google_maps_api_key)
    if kind == "osrm":
        # No key, and the same service `tools/geo.py` already asks for every
        # journey time on every plan. Driving only — it has no timetables, and
        # says so by offering nothing for transit rather than dressing a car
        # route as a bus.
        from ..adapters.routes.osrm import DEFAULT_ROUTER, OsrmRoutes

        return OsrmRoutes(settings.router_url or DEFAULT_ROUTER, geocode=geocode)
    if kind == "demo":
        from ..adapters.routes import DemoRoutes

        return DemoRoutes()
    return None


def build_places(settings: Settings):
    """The place finder "near you" reads, or None."""
    kind = settings.places_provider.strip().lower()
    if kind == "google":
        if not settings.google_maps_api_key:
            logger.error("SAATHI_PLACES_PROVIDER=google but SAATHI_GOOGLE_MAPS_API_KEY is not set")
            return None
        from ..adapters.places import GooglePlaces

        return GooglePlaces(settings.google_maps_api_key)
    if kind == "local":
        # Our own table, loaded monthly from OpenStreetMap. The public
        # Overpass servers answer in thirty to forty seconds when they answer
        # at all, which a family tapping "Near you" experiences as the
        # feature being broken. Same data, read in milliseconds, and it
        # cannot be taken away by somebody else's server being busy.
        from ..adapters.places.sql import SqlPlaces

        # The records database, not the app one: that is where migration
        # 0015 creates the table and where the loader writes.
        return SqlPlaces(settings.records_url)
    if kind == "osm":
        from ..adapters.places import OsmPlaces

        return OsmPlaces(settings.overpass_url)
    if kind == "demo":
        from ..adapters.places import DemoPlaces

        return DemoPlaces()
    return None


def build_networks(settings: Settings) -> dict:
    """The open networks LIVE organisations are reached through, by id.

    `ID=demo` is a seller inside this process; `ID=beckn|gateway|registry|bap_id|
    bap_uri|unique_key_id|signing_key_path|city` is a real network. A malformed
    entry is logged and skipped, like a hospital system: one typo must not stop
    the hospital's other work.
    """
    networks: dict = {}
    for entry in settings.network_providers:
        network_id, _, spec = entry.partition("=")
        parts = [p.strip() for p in spec.split("|")]
        kind = parts[0].lower() if parts else ""
        try:
            if kind == "demo":
                from ..adapters.beckn.demo import DemoNetwork

                networks[network_id.strip()] = DemoNetwork()
            elif kind == "beckn" and len(parts) == 8:
                import httpx

                from ..adapters.beckn import BecknProvider, RegistryLookup, SubscriberRegistry
                from ..adapters.beckn.signing import load_private_key

                _, gateway, registry_url, bap_id, bap_uri, key_id, key_path, city = parts
                lookup = RegistryLookup(base_url=registry_url, client=httpx.AsyncClient())
                networks[network_id.strip()] = BecknProvider(
                    bap_id=bap_id,
                    bap_uri=bap_uri,
                    unique_key_id=key_id,
                    private_key=load_private_key(key_path),
                    registry=SubscriberRegistry(lookup),
                    gateway_url=gateway,
                    city_code=city,
                )
            else:
                logger.error("SAATHI_NETWORK_PROVIDERS entry not understood: %r", network_id)
        except Exception:  # noqa: BLE001
            logger.exception("could not set up network %r", network_id)
    return networks


def build_gateways(settings: Settings) -> dict:
    """Vendors' own payment gateways, by account id. Keys come from named env vars."""
    import os

    from ..live.payments import Gateway
    from ..ports.payments import MerchantAccount

    gateways: dict = {}
    for entry in settings.payment_accounts:
        account_id, _, spec = entry.partition("=")
        parts = [p.strip() for p in spec.split("|")]
        kind = parts[0].lower() if parts else ""
        account_id = account_id.strip()
        try:
            if kind == "fake":
                from ..adapters.payments import FakePayments

                secret = os.urandom(16).hex()
                gateways[account_id] = Gateway(
                    FakePayments(),
                    MerchantAccount("fake", f"fake_{account_id}", secret, secret),
                )
            elif kind in {"razorpay", "cashfree"} and len(parts) >= 4:
                values = [os.environ.get(name, "") for name in parts[1:4]]
                if not all(values):
                    logger.error("payment account %r: its key variables are not set", account_id)
                    continue
                if kind == "razorpay":
                    from ..adapters.payments import RazorpayPayments as Provider
                else:
                    from ..adapters.payments import CashfreePayments as Provider
                phone = os.environ.get(parts[4], "") if len(parts) > 4 else ""
                gateways[account_id] = Gateway(
                    Provider(), MerchantAccount(kind, values[0], values[1], values[2], phone)
                )
            else:
                logger.error("SAATHI_PAYMENT_ACCOUNTS entry not understood: %r", account_id)
        except Exception:  # noqa: BLE001
            logger.exception("could not set up payment account %r", account_id)
    return gateways


def build_spends(settings: Settings):
    """Where a family's spends are kept: the database for real, memory for the demo."""
    if settings.real_world:
        from ..adapters.spends import SqlSpendStore

        return SqlSpendStore(settings.records_url)
    from ..adapters.spends import MemorySpendStore

    return MemorySpendStore()


def build_onboarding(settings: Settings) -> OnboardingStore:
    """Where a family's onboarding details are kept: the database for real, memory for the demo."""
    if settings.real_world:
        from ..adapters.onboarding import SqlOnboardingStore

        return SqlOnboardingStore(settings.records_url)
    from ..adapters.onboarding import MemoryOnboardingStore

    return MemoryOnboardingStore()


class HospitalSystems:
    """Which system to ask about a given hospital.

    The same shape as `HospitalRules` above, for the same reason: everything
    that varies per hospital should be reachable by one cached call keyed on
    `hospital_id`, so the planner and the connector take a callable rather
    than a dictionary they might index with the wrong key.

    Never returns None. A hospital with nothing configured gets `DeskHospital`,
    whose `live` is False and which is therefore never polled — "the desks are
    the feed" is the pilot's stated starting point, not a degraded mode.
    """

    def __init__(self, systems: dict[str, HospitalSystem]) -> None:
        self._systems = systems
        self._desks: HospitalSystem | None = None

    def __call__(self, hospital_id: str) -> HospitalSystem:
        found = self._systems.get(hospital_id)
        if found is not None:
            return found
        if self._desks is None:
            from ..adapters.hospital import DeskHospital

            self._desks = DeskHospital()
        return self._desks

    def all(self) -> dict[str, HospitalSystem]:
        """Every hospital that actually has a system, for the connector to poll."""
        return dict(self._systems)

    def close(self) -> None:
        for system in self._systems.values():
            closer = getattr(system, "close", None)
            if callable(closer):
                closer()


def _parse_system(entry: str) -> tuple[str, HospitalSystem] | None:
    """`TMH-MUM=bahmni|https://…|user|pass` -> one adapter, or None if unusable.

    Refuses rather than guesses. A typo in a hospital id would otherwise
    attach a real hospital's system to a hospital that does not exist, and the
    only symptom would be a board that never changes.
    """
    hospital_id, _, spec = entry.partition("=")
    hospital_id = hospital_id.strip()
    parts = [p.strip() for p in spec.split("|")]
    kind = parts[0].lower() if parts else ""
    base_url = parts[1] if len(parts) > 1 else ""

    if not hospital_id or not kind or not base_url:
        logger.warning("ignoring malformed hospital system entry %r", entry)
        return None

    if kind == "bahmni":
        from ..adapters.hospital import BahmniHospital

        if len(parts) < 4:
            logger.warning("bahmni entry for %s has no username/password; ignoring", hospital_id)
            return None
        return hospital_id, BahmniHospital(
            base_url=base_url, username=parts[2], password=parts[3]
        )

    if kind == "fhir":
        from ..adapters.hospital import FhirHospital

        return hospital_id, FhirHospital(
            base_url=base_url,
            username=parts[2] if len(parts) > 2 and parts[2] else None,
            password=parts[3] if len(parts) > 3 and parts[3] else None,
        )

    if kind == "openemr":
        # `HOSP=openemr|<base>|<client id>|<key id>|<pem path>`
        # The key never appears in the environment, only its path: a private
        # key pasted into a deployment variable ends up in logs, dashboards
        # and shoulder-surfing range.
        from ..adapters.hospital._smart import SYSTEM_SCOPES, SmartTokens
        from ..adapters.hospital.openemr import OpenEMRHospital

        if len(parts) < 5:
            logger.warning(
                "openemr entry for %s needs base|client_id|key_id|key_path; ignoring",
                hospital_id,
            )
            return None
        try:
            pem = Path(parts[4]).read_text()
        except OSError as exc:
            logger.warning("cannot read the signing key for %s: %s", hospital_id, exc)
            return None

        root = base_url.rstrip("/")
        return hospital_id, OpenEMRHospital(
            base_url=f"{root}/apis/default/fhir",
            token=SmartTokens(
                token_url=f"{root}/oauth2/default/token",
                client_id=parts[2],
                key_id=parts[3],
                private_key_pem=pem,
                scope=SYSTEM_SCOPES,
            ),
            # OpenEMR's Appointment search has no `_include`; see the adapter.
            supports_include=False,
            # Optional, and a missing one is not an error: without it the
            # Console reports arrival and claims no delay, which is what it
            # should do when nothing can tell it one. See `_clinic_database`.
            flow=_clinic_database(hospital_id, parts[5:]),
        )

    logger.warning("unknown hospital system kind %r for %s; ignoring", kind, hospital_id)
    return None


def _clinic_database(hospital_id: str, parts: list[str]) -> object | None:
    """`host:port/db|user|pass` -> a read-only handle, or None.

    Appended to the `openemr` entry rather than carried in settings of its
    own, so everything about one hospital stays on one line. Three parts are
    required together: a half-configured database is a typo, and attaching one
    would produce a connector that times out every poll instead of simply not
    reading arrival times.
    """
    if not parts or not any(part.strip() for part in parts):
        return None
    if len(parts) < 3 or not all(part.strip() for part in parts[:3]):
        logger.warning(
            "%s has an incomplete database spec; expected host:port/db|user|pass. "
            "Continuing over FHIR only — arrival times will not be read",
            hospital_id,
        )
        return None

    from ..adapters.hospital.openemr_db import OpenEMRDatabase

    location, user, password = parts[0], parts[1], parts[2]
    host, _, rest = location.partition(":")
    port_text, _, database = rest.partition("/")
    if not database:
        # `host/db` with no port, which is the commoner way to write it.
        host, _, database = location.partition("/")
        port_text = ""
    try:
        port = int(port_text) if port_text else 3306
    except ValueError:
        logger.warning("%s has a non-numeric database port %r; ignoring", hospital_id, port_text)
        return None
    if not host or not database:
        logger.warning("%s has no readable database host/name in %r", hospital_id, location)
        return None

    return OpenEMRDatabase(
        host=host, port=port, database=database, user=user, password=password
    )


def build_hospitals(settings: Settings) -> HospitalSystems:
    """Every connected hospital system, keyed by hospital id.

    Two sources, in order. `hospital_systems` is the real one and may name any
    number of hospitals. The older single `bahmni_*` block is kept as a
    shorthand for the common one-hospital case and is attached to the first
    configured hospital, so an existing deployment keeps working without
    editing its environment.
    """
    systems: dict[str, HospitalSystem] = {}

    for entry in settings.hospital_systems:
        parsed = _parse_system(entry)
        if parsed is not None:
            hospital_id, system = parsed
            systems[hospital_id] = system
            logger.info("%s answers over %s", hospital_id, system.name)

    if settings.bahmni_enabled:
        from ..adapters.hospital import BahmniHospital

        default_id = (
            settings.hospital_places[0].partition("=")[0].strip()
            if settings.hospital_places
            else ""
        )
        if default_id and default_id not in systems:
            systems[default_id] = BahmniHospital(
                base_url=settings.bahmni_base_url or "",
                username=settings.bahmni_username or "",
                password=settings.bahmni_password or "",
            )
            logger.info("%s answers over bahmni (from the single-hospital settings)", default_id)

    if not systems:
        logger.info("no hospital system connected: the desks are the feed")
    return HospitalSystems(systems)


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
            from .demo_records import apply_demo_contacts, seed_demo_records, seed_showcase

            today = SystemClock(settings.hospital_timezone).today()
            seed_demo_records(store, today, settings)
            seed_showcase(store, today)
            apply_demo_contacts(store, settings)
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
    hospitals = build_hospitals(settings)
    runner = LiveRunner(
        world=world,
        bus=bus,
        planner=planner,
        ledger=ledger,
        alerts=alerts,
        actors=build_actors(settings, world),
        tools=toolbox,
        hospitals=hospitals,
        hospital_poll_seconds=settings.bahmni_poll_seconds,
        hospital_window_days=settings.bahmni_window_days,
        hospital_timezone=settings.hospital_timezone,
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
    onboarding = build_onboarding(settings)
    if settings.seed_demo or not settings.real_world:
        from .demo_profiles import seed_demo_onboarding

        seed_demo_onboarding(onboarding, tuple(world.patients()), registry)
    rules = HospitalRules(registry)
    planner.rules_for = rules
    if settings.real_world:
        from ..live.partners import PartnerDesk

        runner.partners = PartnerDesk(
            world=world,
            registry=registry,
            onboarding=onboarding,
            graph_for=planner.graph_for,
            rules_for=rules,
            journey_hours=runner.journey_hours,
            auto=settings.partners_on,
            answer_within=timedelta(minutes=settings.partner_answer_minutes),
        )
        if settings.partners_on:
            logger.info("the network answers: journeys ask the directory's organisations")

    from ..live.kharcha import KharchaDesk
    from ..live.network import NetworkDesk
    from ..live.payments import PaymentsDesk

    runner.kharcha = KharchaDesk(
        store=build_spends(settings),
        world=world,
        ledger=ledger,
        registry=registry,
        onboarding=onboarding,
        alerts=runner.alerts,
    )
    networks = build_networks(settings)
    if networks:
        runner.network = NetworkDesk(
            providers=networks,
            world=world,
            registry=registry,
            kharcha=runner.kharcha,
            geocode=_geocoder(runner),
        )
        logger.info("open networks: %s", ", ".join(sorted(networks)))
    gateways = build_gateways(settings)
    if gateways:
        runner.payments = PaymentsDesk(gateways=gateways, kharcha=runner.kharcha, registry=registry)
        logger.info("vendor gateways: %s", ", ".join(sorted(gateways)))

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
        onboarding=onboarding,
        hospitals=hospitals,
        routes=build_routes(settings, geocode=_geocoder(runner)),
        places=build_places(settings),
    )
