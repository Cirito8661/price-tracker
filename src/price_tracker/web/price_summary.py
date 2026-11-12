"""Display summary derived from real price history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..models.enums import PriceChangeType
from ..models.price_history import PriceHistory
from ..models.product import Product


@dataclass(frozen=True)
class PriceSummary:
    """Latest, previous, and change values for a product page."""

    latest_price: Decimal | None
    latest_currency: str | None
    latest_checked_at: datetime | None
    previous_price: Decimal | None
    previous_currency: str | None
    previous_checked_at: datetime | None
    change_type: PriceChangeType | None
    change_amount: Decimal | None


def build_price_summary(
    product: Product,
    history: list[PriceHistory],
) -> PriceSummary:
    """Build a summary from history, falling back to product data."""

    if not history:
        return PriceSummary(
            latest_price=product.current_price,
            latest_currency=product.currency,
            latest_checked_at=product.last_checked_at,
            previous_price=None,
            previous_currency=None,
            previous_checked_at=None,
            change_type=None,
            change_amount=None,
        )

    latest = history[-1]
    previous = history[-2] if len(history) >= 2 else None
    change_amount = None
    if previous is not None and previous.currency == latest.currency:
        change_amount = latest.price - previous.price

    return PriceSummary(
        latest_price=latest.price,
        latest_currency=latest.currency,
        latest_checked_at=latest.checked_at,
        previous_price=previous.price if previous is not None else None,
        previous_currency=previous.currency if previous is not None else None,
        previous_checked_at=previous.checked_at if previous is not None else None,
        change_type=latest.change_type,
        change_amount=change_amount,
    )
