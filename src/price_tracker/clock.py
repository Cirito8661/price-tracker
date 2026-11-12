"""Time utilities used across the application."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""

    return datetime.now(UTC)
