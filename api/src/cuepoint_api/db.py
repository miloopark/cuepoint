from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings


def _normalize(url: str) -> str:
    """Accept Neon/Heroku-style postgres:// URLs and pin the psycopg driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


# Explicit pool bounds: a saturated pool times out fast instead of hanging handlers.
engine = create_engine(
    _normalize(settings.database_url),
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
