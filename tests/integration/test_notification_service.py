"""Notification persistence, deduplication, and retry tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from price_tracker.config import Settings
from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import (
    NotificationStatus,
    NotificationType,
    PriceChangeType,
    ScrapeStatus,
)
from price_tracker.models.price_history import PriceHistory
from price_tracker.repositories.notifications import NotificationRepository
from price_tracker.services.notification_service import NotificationService
from price_tracker.services.product_service import PriceCheckRecord
from tests.web_helpers import create_product

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NEW_TIME = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


class FakeChannel:
    name = "fake"

    def __init__(self, enabled: bool = True, fail: bool = False) -> None:
        self.enabled = enabled
        self.fail = fail
        self.sent = []

    def is_enabled(self) -> bool:
        return self.enabled

    async def send(self, notification, product) -> None:
        if self.fail:
            raise RuntimeError("channel failed")
        self.sent.append(notification)


def make_record(
    session_factory: SessionFactory,
    *,
    old_price: Decimal = Decimal("51.77"),
    new_price: Decimal = Decimal("45.00"),
    target_price: Decimal | None = None,
    change_type: PriceChangeType = PriceChangeType.DECREASE,
) -> PriceCheckRecord:
    product = create_product(
        session_factory,
        name="A Light in the Attic",
        current_price=old_price,
        currency="GBP",
        target_price=target_price,
        scrape_status=ScrapeStatus.OK,
        last_checked_at=OLD_TIME,
    )
    history = PriceHistory(
        product_id=product.id,
        price=new_price,
        currency="GBP",
        change_type=change_type,
        checked_at=NEW_TIME,
    )
    return PriceCheckRecord(
        product=product,
        history=history,
        previous_price=old_price,
        previous_currency="GBP",
        previous_checked_at=OLD_TIME,
        change_type=change_type,
    )


def make_service(
    session_factory: SessionFactory,
    settings: Settings,
    channel: FakeChannel,
) -> NotificationService:
    return NotificationService(
        session_factory,
        [channel],
        lambda: settings,
    )


async def test_price_drop_notification_is_persisted_and_sent(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    channel = FakeChannel()
    service = make_service(web_session_factory, initialized_settings, channel)
    record = make_record(web_session_factory)

    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    notification = notifications[0]
    assert notification.notification_type is NotificationType.PRICE_DROP
    assert notification.old_price == Decimal("51.77")
    assert notification.new_price == Decimal("45.00")
    assert notification.currency == "GBP"
    assert notification.status is NotificationStatus.SENT
    assert notification.sent_at is not None
    assert len(channel.sent) == 1


async def test_duplicate_notification_is_suppressed(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    channel = FakeChannel()
    service = make_service(web_session_factory, initialized_settings, channel)
    record = make_record(web_session_factory)

    await service.process_check(record)
    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    assert len(channel.sent) == 1


async def test_target_crossing_creates_drop_and_target_notifications(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    channel = FakeChannel()
    service = make_service(web_session_factory, initialized_settings, channel)
    record = make_record(
        web_session_factory,
        old_price=Decimal("45.00"),
        new_price=Decimal("39.00"),
        target_price=Decimal("40.00"),
    )

    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 2
    assert {notification.notification_type for notification in notifications} == {
        NotificationType.PRICE_DROP,
        NotificationType.TARGET_REACHED,
    }
    assert all(notification.status is NotificationStatus.SENT for notification in notifications)


async def test_target_is_not_repeated_when_already_below(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    channel = FakeChannel()
    service = make_service(web_session_factory, initialized_settings, channel)
    record = make_record(
        web_session_factory,
        old_price=Decimal("39.00"),
        new_price=Decimal("38.00"),
        target_price=Decimal("40.00"),
    )

    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    assert notifications[0].notification_type is NotificationType.PRICE_DROP


async def test_failed_notification_is_retried(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    channel = FakeChannel(fail=True)
    service = make_service(web_session_factory, initialized_settings, channel)
    record = make_record(web_session_factory)

    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    assert notifications[0].status is NotificationStatus.FAILED
    assert notifications[0].attempts == 1

    channel.fail = False
    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    assert notifications[0].status is NotificationStatus.SENT
    assert notifications[0].attempts == 2
    assert len(channel.sent) == 1


async def test_no_enabled_channels_marks_notification_skipped(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    service = NotificationService(
        web_session_factory,
        [],
        lambda: initialized_settings,
    )
    record = make_record(web_session_factory)

    await service.process_check(record)

    with web_session_factory() as session:
        notifications = NotificationRepository(session).list_for_product(record.product.id)

    assert len(notifications) == 1
    assert notifications[0].status is NotificationStatus.SKIPPED
