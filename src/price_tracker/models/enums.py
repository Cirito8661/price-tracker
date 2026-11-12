"""Domain enumerations and their SQLAlchemy column types."""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class ScrapeStatus(StrEnum):
    """State of the most recent scrape attempt."""

    PENDING = "pending"
    OK = "ok"
    ERROR = "error"


class PriceChangeType(StrEnum):
    """Direction of a price change relative to the previous check."""

    INITIAL = "initial"
    DECREASE = "decrease"
    INCREASE = "increase"
    UNCHANGED = "unchanged"
    CURRENCY_CHANGED = "currency_changed"


class NotificationType(StrEnum):
    """Supported notification conditions."""

    PRICE_DROP = "price_drop"
    TARGET_REACHED = "target_reached"


class NotificationStatus(StrEnum):
    """Delivery state of a notification record."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


def sqlalchemy_enum(
    enum_class: type[StrEnum],
    *,
    name: str,
    length: int,
) -> SAEnum:
    """Build a portable VARCHAR-backed enum with a CHECK constraint."""

    return SAEnum(
        enum_class,
        name=name,
        native_enum=False,
        length=length,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )
