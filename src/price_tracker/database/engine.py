"""SQLite engine creation and connection-level pragmas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.pool import NullPool, StaticPool

from ..config import Settings


def _is_memory_database(url: URL) -> bool:
    database = url.database or ""
    return database in {"", ":memory:"} or ":memory:" in database or "mode=memory" in str(url)


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("only SQLite database URLs are supported")

    database = url.database
    if not database or _is_memory_database(url) or database.startswith("file:"):
        return

    Path(database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite_connection(
    dbapi_connection: Any,
    connection_record: Any,
) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def create_engine_for_url(database_url: str) -> Engine:
    """Create a SQLite engine with concurrency-safe pragmas."""

    _ensure_sqlite_parent(database_url)
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("only SQLite database URLs are supported")

    memory_database = _is_memory_database(url)
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        poolclass=StaticPool if memory_database else NullPool,
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def create_engine_from_settings(settings: Settings) -> Engine:
    """Create the configured application engine."""

    return create_engine_for_url(settings.effective_database_url)
