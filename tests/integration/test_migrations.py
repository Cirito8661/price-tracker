"""Alembic migration tests."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

import price_tracker.models  # noqa: F401
from price_tracker.database.base import Base
from price_tracker.database.engine import create_engine_for_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def make_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["configure_logger"] = False
    return config


def make_database_url(tmp_path: Path) -> str:
    return f"sqlite+pysqlite:///{(tmp_path / 'migration.db').as_posix()}"


def test_upgrade_creates_schema_and_downgrade_removes_it(
    tmp_path: Path,
) -> None:
    database_url = make_database_url(tmp_path)
    config = make_config(database_url)

    command.upgrade(config, "head")

    engine = create_engine_for_url(database_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"products", "price_history", "notifications"} <= tables

        product_columns = {column["name"] for column in inspector.get_columns("products")}
        assert {
            "id",
            "url",
            "name",
            "store",
            "current_price",
            "currency",
            "target_price",
            "is_active",
            "scrape_status",
            "last_error",
            "created_at",
            "updated_at",
            "last_checked_at",
            "last_attempt_at",
        } <= product_columns

        product_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("products")
        }
        assert {
            "ck_products_currency_len",
            "ck_products_price_currency_pair",
            "ck_products_scrape_status",
            "ck_products_store_len",
        } <= product_checks

        product_uniques = {
            constraint["name"] for constraint in inspector.get_unique_constraints("products")
        }
        assert "uq_products_url" in product_uniques

        product_indexes = {index["name"] for index in inspector.get_indexes("products")}
        assert {
            "ix_products_is_active",
            "ix_products_store",
            "ix_products_scrape_status",
        } <= product_indexes

        history_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("price_history")
        }
        assert {
            "ck_price_history_currency_len",
            "ck_price_history_price_nonempty",
            "ck_price_history_change_type",
        } <= history_checks

        notification_checks = {
            constraint["name"] for constraint in inspector.get_check_constraints("notifications")
        }
        assert {
            "ck_notifications_currency_len",
            "ck_notifications_prices_nonempty",
            "ck_notifications_attempts_nonnegative",
            "ck_notifications_notification_type",
            "ck_notifications_status",
        } <= notification_checks

        history_foreign_keys = inspector.get_foreign_keys("price_history")
        assert any(
            foreign_key["referred_table"] == "products"
            and foreign_key["options"].get("ondelete") == "CASCADE"
            for foreign_key in history_foreign_keys
        )

        notification_foreign_keys = inspector.get_foreign_keys("notifications")
        assert any(
            foreign_key["referred_table"] == "products"
            and foreign_key["options"].get("ondelete") == "CASCADE"
            for foreign_key in notification_foreign_keys
        )
    finally:
        engine.dispose()

    command.downgrade(config, "base")

    engine = create_engine_for_url(database_url)
    try:
        remaining_tables = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    assert {"products", "price_history", "notifications"}.isdisjoint(remaining_tables)


def test_migration_matches_model_metadata(tmp_path: Path) -> None:
    database_url = make_database_url(tmp_path)
    config = make_config(database_url)
    command.upgrade(config, "head")

    engine = create_engine_for_url(database_url)
    try:
        with engine.connect() as connection:
            migration_context = MigrationContext.configure(
                connection,
                opts={"compare_type": True, "render_as_batch": True},
            )
            differences = compare_metadata(migration_context, Base.metadata)
    finally:
        engine.dispose()

    relevant_differences = [
        difference
        for difference in differences
        if not (
            isinstance(difference, tuple)
            and difference
            and difference[0] == "remove_table"
            and getattr(difference[1], "name", None) == "alembic_version"
        )
    ]

    assert relevant_differences == []
