"""Database fixtures use a rollback-only transaction and synthetic records."""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from partner_reports.config import get_settings


@pytest.fixture
def db_session() -> Iterator[Session]:
    database_url = get_settings().database_url.get_secret_value()
    engine = create_engine(database_url, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
        engine.dispose()
