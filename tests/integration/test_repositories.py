"""Repository behavior tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
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
from price_tracker.repositories.notifications import NotificationRepository
from price_tracker.repositories.price_history import PriceHistoryRepository
from price_tracker.repositories.products import ProductRepository

BASE_TIME = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


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


def make_history(
    product: Product,
    *,
    price: Decimal,
    change_type: PriceChangeType,
    checked_at: datetime,
) -> PriceHistory:
    return PriceHistory(
        product=product,
        price=price,
        currency="GBP",
        change_type=change_type,
        checked_at=checked_at,
    )


def make_notification(
    product: Product,
    *,
    notification_type: NotificationType,
    old_price: Decimal,
    new_price: Decimal,
    status: NotificationStatus,
    created_at: datetime,
    attempts: int = 0,
) -> Notification:
    return Notification(
        product=product,
        notification_type=notification_type,
        old_price=old_price,
        new_price=new_price,
        currency="GBP",
        status=status,
        created_at=created_at,
        attempts=attempts,
    )


def test_product_repository_crud(db_session: Session) -> None:
    repository = ProductRepository(db_session)
    product = repository.add(make_product())

    assert product.id is not None
    assert repository.get(product.id) is product
    assert repository.get_by_url(product.url) is product
    assert repository.count() == 1
    assert repository.list() == [product]

    repository.delete(product)
    db_session.commit()

    assert repository.count() == 0
    assert repository.get(product.id) is None


def test_product_repository_active_filters(db_session: Session) -> None:
    repository = ProductRepository(db_session)
    active = repository.add(make_product())
    inactive = repository.add(
        make_product(
            url="https://books.toscrape.com/catalogue/other.html",
            is_active=False,
        )
    )
    db_session.commit()

    assert repository.count() == 2
    assert repository.count(active_only=True) == 1
    assert repository.list_active_ids() == [active.id]
    assert repository.list(active_only=True) == [active]
    assert {product.id for product in repository.list()} == {
        active.id,
        inactive.id,
    }


def test_price_history_repository(db_session: Session) -> None:
    product_repository = ProductRepository(db_session)
    history_repository = PriceHistoryRepository(db_session)
    product = product_repository.add(make_product())
    first = history_repository.add(
        make_history(
            product,
            price=Decimal("51.77"),
            change_type=PriceChangeType.INITIAL,
            checked_at=BASE_TIME,
        )
    )
    second = history_repository.add(
        make_history(
            product,
            price=Decimal("45.00"),
            change_type=PriceChangeType.DECREASE,
            checked_at=BASE_TIME + timedelta(hours=1),
        )
    )
    third = history_repository.add(
        make_history(
            product,
            price=Decimal("47.00"),
            change_type=PriceChangeType.INCREASE,
            checked_at=BASE_TIME + timedelta(hours=2),
        )
    )
    db_session.commit()

    assert history_repository.list_for_product(product.id) == [
        first,
        second,
        third,
    ]
    assert history_repository.latest_for_product(product.id) is third
    assert history_repository.count_for_product(product.id) == 3
    assert history_repository.recent_decreases(BASE_TIME + timedelta(hours=1)) == [second]
    assert [entry for entry, related_product in history_repository.recent_changes(limit=2)] == [
        third,
        second,
    ]
    assert all(
        related_product.id == product.id
        for _, related_product in history_repository.recent_changes(limit=2)
    )


def test_notification_repository(db_session: Session) -> None:
    product_repository = ProductRepository(db_session)
    notification_repository = NotificationRepository(db_session)
    product = product_repository.add(make_product())
    sent = notification_repository.add(
        make_notification(
            product,
            notification_type=NotificationType.PRICE_DROP,
            old_price=Decimal("51.77"),
            new_price=Decimal("40.00"),
            status=NotificationStatus.SENT,
            created_at=BASE_TIME,
        )
    )
    failed = notification_repository.add(
        make_notification(
            product,
            notification_type=NotificationType.TARGET_REACHED,
            old_price=Decimal("40.00"),
            new_price=Decimal("39.00"),
            status=NotificationStatus.FAILED,
            created_at=BASE_TIME + timedelta(hours=1),
            attempts=1,
        )
    )
    db_session.commit()

    assert (
        notification_repository.latest_sent(
            product.id,
            NotificationType.PRICE_DROP,
        )
        is sent
    )
    assert (
        notification_repository.find_sent_with_price(
            product.id,
            NotificationType.PRICE_DROP,
            Decimal("40.00"),
        )
        is sent
    )
    assert (
        notification_repository.find_sent_with_price(
            product.id,
            NotificationType.PRICE_DROP,
            Decimal("39.00"),
        )
        is None
    )
    assert notification_repository.find_retryable(
        product.id,
        max_attempts=3,
    ) == [failed]
    assert notification_repository.list_for_product(product.id) == [
        failed,
        sent,
    ]
    assert notification_repository.count_for_product(product.id) == 2


def test_notification_retryable_excludes_exhausted_attempts(
    db_session: Session,
) -> None:
    product_repository = ProductRepository(db_session)
    notification_repository = NotificationRepository(db_session)
    product = product_repository.add(make_product())
    notification_repository.add(
        make_notification(
            product,
            notification_type=NotificationType.PRICE_DROP,
            old_price=Decimal("51.77"),
            new_price=Decimal("40.00"),
            status=NotificationStatus.FAILED,
            created_at=BASE_TIME,
            attempts=3,
        )
    )
    db_session.commit()

    assert (
        notification_repository.find_retryable(
            product.id,
            max_attempts=3,
        )
        == []
    )


def test_session_scope_commits(
    session_factory: SessionFactory,
) -> None:
    from price_tracker.database.session import session_scope

    with session_scope(session_factory) as session:
        repository = ProductRepository(session)
        product = repository.add(make_product())

    with session_factory() as session:
        loaded = ProductRepository(session).get(product.id)
        assert loaded is not None
        assert loaded.url == product.url


def test_session_scope_rolls_back_on_error(
    session_factory: SessionFactory,
) -> None:
    from price_tracker.database.session import session_scope

    with pytest.raises(RuntimeError), session_scope(session_factory) as session:
        ProductRepository(session).add(make_product())
        raise RuntimeError("force rollback")

    with session_factory() as session:
        assert ProductRepository(session).count() == 0
