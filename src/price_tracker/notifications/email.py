"""SMTP email notification channel."""

from __future__ import annotations

import asyncio
import smtplib
from collections.abc import Callable
from email.message import EmailMessage

from ..config import Settings
from ..models.notification import Notification
from ..models.product import Product
from .base import (
    NotificationChannel,
    NotificationChannelDisabled,
    NotificationChannelError,
)


class EmailNotifier(NotificationChannel):
    """Send notification events over SMTP."""

    name = "email"

    def __init__(self, settings_provider: Callable[[], Settings]) -> None:
        self._settings_provider = settings_provider

    def is_enabled(self) -> bool:
        return self._settings_provider().effective_email_enabled

    async def send(
        self,
        notification: Notification,
        product: Product,
    ) -> None:
        settings = self._settings_provider()
        if not settings.effective_email_enabled:
            raise NotificationChannelDisabled("Email notifications are not configured.")
        await asyncio.to_thread(
            self._send_sync,
            settings,
            notification,
            product,
        )

    def _send_sync(
        self,
        settings: Settings,
        notification: Notification,
        product: Product,
    ) -> None:
        if settings.smtp_host is None or settings.smtp_from is None or settings.smtp_to is None:
            raise NotificationChannelDisabled("Email notifications are not configured.")

        product_name = " ".join((product.name or product.url).split())[:100]
        subject_prefix = (
            "Target price reached"
            if notification.notification_type.value == "target_reached"
            else "Price drop"
        )
        target_line = (
            f"\nTarget price: {product.target_price} {notification.currency}"
            if product.target_price is not None
            else ""
        )
        body = (
            f"Product: {product.name or product.url}\n"
            f"Store: {product.store}\n"
            f"URL: {product.url}\n"
            f"Old price: {notification.old_price} {notification.currency}\n"
            f"New price: {notification.new_price} {notification.currency}\n"
            f"Condition: {notification.notification_type.value}\n"
            f"{target_line}\n"
            f"Checked at: {notification.created_at.isoformat()}\n"
        )

        message = EmailMessage()
        message["Subject"] = f"{subject_prefix}: {product_name}"
        message["From"] = settings.smtp_from
        message["To"] = settings.smtp_to
        message.set_content(body)

        password = (
            settings.smtp_password.get_secret_value()
            if settings.smtp_password is not None
            else None
        )

        try:
            if settings.smtp_security == "ssl":
                smtp_client = smtplib.SMTP_SSL(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                )
                with smtp_client as smtp:
                    if settings.smtp_username is not None:
                        smtp.login(settings.smtp_username, password or "")
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(
                    settings.smtp_host,
                    settings.smtp_port,
                    timeout=settings.smtp_timeout_seconds,
                ) as smtp:
                    smtp.starttls()
                    if settings.smtp_username is not None:
                        smtp.login(settings.smtp_username, password or "")
                    smtp.send_message(message)
        except Exception as exc:
            raise NotificationChannelError(f"SMTP delivery failed ({type(exc).__name__}).") from exc
