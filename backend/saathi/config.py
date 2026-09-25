"""Configuration, read from the environment.

Every external dependency is optional. With nothing configured, Saathi runs
fully in-process against synthetic data — which is what the prototype does and
what CI runs. Each integration turns on when its credentials appear.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="SAATHI_", extra="ignore"
    )

    environment: str = "local"
    log_level: str = "INFO"

    # --- storage ---
    database_url: str = "sqlite+aiosqlite:///./saathi.db"
    neo4j_uri: str | None = None
    neo4j_user: str | None = None
    neo4j_password: str | None = None

    # --- language layer ---
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_model: str = "claude-opus-5"

    # --- readiness model ---
    #: 1 - alpha is the coverage guarantee on readiness windows. 0.1 means we
    #: expect to be wrong about a report's timing at most 10% of the time.
    conformal_alpha: float = 0.1
    #: Days of slack added after a report's predicted-latest date.
    travel_lead_days: int = 1

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

    @property
    def language_layer_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def neo4j_enabled(self) -> bool:
        return bool(self.neo4j_uri and self.neo4j_user and self.neo4j_password)

    @property
    def whatsapp_enabled(self) -> bool:
        return bool(self.whatsapp_phone_number_id and self.whatsapp_token)

    @property
    def bhashini_enabled(self) -> bool:
        return bool(self.bhashini_api_key and self.bhashini_user_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
