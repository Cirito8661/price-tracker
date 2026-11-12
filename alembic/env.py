"""Alembic environment for Price Tracker."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

import price_tracker.models  # noqa: F401
from price_tracker.config import Settings
from price_tracker.database.base import Base
from price_tracker.database.engine import create_engine_for_url

config = context.config
if config.config_file_name is not None and config.attributes.get(
    "configure_logger",
    True,
):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured and configured.strip():
        return configured.strip()
    return Settings().effective_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine_for_url(_database_url())
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                compare_type=True,
                render_as_batch=True,
            )
            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
