"""Configuration, read from the environment.

Every external dependency is optional. With nothing configured, Saathi runs
fully in-process against synthetic data — which is what the prototype does and
what CI runs. Each integration turns on when its credentials appear.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SAATHI_", extra="ignore"
    )

    # --- runtime ---
    environment: str = "local"
    log_level: str = "INFO"
    #: Run as a demo: dev-only control endpoints are mounted and a simulator may
    #: drive the clock. Never allowed when `environment` is "production".
    sim_mode: bool = False
    #: "demo" is the simulated world: a synthetic cohort, a clock that runs fast,
    #: actors that write to the families. "real" is a hospital's own records,
    #: entered by people, on the real calendar, with nobody pretending to be a
    #: family. The switch changes what the world is made of and nothing else.
    world: Literal["demo", "real"] = "demo"
    #: The hospital's timezone. "Today" is the hospital's date, not the server's.
    hospital_timezone: str = "Asia/Kolkata"
    #: Where reference data lives. Empty means: the repo's `data/` when running
    #: from a checkout, otherwise `./data`. Always resolved to an absolute path.
    data_dir: str = ""

    #: Origins allowed to call the API cross-site. Only browsers need this: a
    #: native app is not bound by CORS. The defaults are the local dev ports of
    #: the staff apps, the family app's web build (Expo, 8081) and the demo stage.
    cors_origins: str = (
        "http://localhost:5173,http://localhost:5174,http://localhost:5175,"
        "http://localhost:5176,http://localhost:5180,http://localhost:5190,"
        "http://localhost:8081"
    )

    # --- who may do what ---
    #: "auto" turns login on in the real world and off in the demo, where the
    #: stage shows every role at once and a login screen would be in the way.
    auth: Literal["auto", "on", "off"] = "auto"
    identity_provider: Literal["local", "oidc"] = "local"
    #: Signs tokens. A fixed default keeps local sign-ins valid across a reload;
    #: production refuses to start without a real one.
    auth_secret: str = "dev-only-secret-change-me-before-any-real-use"

    # --- storage ---
    #: Where the real world's records live. A SQLAlchemy URL: moving to Postgres
    #: is changing this string (`postgresql+psycopg://user:pw@host/db`) and
    #: running `make migrate`. Unused in the demo world.
    records_url: str = "sqlite:///./saathi_records.db"
    #: The first administrator, created at startup when no account of that name
    #: exists. For a host with no shell (a free Render instance has none): set
    #: both as secrets. Never overwrites an account, so a password changed since
    #: is not reset by a restart.
    admin_username: str | None = None
    admin_password: str | None = None
    #: Load a small synthetic cohort into an *empty* real database, so a fresh
    #: deployment has families to look at. Never touches a database that already
    #: holds a family. `seed_demo_phone` makes the first family answer to that
    #: number, so someone can sign in as a caregiver.
    seed_demo: bool = False
    #: "simulated" answers on behalf of the directory's organisations so a journey
    #: moves by itself; "off" leaves every party to be recorded by a person. Left
    #: unset it follows `seed_demo`.
    partners: str | None = None
    #: How long an asked organisation has to answer before its silence reads as
    #: UNKNOWN. Six hours: long enough for a dharamshala clerk to see the job,
    #: short enough that a family is not told "asked" for a day.
    partner_answer_minutes: int = Field(default=360, ge=1)
    seed_demo_phone: str | None = None
    #: With no SMS provider the one-time code only reaches the log. Setting this to
    #: six digits makes `seed_demo_phone` (that phone alone) accept it, so a
    #: demonstration can sign in without anyone reading a log. Off by default;
    #: a real deployment sends real codes.
    demo_otp: str | None = None
    #: The email the first seeded family answers to, so someone can sign in with
    #: a code sent there. `demo_otp` applies to it as well.
    seed_demo_email: str | None = None
    #: Email for one-time codes, sent through Brevo over HTTPS. Without both of
    #: these the code is written to the log, as it is for a phone with no SMS.
    #: Sarvam: speech in Indian languages. First choice for listening, and the
    #: only way the family app can speak at all — no browser has an Odia voice.
    #: Aliased because the key is handed out as SARVAM_KEY, not under our prefix.
    sarvam_api_key: str | None = Field(default=None, alias="SARVAM_KEY")
    #: Pinned, not inferred: every earlier version of either model answers a
    #: request with a deprecation notice instead of audio.
    sarvam_listen_model: str = "saarika:v2.5"
    sarvam_speak_model: str = "bulbul:v3"
    #: Hertz. Sarvam defaults to 22050 if this is not asked for; 24000 is the
    #: most it offers and costs nothing extra — measured, same bytes back.
    #: A phone speaker will not make much of the difference, but a family
    #: listening in a noisy ward might, and nothing is lost by asking.
    sarvam_sample_rate: int = 24000

    brevo_api_key: str | None = None
    email_from: str | None = None
    email_from_name: str = "Saathi"
    #: How often the real world re-plans, in real seconds. In the real world a
    #: "day" is not simulated, so this is only how soon a changed fact (a report
    #: released, a date rolling over) is noticed.
    real_tick_seconds: float = 300.0
    database_url: str = "sqlite+aiosqlite:///./saathi.db"
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    # --- language layer ---
    #: Groq is the live demo's backend: constrained-decoding structured output
    #: at roughly 1000 tok/s, so a rendered message lands inside a tick.
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    #: Must be a model that supports `strict: true` structured outputs.
    groq_model: str = "openai/gpt-oss-20b"
    #: Actors write prose rather than fill a template, so they get more room.
    groq_actor_model: str = "openai/gpt-oss-120b"
    #: Multilingual speech-to-text. For many of these families voice is not
    #: a convenience, it is the only channel that works.
    whisper_model: str = "whisper-large-v3-turbo"
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_model: str = "claude-opus-5"

    # --- the live world ---
    #: Real seconds per simulated day.
    live_seconds_per_day: float = 4.0
    #: Families whose messages are rendered and whose actors run. Every patient
    #: is still planned every day; this caps API spend, not scope.
    live_watched: int = 8
    #: Ticks a desk candidate waits before it is assumed confirmed, so an
    #: unattended demo still moves.
    live_auto_confirm_ticks: int = 2
    #: Real seconds between caregiver messages from the actor.
    live_inbound_every_seconds: float = 15.0
    #: Days to rewind the world at startup, so reports land while anyone is
    #: watching instead of having all landed before the demo begins.
    live_start_offset_days: int = 3
    #: Start the clock on boot. Off by default: `make api` should behave as it
    #: always has until an operator presses play.
    live_autostart: bool = False
    #: Seed the two scripted demo families (`synthetic/scripted.py`) alongside
    #: the cohort, and enable `advance_story`. Off by default: the existing
    #: 50-family demo is unaffected unless this is explicitly turned on.
    #: The brief's two stories are the demo, so they are the default world.
    #: The 50-family cohort is still underneath them for scoring.
    live_scripted: bool = True

    # --- readiness model ---
    #: 1 - alpha is the coverage guarantee on readiness windows. 0.1 means we
    #: expect to be wrong about a report's timing at most 10% of the time.
    conformal_alpha: float = 0.1
    #: Days of slack added after a report's predicted-latest date.
    travel_lead_days: int = 1

    # --- real-world fact tools ---
    #: Where each hospital physically is, as ID=PLACE pairs. Configuration,
    #: not a constant in the code: a pilot at a different hospital changes
    #: this and nothing else. Read by `tools.fetch` and the centre directory.
    hospital_places: list[str] = Field(
        default_factory=lambda: ["TMH-MUM=Mumbai", "HBCH-MZP=Muzaffarpur"]
    )
    #: Services the reference cache is filled from. Free, keyless, rate-limited;
    #: override to point at your own instance for a pilot.
    #: Places that are destinations as well as origins — the district day-care
    #: centres a family might be offered instead of the hub. Fetched both ways
    #: so "is anywhere nearer?" can be answered at all.
    centre_places: list[str] = Field(
        default_factory=lambda: ["Darbhanga", "Samastipur", "Patna", "Gaya"]
    )
    geocoder_url: str = "https://nominatim.openstreetmap.org"
    router_url: str = "https://router.project-osrm.org"
    #: Let tools call out during a live run. Off by default — a demo makes far
    #: too many lookups for a public service, so the cache is filled once by
    #: `make fetch-reference` and read from thereafter.
    tools_allow_network: bool = False
    #: Where the fetched facts live. Empty means `<data_dir>/reference_cache.json`.
    reference_cache_path: str = ""
    #: Optional entitlement/scheme endpoint. Without it, what a family holds is
    #: whatever they or a desk have told us — and "unknown" otherwise, which is
    #: the answer that puts the document on the checklist.
    scheme_feed_url: str | None = None

    # --- health data ---
    abdm_base_url: str | None = None
    abdm_client_id: str | None = None
    abdm_client_secret: str | None = None
    hospital_feed_url: str | None = None

    # --- the hospital management system ---
    #: Root of the Bahmni install, e.g. https://hms.example.org — not the
    #: /openmrs path, which the adapter appends. Without it the desks are the
    #: feed, which is the pilot's starting point rather than a failure.
    bahmni_base_url: str | None = None
    bahmni_username: str | None = None
    bahmni_password: str | None = None
    #: How often to re-read the appointment window. Bahmni's appointments carry
    #: no `dateChanged`, so there is no cursor to poll against and every cycle
    #: reads the whole window — keep this honest about that cost. Three seconds
    #: is what makes a judge's cancellation feel immediate on stage.
    bahmni_poll_seconds: float = 3.0
    #: How far either side of today the appointment window reaches. The window
    #: is re-read in full every cycle, so this is the one knob that decides how
    #: much work a poll is.
    bahmni_window_days: int = 30
    #: How often to ask for clinical results. Separate from the appointment
    #: poll because this side *does* support `_lastUpdated`, so it is a cheap
    #: cursor query and does not need the same cadence.
    bahmni_clinical_poll_seconds: float = 15.0

    # --- OpenEMR, for the seeder ---
    #: Root of the OpenEMR install, e.g. http://localhost:8300 — not the
    #: /apis/default/fhir path, which the adapter appends.
    openemr_base_url: str | None = None
    #: From `python -m saathi.bootstrap.openemr_seed --register`. The signing
    #: key is a path, never the key itself: a private key in an environment
    #: variable ends up in logs and dashboards.
    openemr_client_id: str | None = None
    openemr_key_id: str | None = None
    openemr_key_path: str | None = None

    #: One entry per hospital that has a system to read, in the same `ID=VALUE`
    #: style as `hospital_places`:
    #:
    #:     TMH-MUM=bahmni|https://hms.example.org|user|pass
    #:     GAYA-DH=fhir|https://fhir.example.org/fhir
    #:
    #: The kind decides the adapter; everything after it is that adapter's
    #: connection detail. A hospital absent from this list has no system to
    #: read, which is not a failure: its desks are the feed.
    #:
    #: The `bahmni_*` settings above remain a single-hospital shorthand, so a
    #: deployment that predates this keeps working untouched.
    #: `NoDecode` so the environment source hands this over as the plain
    #: string it is. Without it pydantic-settings tries to JSON-decode a
    #: `list[str]` env var and the process dies at startup naming the field
    #: but not the reason — see `_comma_separated` below.
    hospital_systems: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- the open networks and the vendors' own gateways ---
    #: Networks a LIVE organisation books through, one per entry:
    #:
    #:     ondc=beckn|<gateway_url>|<bap_id>|<bap_uri>|<unique_key_id>|<signing_key_path>|<city>
    #:     demo=demo
    #:
    #: `demo` is a seller running inside this process (`adapters/beckn/demo.py`),
    #: for showing the flow without a network. Refused in production.
    network_providers: Annotated[list[str], NoDecode] = Field(default_factory=list)
    #: Vendors' own payment gateways, one per entry. The values after the kind
    #: are the NAMES of environment variables holding the keys, never the keys:
    #:
    #:     tmh-pharmacy=razorpay|TMH_RZP_KEY_ID|TMH_RZP_SECRET|TMH_RZP_WEBHOOK_SECRET
    #:     demo-pay=fake
    #:
    #: Saathi never holds money: each account is the vendor's, and the family
    #: pays the vendor through it. `fake` is for showing the flow; refused in
    #: production.
    payment_accounts: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- getting there: which bus, boarded where ---
    #: "google" reads Google's Directions API (needs `google_maps_api_key`, billing on);
    #: "demo" shows invented timetables labelled as such. Empty: no route planning,
    #: and the app falls back to opening Maps.
    routes_provider: str = ""
    google_maps_api_key: str | None = None
    #: What is around a point: shops, labs, clinics. "osm" (OpenStreetMap, no key),
    #: "google" (Places API, same key) or "demo" (invented shops, labelled). Empty: not offered.
    #: "local" reads our own `places` table, loaded monthly from
    #: OpenStreetMap (`python -m saathi.tools.load_places`). The one that
    #: works without a key, without billing, and without a public server's
    #: queue. "osm" reads Overpass live; "google" needs a key and billing.
    places_provider: str = ""
    #: The Overpass endpoint for `places_provider=osm` (OpenStreetMap's open data, no key).
    overpass_url: str = "https://overpass-api.de/api/interpreter"

    # --- reaching the family ---
    whatsapp_phone_number_id: str | None = None
    whatsapp_token: str | None = None
    exotel_sid: str | None = None
    exotel_token: str | None = None
    bhashini_api_key: str | None = None
    bhashini_user_id: str | None = None

    @model_validator(mode="after")
    def _no_sim_in_production(self) -> Settings:
        if self.sim_mode and self.environment.lower() == "production":
            raise ValueError(
                "SAATHI_SIM_MODE is on while SAATHI_ENVIRONMENT=production: "
                "demo controls must never be reachable in production"
            )
        if self.environment.lower() == "production":
            pretend = [
                entry
                for entry in (*self.network_providers, *self.payment_accounts)
                if entry.partition("=")[2].split("|")[0].strip().lower() in {"demo", "fake"}
            ]
            if pretend:
                raise ValueError(
                    f"{pretend} pretend to be a network or a gateway; "
                    "never in SAATHI_ENVIRONMENT=production"
                )
        if self.environment.lower() == "production" and "demo" in {
            self.routes_provider.strip().lower(),
            self.places_provider.strip().lower(),
        }:
            raise ValueError(
                "invented timetables or shops must never run in "
                "SAATHI_ENVIRONMENT=production"
            )
        if self.sim_mode and self.world == "real":
            raise ValueError(
                "SAATHI_SIM_MODE is on while SAATHI_WORLD=real: the simulator's "
                "controls must never be reachable on real records"
            )
        return self

    @field_validator("hospital_systems", "network_providers", "payment_accounts", mode="before")
    @classmethod
    def _comma_separated(cls, raw: object) -> object:
        """Accept `A,B` as well as `["A","B"]` from the environment.

        Paired with `NoDecode` on the field. Without both, a perfectly
        reasonable `SAATHI_HOSPITAL_SYSTEMS=TMH-MUM=bahmni|…,GAYA-DH=fhir|…`
        kills the process at startup with an error naming the field and not
        the reason. Nobody writing a deployment variable expects to quote JSON
        into it.

        A string that still looks like JSON is decoded as JSON, so both forms
        work and an existing deployment cannot break.
        """
        import json as _json

        if not isinstance(raw, str):
            return raw
        text = raw.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                return _json.loads(text)
            except ValueError as exc:
                raise ValueError(f"SAATHI_HOSPITAL_SYSTEMS is not valid JSON: {exc}") from exc
        return [part.strip() for part in text.split(",") if part.strip()]

    @field_validator("partners")
    @classmethod
    def _partners_mode(cls, mode: str | None) -> str | None:
        if mode is not None and mode not in ("simulated", "off"):
            raise ValueError("SAATHI_PARTNERS must be 'simulated' or 'off'")
        return mode

    @property
    def partners_on(self) -> bool:
        """Whether simulated organisations answer. Real records only, and only when asked for."""
        mode = self.partners or ("simulated" if self.seed_demo else "off")
        return self.real_world and mode == "simulated"

    @field_validator("demo_otp")
    @classmethod
    def _demo_otp_is_six_digits(cls, code: str | None) -> str | None:
        if code is not None and not (len(code) == 6 and code.isdigit()):
            raise ValueError("SAATHI_DEMO_OTP must be exactly six digits")
        return code

    @field_validator("records_url")
    @classmethod
    def _postgres_url_as_pasted(cls, url: str) -> str:
        """Accept the connection string as a host shows it.

        Supabase, Render and Heroku all hand out `postgres://` or `postgresql://`,
        which SQLAlchemy reads as the older psycopg2 driver. This project ships
        psycopg 3, so name it.
        """
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url[len(prefix) :]
        return url

    @model_validator(mode="after")
    def _auth_is_sound(self) -> Settings:
        if not self.auth_on:
            if self.environment.lower() == "production":
                raise ValueError(
                    "SAATHI_AUTH=off is not allowed when SAATHI_ENVIRONMENT=production"
                )
            return self
        production = self.environment.lower() == "production"
        if production and (len(self.auth_secret) < 32 or self.auth_secret.startswith("dev-only")):
            raise ValueError(
                "SAATHI_AUTH_SECRET must be set to your own value of at least 32 characters "
                "in production"
            )
        if production and self.identity_provider == "local":
            raise ValueError(
                "production needs SAATHI_IDENTITY_PROVIDER=oidc: local accounts log one-time "
                "codes instead of sending them"
            )
        return self

    @property
    def auth_on(self) -> bool:
        return self.auth == "on" or (self.auth == "auto" and self.world == "real")

    @property
    def real_world(self) -> bool:
        return self.world == "real"

    @property
    def data_path(self) -> Path:
        if self.data_dir:
            return Path(self.data_dir).expanduser().resolve()
        checkout = Path(__file__).resolve().parents[2] / "data"
        return checkout if checkout.is_dir() else (Path.cwd() / "data").resolve()

    @property
    def reference_cache_file(self) -> Path:
        if self.reference_cache_path:
            return Path(self.reference_cache_path).expanduser().resolve()
        return self.data_path / "reference_cache.json"

    @property
    def language_layer_enabled(self) -> bool:
        return bool(self.groq_api_key or self.anthropic_api_key)

    @property
    def actors_enabled(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)

    @property
    def abdm_enabled(self) -> bool:
        return bool(self.abdm_base_url and self.abdm_client_id and self.abdm_client_secret)

    @property
    def hospital_feed_enabled(self) -> bool:
        return bool(self.hospital_feed_url)

    @property
    def bahmni_enabled(self) -> bool:
        """Whether an HMS is connected at all.

        Note what is *not* required here: `tools_allow_network`. That switch
        exists to stop a demo hammering a public geocoder, and a hospital's own
        HMS is not that — a pilot that configured Bahmni meant it.
        """
        return bool(self.bahmni_base_url and self.bahmni_username and self.bahmni_password)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_token)

    @property
    def bhashini_enabled(self) -> bool:
        return bool(self.bhashini_api_key and self.bhashini_user_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
