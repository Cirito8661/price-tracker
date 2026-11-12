"""Notification history model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..clock import utcnow
from ..database.base import Base
from ..database.types import DecimalText, UtcDateTime
from .enums import NotificationStatus, NotificationType, sqlalchemy_enum

if TYPE_CHECKING:
    from .product import Product


class Notification(Base):
    """A price-drop or target-price notification event."""

    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "length(currency) = 3",
            name="currency_len",
        ),
        CheckConstraint(
            "length(old_price) > 0 AND length(new_price) > 0",
            name="prices_nonempty",
        ),
        CheckConstraint(
            "attempts >= 0",
            name="attempts_nonnegative",
        ),
        Index(
            "ix_notifications_product_type_created",
            "product_id",
            "notification_type",
            "created_at",
        ),
        Index("ix_notifications_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        sqlalchemy_enum(
            NotificationType,
            name="notification_type",
            length=32,
        ),
        nullable=False,
    )
    old_price: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    new_price: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        sqlalchemy_enum(
            NotificationStatus,
            name="status",
            length=16,
        ),
        nullable=False,
        default=NotificationStatus.PENDING,
        server_default=NotificationStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime,
        nullable=True,
    )

    product: Mapped[Product] = relationship(back_populates="notifications")

    def __repr__(self) -> str:
        return (
            f"Notification(id={self.id!r}, product_id={self.product_id!r}, "
            f"type={self.notification_type!r}, status={self.status!r})"
        )
