"""SMTP email channel tests using a fake SMTP client."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import ClassVar

import pytest
from pydantic import SecretStr

from price_tracker.config import Settings
from price_tracker.models.enums import NotificationStatus, NotificationType
from price_tracker.models.notification import Notification
from price_tracker.models.product import Product
from price_tracker.notifications.base import NotificationChannelDisabled
from price_tracker.notifications.email import EmailNotifier

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class FakeSMTP:
    instances: ClassVar[list[FakeSMTP]] = []

    def __init__(self, host: str, port: int, timeout: int | None = None) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_args: tuple[str, str] | None = None
        self.message = None
        FakeSMTP.instances.append(self)

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *args) -> bool:
        return False

    def starttls(self) -> None:
        self.started_tls = True

    def login(self, username: str, password: str) -> None:
        self.login_args = (username, password)

    def send_message(self, message) -> None:
        self.message = message


def configured_settings(settings: Settings, **overrides) -> Settings:
    values = {
        "email_enabled": True,
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_username": "tracker",
        "smtp_password": SecretStr("smtp-secret"),
        "smtp_from": "tracker@example.com",
        "smtp_to": "owner@example.com",
        "smtp_security": "starttls",
        "smtp_timeout_seconds": 15,
    }
    values.update(overrides)
    return settings.model_copy(update=values)


def make_product() -> Product:
    return Product(
        id=1,
        url="https://books.toscrape.com/catalogue/item.html",
        name="A Light in the Attic",
        store="books_toscrape",
        current_price=Decimal("45.00"),
        currency="GBP",
        target_price=Decimal("40.00"),
    )


def make_notification() -> Notification:
    return Notification(
        id=1,
        product_id=1,
        notification_type=NotificationType.PRICE_DROP,
        old_price=Decimal("51.77"),
        new_price=Decimal("45.00"),
        currency="GBP",
        status=NotificationStatus.PENDING,
        created_at=OLD_TIME,
    )


async def test_starttls_email_delivery(settings: Settings, monkeypatch) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        "price_tracker.notifications.email.smtplib.SMTP",
        FakeSMTP,
    )
    notifier = EmailNotifier(lambda: configured_settings(settings))

    assert notifier.is_enabled() is True
    await notifier.send(make_notification(), make_product())

    assert len(FakeSMTP.instances) == 1
    smtp = FakeSMTP.instances[0]
    assert smtp.host == "smtp.example.com"
    assert smtp.port == 587
    assert smtp.started_tls is True
    assert smtp.login_args == ("tracker", "smtp-secret")
    assert smtp.message is not None
    assert smtp.message["From"] == "tracker@example.com"
    assert smtp.message["To"] == "owner@example.com"
    assert "Price drop" in smtp.message["Subject"]
    body = smtp.message.get_content()
    assert "51.77" in body
    assert "45.00" in body
    assert "A Light in the Attic" in body


async def test_ssl_email_delivery(settings: Settings, monkeypatch) -> None:
    FakeSMTP.instances.clear()
    monkeypatch.setattr(
        "price_tracker.notifications.email.smtplib.SMTP_SSL",
        FakeSMTP,
    )
    notifier = EmailNotifier(lambda: configured_settings(settings, smtp_security="ssl"))

    await notifier.send(make_notification(), make_product())

    smtp = FakeSMTP.instances[0]
    assert smtp.started_tls is False
    assert smtp.login_args == ("tracker", "smtp-secret")


async def test_disabled_email_channel_raises(settings: Settings) -> None:
    notifier = EmailNotifier(lambda: settings)

    assert notifier.is_enabled() is False
    with pytest.raises(NotificationChannelDisabled):
        await notifier.send(make_notification(), make_product())
