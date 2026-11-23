from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from domain.persistence.models import Base

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine(database_url: str | None = None) -> Engine:
    """Returns or initializes the singleton SQLAlchemy 2.x engine with SQLite WAL optimization."""
    global _engine
    if _engine is None or (database_url and str(_engine.url) != database_url):
        url = database_url or get_settings().database_url
        connect_args: dict[str, Any] = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False

        _engine = create_engine(url, connect_args=connect_args)

        # Enforce WAL mode and foreign key constraints for SQLite connections
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()

    return _engine


def get_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    """Returns singleton sessionmaker bound to current engine."""
    global _session_factory
    engine = get_engine(database_url)
    if _session_factory is None:
        _session_factory = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=engine,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def get_db_session(database_url: str | None = None) -> Generator[Session]:
    """Context manager providing a transactional database session."""
    factory = get_session_factory(database_url)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(engine: Engine | None = None) -> None:
    """Initializes all 11 tables in the database schema automatically."""
    target_engine = engine or get_engine()
    Base.metadata.create_all(bind=target_engine)
