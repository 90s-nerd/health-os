from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Health OS"
    deployment_mode: str = "standalone"
    auth_mode: str = "pin"
    database_url: str = "sqlite:///./health-os.db"
    timezone: str = "America/Chicago"
    default_timezone: str = "America/Chicago"
    ha_trusted_proxies: str = "172.30.32.2/32"
    embedded_mode: bool = False
    frame_ancestors: str = ""
    app_pin: str | None = None
    session_secret: str = "development-only-change-me"
    session_secure: bool = False
    session_timeout_minutes: int = 120
    keep_signed_in_days: int = 30
    backup_dir: str = "./backups"
    backup_retention_days: int = 14
    photo_uploads_enabled: bool = False
    integration_enabled: bool = False
    integration_base_url: str = "http://automation.local:8123"
    integration_token: str | None = None
    integration_verify_ssl: bool = False
    supervisor_token: str | None = None
    supervisor_api_url: str = "http://supervisor/core"


@lru_cache
def get_config() -> Config:
    return Config()
