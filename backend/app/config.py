from functools import lru_cache
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit
from pathlib import Path
from pydantic import AwareDatetime, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    nebius_api_key: SecretStr | None = None
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1"
    nebius_lightning_model: str = "nvidia/Nemotron-3_5-Lightning"
    nebius_super_model: str = "nvidia/nemotron-3-super-120b-a12b"
    infraclaim_llm_mode: Literal["mock", "live"] = "mock"
    nebius_timeout_seconds: float = Field(default=45, ge=1, le=120)
    nebius_max_attempts: int = Field(default=2, ge=1, le=3)
    nebius_max_tokens: int = Field(default=8192, ge=256, le=16384)
    evaluation_api_enabled: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    database_path: str = "data/infraclaim.sqlite3"
    auth_enabled: bool = True
    self_signup_enabled: bool = False  # Explicitly opt in for a trusted local pilot.
    auth_cookie_secure: bool = False  # Set true behind HTTPS in a hosted deployment.
    infraclaim_deployment: Literal['local', 'hosted'] = 'local'
    manual_source_gate: bool = True
    autonomy_min_confidence: float = Field(default=0.90, ge=0, le=1)
    autonomy_max_amount_usd: float = Field(default=50000, gt=0)
    watcher_enabled: bool = True
    watcher_interval_seconds: float = Field(default=2, ge=0.1)
    credit_delay_seconds: float = Field(default=4, ge=0)
    # Freeze business time for replayable October 2026 fixtures; audit time is real UTC.
    demo_now: AwareDatetime = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)

    @model_validator(mode='after')
    def hosted_security(self):
        if self.infraclaim_deployment == 'hosted' and (not self.auth_enabled or not self.auth_cookie_secure):
            raise ValueError('Hosted deployment requires authentication and secure session cookies.')
        return self

    @field_validator('nebius_base_url')
    @classmethod
    def trusted_endpoint(cls, value):
        url = urlsplit(value)
        host = url.hostname or ''
        if (url.scheme != 'https' or url.username or url.password or url.query or url.fragment
                or url.port not in (None, 443) or url.path.rstrip('/') != '/v1'
                or not (host == 'api.tokenfactory.nebius.com'
                        or (host.startswith('api.tokenfactory.') and host.endswith('.nebius.com')))):
            raise ValueError('Use an HTTPS Nebius Token Factory /v1 endpoint without credentials or query parameters')
        return value.rstrip('/')

    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / '.env', extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
