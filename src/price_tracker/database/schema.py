"""Database schema verification used during application startup."""

from __future__ import annotations

from sqlalchemy import Engine, inspect

REQUIRED_TABLES = frozenset({"products", "price_history", "notifications"})


class DatabaseSchemaError(RuntimeError):
    """Raised when the database has not been initialized by Alembic."""


def verify_database_schema(engine: Engine) -> None:
    """Ensure the required application tables exist.

    The application intentionally does not auto-migrate. If the schema is
    missing, the user must run ``alembic upgrade head``.
    """

    existing_tables = set(inspect(engine).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - existing_tables)
    if missing_tables:
        missing = ", ".join(missing_tables)
        raise DatabaseSchemaError(
            "Database schema is not initialized. Run `alembic upgrade head` "
            f"from the project root. Missing tables: {missing}."
        )
