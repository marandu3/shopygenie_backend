from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql+asyncpg://shopygenie:shopygenie@localhost:5433/shopygenie"

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14

    cors_origins: str = "http://localhost:4200"

    platform_owner_email: str = "johnwillymarandu@gmail.com"
    platform_owner_password: str = "change-me"
    platform_owner_name: str = "Platform Owner"

    # Local-dev/seed convenience only — never read by the live send path
    # (app/integrations/sms/factory.get_sms_provider), which is strictly
    # per-organization (MASTER PROMPT §43). When set, scripts/seed.py
    # applies these to the demo tenant so SMS can be tested immediately
    # without clicking through Settings → Notifications first.
    smsgate_base_url: str = ""
    smsgate_username: str = ""
    smsgate_password: str = ""
    smsgate_device_id: str = ""

    uploads_dir: str = "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
