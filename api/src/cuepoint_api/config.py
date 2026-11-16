"""Settings from environment (CUEPOINT_*), with local docker-compose defaults."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUEPOINT_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://cuepoint:cuepoint@localhost:5433/cuepoint"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "cuepoint"
    s3_secret_key: str = "cuepoint123"
    s3_bucket: str = "cuepoint-audio"

    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_mb: int = 300

    # audd.io API token; empty = identification disabled.
    audd_token: str = ""


settings = Settings()
