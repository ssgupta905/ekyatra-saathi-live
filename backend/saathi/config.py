"""Configuration, read from the environment.

Every external dependency is optional. With nothing configured, Saathi runs
fully in-process against synthetic data — which is what the prototype does and
what CI runs. Each integration turns on when its credentials appear.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # --- storage ---
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
        return self

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
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_token)

    @property
    def bhashini_enabled(self) -> bool:
        return bool(self.bhashini_api_key and self.bhashini_user_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
