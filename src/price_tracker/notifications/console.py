"""Console notification channel."""

from __future__ import annotations

import logging

from ..models.notification import Notification
from ..models.product import Product
from .base import NotificationChannel

logger = logging.getLogger(__name__)


class ConsoleNotifier(NotificationChannel):
    """Write notification events to the application log."""

    name = "console"

    def is_enabled(self) -> bool:
        return True

    async def send(
        self,
        notification: Notification,
        product: Product,
    ) -> None:
        logger.info(
            "Notification [%s] %s: %s -> %s %s",
            notification.notification_type.value,
            product.name or product.url,
            notification.old_price,
            notification.new_price,
            notification.currency,
        )
