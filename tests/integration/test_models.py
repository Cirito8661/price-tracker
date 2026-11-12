"""Model persistence and constraint tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import (
    NotificationStatus,
    NotificationType,
    PriceChangeType,
    ScrapeStatus,
)
from price_tracker.models.notification import Notification
from price_tracker.models.price_history import PriceHistory
from price_tracker.models.product import Product


def make_product(**overrides: object) -> Product:
    values: dict[str, object] = {
        "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "name": "A Light in the Attic",
        "store": "books_toscrape",
        "current_price": Decimal("51.77"),
        "currency": "GBP",
        "target_price": Decimal("40.00"),
        "is_active": True,
        "scrape_status": ScrapeStatus.OK,
    }
    values.update(overrides)
    return Product(**values)


def make_history(product: Product, **overrides: object) -> PriceHistory:
    values: dict[str, object] = {
        "product": product,
        "price": Decimal("51.77"),
        "currency": "GBP",
        "change_type": PriceChangeType.INITIAL,
        "checked_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }
    values.update(overrides)
    return PriceHistory(**values)


def make_notification(product: Product, **overrides: object) -> Notification:
    values: dict[str, object] = {
        "product": product,
        "notification_type": NotificationType.PRICE_DROP,
        "old_price": Decimal("51.77"),
        "new_price": Decimal("40.00"),
        "currency": "GBP",
        "status": NotificationStatus.SENT,
        "created_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    }
    values.update(overrides)
    return Notification(**values)


def test_product_decimal_and_utc_roundtrip(db_session: Session) -> None:
    product = make_product(
        created_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    db_session.add(product)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(Product, product.id)

    assert loaded is not None
    assert loaded.current_price == Decimal("51.77")
    assert loaded.target_price == Decimal("40.00")
    assert loaded.currency == "GBP"
    assert loaded.scrape_status is ScrapeStatus.OK
    assert loaded.is_active is True
    assert loaded.created_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert loaded.created_at.tzinfo is UTC


def test_failed_scrape_product_allows_null_fields(db_session: Session) -> None:
    product = make_product(
        name=None,
        current_price=None,
        currency=None,
        target_price=None,
        scrape_status=ScrapeStatus.ERROR,
        last_error="price not found",
        last_attempt_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )
    db_session.add(product)
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(Product, product.id)

    assert loaded is not None
    assert loaded.name is None
    assert loaded.current_price is None
    assert loaded.currency is None
    assert loaded.scrape_status is ScrapeStatus.ERROR
    assert loaded.last_error == "price not found"
    assert loaded.last_checked_at is None
    assert loaded.last_attempt_at == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_duplicate_url_is_rejected(db_session: Session) -> None:
    db_session.add(make_product())
    db_session.commit()

    db_session.add(make_product())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_price_currency_pair_constraint(db_session: Session) -> None:
    db_session.add(
        make_product(
            current_price=Decimal("10.00"),
            currency=None,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_currency_length_constraint(db_session: Session) -> None:
    db_session.add(make_product(currency="GB"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_notification_attempts_constraint(db_session: Session) -> None:
    product = make_product()
    db_session.add(product)
    db_session.flush()
    db_session.add(make_notification(product, attempts=-1))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_relationships_and_cascade_delete(
    db_session: Session,
    session_factory: SessionFactory,
) -> None:
    product = make_product()
    history = make_history(product)
    notification = make_notification(product)
    db_session.add_all([product, history, notification])
    db_session.commit()

    db_session.refresh(product)
    assert product.price_history == [history]
    assert product.notifications == [notification]

    db_session.delete(product)
    db_session.commit()

    with session_factory() as verification_session:
        history_count = verification_session.scalar(select(func.count()).select_from(PriceHistory))
        notification_count = verification_session.scalar(
            select(func.count()).select_from(Notification)
        )

    assert history_count == 0
    assert notification_count == 0


def test_updated_at_changes_on_update(db_session: Session) -> None:
    product = make_product(
        created_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    db_session.add(product)
    db_session.commit()
    original_updated_at = product.updated_at

    product.name = "Updated title"
    db_session.commit()

    assert product.updated_at > original_updated_at
    assert product.updated_at.tzinfo is UTC


def test_enum_values_roundtrip(db_session: Session) -> None:
    product = make_product()
    history = make_history(
        product,
        change_type=PriceChangeType.DECREASE,
    )
    notification = make_notification(
        product,
        status=NotificationStatus.FAILED,
    )
    db_session.add_all([product, history, notification])
    db_session.commit()
    db_session.expire_all()

    loaded_product = db_session.get(Product, product.id)
    loaded_history = db_session.get(PriceHistory, history.id)
    loaded_notification = db_session.get(Notification, notification.id)

    assert loaded_product is not None
    assert loaded_product.scrape_status is ScrapeStatus.OK
    assert loaded_history is not None
    assert loaded_history.change_type is PriceChangeType.DECREASE
    assert loaded_notification is not None
    assert loaded_notification.notification_type is NotificationType.PRICE_DROP
    assert loaded_notification.status is NotificationStatus.FAILED
