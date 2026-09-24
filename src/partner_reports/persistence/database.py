"""Database engine/session factories that never log the connection secret."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from partner_reports.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create the process-level PostgreSQL engine with liveness checks."""

    database_url = get_settings().database_url.get_secret_value()
    return create_engine(database_url, pool_pre_ping=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return non-autocommitting sessions for explicit transaction boundaries."""

    return sessionmaker(bind=get_engine(), expire_on_commit=False)
