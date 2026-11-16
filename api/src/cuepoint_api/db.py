from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .config import settings

# Explicit pool bounds: a saturated pool times out fast instead of hanging handlers.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=10,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
