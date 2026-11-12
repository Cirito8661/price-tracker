"""Helpers for web integration tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import PriceChangeType, ScrapeStatus
from price_tracker.models.price_history import PriceHistory
from price_tracker.models.product import Product

_CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


def extract_csrf_token(html: str) -> str:
    match = _CSRF_PATTERN.search(html)
    if match is None:
        raise AssertionError("CSRF token not found in response")
    return match.group(1)


def create_product(
    session_factory: SessionFactory,
    **overrides: object,
) -> Product:
    values: dict[str, object] = {
        "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "name": None,
        "store": "books.toscrape.com",
        "current_price": None,
        "currency": None,
        "target_price": None,
        "is_active": True,
        "scrape_status": ScrapeStatus.PENDING,
    }
    values.update(overrides)

    with session_factory() as session:
        product = Product(**values)
        session.add(product)
        session.commit()
        session.refresh(product)
        return product


def create_history(
    session_factory: SessionFactory,
    product: Product,
    *,
    price: Decimal,
    currency: str = "GBP",
    change_type: PriceChangeType = PriceChangeType.DECREASE,
    checked_at: datetime | None = None,
) -> PriceHistory:
    with session_factory() as session:
        entry = PriceHistory(
            product_id=product.id,
            price=price,
            currency=currency,
            change_type=change_type,
            checked_at=checked_at or datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def count_products(session_factory: SessionFactory) -> int:
    with session_factory() as session:
        return len(list(session.scalars(select(Product))))


def load_product(session_factory: SessionFactory, product_id: int) -> Product | None:
    with session_factory() as session:
        return session.get(Product, product_id)
