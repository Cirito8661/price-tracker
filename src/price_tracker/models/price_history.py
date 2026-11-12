"""Price history model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..clock import utcnow
from ..database.base import Base
from ..database.types import DecimalText, UtcDateTime
from .enums import PriceChangeType, sqlalchemy_enum

if TYPE_CHECKING:
    from .product import Product


class PriceHistory(Base):
    """One successful price observation for a product."""

    __tablename__ = "price_history"
    __table_args__ = (
        CheckConstraint(
            "length(currency) = 3",
            name="currency_len",
        ),
        CheckConstraint(
            "length(price) > 0",
            name="price_nonempty",
        ),
        Index(
            "ix_price_history_product_checked",
            "product_id",
            "checked_at",
        ),
        Index("ix_price_history_checked_at", "checked_at"),
        Index("ix_price_history_change_type", "change_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    price: Mapped[Decimal] = mapped_column(DecimalText, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    change_type: Mapped[PriceChangeType] = mapped_column(
        sqlalchemy_enum(PriceChangeType, name="change_type", length=16),
        nullable=False,
    )
    checked_at: Mapped[datetime] = mapped_column(
        UtcDateTime,
        nullable=False,
        default=utcnow,
    )

    product: Mapped[Product] = relationship(back_populates="price_history")

    def __repr__(self) -> str:
        return (
            f"PriceHistory(id={self.id!r}, product_id={self.product_id!r}, "
            f"price={self.price!r}, currency={self.currency!r})"
        )
