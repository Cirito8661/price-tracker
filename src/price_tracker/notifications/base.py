"""Notification channel interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..models.notification import Notification
from ..models.product import Product


class NotificationChannelError(Exception):
    """Raised when a notification channel cannot deliver a message."""


class NotificationChannelDisabled(NotificationChannelError):
    """Raised when a channel is not configured or enabled."""


class NotificationChannel(ABC):
    """Interface implemented by notification delivery channels."""

    name: ClassVar[str]

    @abstractmethod
    def is_enabled(self) -> bool:
        """Return whether the channel is currently configured."""

    @abstractmethod
    async def send(
        self,
        notification: Notification,
        product: Product,
    ) -> None:
        """Deliver one notification or raise a channel error."""
