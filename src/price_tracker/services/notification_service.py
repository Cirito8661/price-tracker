"""Notification evaluation, deduplication, persistence, and delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal

from ..clock import utcnow
from ..config import Settings
from ..database.session import SessionFactory
from ..models.enums import (
    NotificationStatus,
    NotificationType,
    PriceChangeType,
)
from ..models.notification import Notification
from ..models.product import Product
from ..notifications.base import NotificationChannel, NotificationChannelDisabled
from ..repositories.notifications import NotificationRepository
from .product_service import PriceCheckRecord

logger = logging.getLogger(__name__)


class NotificationService:
    """Create and deliver notifications for successful price checks."""

    def __init__(
        self,
        session_factory: SessionFactory,
        channels: list[NotificationChannel],
        settings_provider: Callable[[], Settings],
    ) -> None:
        self.session_factory = session_factory
        self.channels = channels
        self._settings_provider = settings_provider

    async def process_check(self, record: PriceCheckRecord) -> None:
        """Retry open notifications and evaluate new price conditions."""

        notifications = await asyncio.to_thread(self._prepare, record)
        for notification in notifications:
            await self._deliver(notification, record.product)

    def _prepare(self, record: PriceCheckRecord) -> list[Notification]:
        settings = self._settings_provider()
        product_id = record.product.id

        with self.session_factory() as session:
            repository = NotificationRepository(session)
            retryable = repository.find_retryable(
                product_id,
                max_attempts=settings.max_notification_attempts,
            )
            created: list[Notification] = []

            if (
                record.change_type is PriceChangeType.DECREASE
                and record.previous_price is not None
                and not self._is_duplicate(
                    repository,
                    product_id,
                    NotificationType.PRICE_DROP,
                    record.history.price,
                    settings,
                    retryable,
                )
            ):
                created.append(
                    self._create(
                        repository,
                        record,
                        NotificationType.PRICE_DROP,
                    )
                )

            target_price = record.product.target_price
            if (
                target_price is not None
                and record.previous_price is not None
                and record.previous_currency == record.history.currency
                and record.previous_price > target_price >= record.history.price
                and not self._is_duplicate(
                    repository,
                    product_id,
                    NotificationType.TARGET_REACHED,
                    record.history.price,
                    settings,
                    retryable,
                )
            ):
                created.append(
                    self._create(
                        repository,
                        record,
                        NotificationType.TARGET_REACHED,
                    )
                )

            session.commit()
            return retryable + created

    def _create(
        self,
        repository: NotificationRepository,
        record: PriceCheckRecord,
        notification_type: NotificationType,
    ) -> Notification:
        notification = Notification(
            product_id=record.product.id,
            notification_type=notification_type,
            old_price=record.previous_price,
            new_price=record.history.price,
            currency=record.history.currency,
            status=NotificationStatus.PENDING,
            attempts=0,
            created_at=utcnow(),
        )
        repository.add(notification)
        return notification

    def _is_duplicate(
        self,
        repository: NotificationRepository,
        product_id: int,
        notification_type: NotificationType,
        new_price: Decimal,
        settings: Settings,
        retryable: list[Notification],
    ) -> bool:
        if any(
            notification.notification_type == notification_type
            and notification.new_price == new_price
            for notification in retryable
        ):
            return True

        sent = repository.find_sent_with_price(
            product_id,
            notification_type,
            new_price,
        )
        if sent is None:
            return False
        cutoff = utcnow() - timedelta(hours=settings.notification_cooldown_hours)
        return sent.created_at >= cutoff

    async def _deliver(
        self,
        notification: Notification,
        product: Product,
    ) -> None:
        enabled_channels = [channel for channel in self.channels if channel.is_enabled()]
        if not enabled_channels:
            await asyncio.to_thread(
                self._update,
                notification.id,
                NotificationStatus.SKIPPED,
                notification.attempts + 1,
                None,
                "No notification channels are enabled.",
            )
            return

        successes = 0
        errors: list[str] = []
        for channel in enabled_channels:
            try:
                await channel.send(notification, product)
            except NotificationChannelDisabled:
                continue
            except Exception as exc:
                logger.exception(
                    "Notification channel %s failed for product %s",
                    channel.name,
                    product.id,
                )
                errors.append(f"{channel.name}: {type(exc).__name__}")
            else:
                successes += 1

        status = NotificationStatus.SENT if successes else NotificationStatus.FAILED
        sent_at = utcnow() if successes else None
        error_message = "; ".join(errors) or None
        await asyncio.to_thread(
            self._update,
            notification.id,
            status,
            notification.attempts + 1,
            sent_at,
            error_message,
        )

    def _update(
        self,
        notification_id: int,
        status: NotificationStatus,
        attempts: int,
        sent_at: datetime | None,
        error_message: str | None,
    ) -> None:
        with self.session_factory() as session:
            repository = NotificationRepository(session)
            notification = repository.get(notification_id)
            if notification is None:
                return
            notification.status = status
            notification.attempts = attempts
            notification.sent_at = sent_at
            notification.error_message = error_message
            session.commit()
