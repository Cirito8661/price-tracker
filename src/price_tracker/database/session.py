"""Session factory and transaction helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

SessionFactory = sessionmaker[Session]


def create_session_factory(engine: Engine) -> SessionFactory:
    """Create a session factory with explicit transaction control."""

    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )


@contextmanager
def session_scope(session_factory: SessionFactory) -> Iterator[Session]:
    """Provide a session that commits on success and rolls back on error."""

    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
