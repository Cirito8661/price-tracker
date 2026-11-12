"""Tracked product model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Index,
    Integer,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..clock import utcnow
from ..database.base import Base
from ..database.types import DecimalText, UtcDateTime
from .enums import ScrapeStatus, sqlalchemy_enum

if TYPE_CHECKING:
    from .notification import Notification
    from .price_history import PriceHistory


class Product(Base):
    """A product whose price is monitored by the application."""

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "(current_price IS NULL AND currency IS NULL) OR "
            "(current_price IS NOT NULL AND currency IS NOT NULL)",
            name="price_currency_pair",
        ),
        CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="currency_len",
        ),
        CheckConstraint(
            "length(store) > 0",
            name="store_len",
        ),
        Index("ix_products_is_active", "is_active"),
        Index("ix_products_store", "store"),
        Index("ix_products_scrape_status", "scrape_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    store: Mapped[str] = mapped_column(String(64), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(
        DecimalText,
        nullable=True,
    )
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(
        DecimalText,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=true(),
    )
    scrape_status: Mapped[ScrapeStatus] = mapped_column(
        sqlalchemy_enum(ScrapeStatus, name="scrape_status", length=16),
        nullable=False,
        default=ScrapeStatus.PENDING,
        server_default=ScrapeStatus.PENDING.value,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime,
        nullable=True,
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        UtcDateTime,
        nullable=True,
    )

    price_history: Mapped[list[PriceHistory]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="PriceHistory.checked_at",
    )
    notifications: Mapped[list[Notification]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Notification.created_at",
    )

    def __repr__(self) -> str:
        return f"Product(id={self.id!r}, store={self.store!r}, url={self.url!r})"
