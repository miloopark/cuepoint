"""Settings from environment (CUEPOINT_*), with local docker-compose defaults."""

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CUEPOINT_", env_file=".env", extra="ignore")

    # CUEPOINT_DATABASE_URL locally; DATABASE_URL as injected by Neon on Vercel.
    database_url: str = Field(
        default="postgresql+psycopg://cuepoint:cuepoint@localhost:5433/cuepoint",
        validation_alias=AliasChoices("CUEPOINT_DATABASE_URL", "DATABASE_URL"),
    )
    redis_url: str = "redis://localhost:6379/0"

    # "rq" (local docker redis) or "vercel" (Vercel Queues push subscribers)
    queue_backend: str = "rq"

    # "s3" (local SeaweedFS / R2 via boto3) or "blob" (Vercel Blob public store)
    storage_backend: str = "s3"
    # Blob mode: the store's public base URL; audio keys are full blob URLs under it.
    blob_public_base: str = ""

    s3_endpoint: str = "http://localhost:8333"
    s3_access_key: str = "cuepoint"
    s3_secret_key: str = "cuepoint123"
    s3_bucket: str = "cuepoint-audio"

    cors_origins: list[str] = ["http://localhost:5173"]
    max_upload_mb: int = 300

    # audd.io API token; empty = identification disabled.
    audd_token: str = ""


settings = Settings()
