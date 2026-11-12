"""Integration tests for SQLite engine configuration."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, select

from price_tracker.database.base import Base
from price_tracker.database.engine import create_engine_for_url
from price_tracker.database.schema import DatabaseSchemaError, verify_database_schema
from price_tracker.database.session import create_session_factory
from price_tracker.models.product import Product


def test_sqlite_pragmas_are_enabled(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar() == 5000
        assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
        assert connection.exec_driver_sql("PRAGMA synchronous").scalar() == 1


def test_non_sqlite_url_is_rejected() -> None:
    with pytest.raises(ValueError):
        create_engine_for_url("postgresql://user:pass@example.com/db")


def test_sqlite_parent_directory_is_created(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "price_tracker.db"

    engine = create_engine_for_url(f"sqlite+pysqlite:///{database_path.as_posix()}")
    try:
        assert database_path.parent.is_dir()
    finally:
        engine.dispose()


def test_in_memory_database_uses_shared_connection() -> None:
    engine = create_engine_for_url("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            session.add(
                Product(
                    url="https://books.toscrape.com/catalogue/test.html",
                    store="books_toscrape",
                    current_price=Decimal("10.00"),
                    currency="GBP",
                )
            )
            session.commit()

        with session_factory() as session:
            product = session.scalars(select(Product)).one()
            assert product.current_price == Decimal("10.00")
    finally:
        engine.dispose()


def test_verify_schema_passes_for_initialized_database(db_engine: Engine) -> None:
    verify_database_schema(db_engine)


def test_verify_schema_reports_missing_tables(tmp_path: Path) -> None:
    database_path = tmp_path / "empty.db"
    engine = create_engine_for_url(f"sqlite+pysqlite:///{database_path.as_posix()}")
    try:
        with pytest.raises(DatabaseSchemaError, match="alembic upgrade head"):
            verify_database_schema(engine)
    finally:
        engine.dispose()
