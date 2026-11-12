"""Notification repository."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.enums import NotificationStatus, NotificationType
from ..models.notification import Notification


class NotificationRepository:
    """Persistence and deduplication queries for notifications."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, notification: Notification) -> Notification:
        self.session.add(notification)
        self.session.flush()
        return notification

    def get(self, notification_id: int) -> Notification | None:
        return self.session.get(Notification, notification_id)

    def list_for_product(
        self,
        product_id: int,
        *,
        limit: int = 50,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(Notification.product_id == product_id)
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def latest_sent(
        self,
        product_id: int,
        notification_type: NotificationType,
    ) -> Notification | None:
        statement = (
            select(Notification)
            .where(
                Notification.product_id == product_id,
                Notification.notification_type == notification_type,
                Notification.status == NotificationStatus.SENT,
            )
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def find_sent_with_price(
        self,
        product_id: int,
        notification_type: NotificationType,
        new_price: Decimal,
    ) -> Notification | None:
        statement = (
            select(Notification)
            .where(
                Notification.product_id == product_id,
                Notification.notification_type == notification_type,
                Notification.status == NotificationStatus.SENT,
                Notification.new_price == new_price,
            )
            .order_by(
                Notification.created_at.desc(),
                Notification.id.desc(),
            )
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def find_retryable(
        self,
        product_id: int,
        *,
        max_attempts: int,
    ) -> list[Notification]:
        statement = (
            select(Notification)
            .where(
                Notification.product_id == product_id,
                Notification.status.in_(
                    [
                        NotificationStatus.PENDING,
                        NotificationStatus.FAILED,
                    ]
                ),
                Notification.attempts < max_attempts,
            )
            .order_by(Notification.created_at.asc(), Notification.id.asc())
        )
        return list(self.session.scalars(statement))

    def count_for_product(self, product_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.product_id == product_id)
        )
        return int(self.session.scalar(statement) or 0)
