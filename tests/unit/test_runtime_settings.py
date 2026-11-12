"""Runtime settings persistence tests."""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr, ValidationError

from price_tracker.config import Settings
from price_tracker.runtime_settings import RuntimeSettings, RuntimeSettingsStore


def test_defaults_come_from_base_settings(settings: Settings) -> None:
    store = RuntimeSettingsStore(
        settings.data_dir / "runtime_settings.json",
        settings,
    )

    assert store.runtime.check_interval_seconds == settings.check_interval_seconds
    assert store.runtime.email_enabled == settings.email_enabled
    assert store.effective_settings.check_interval_seconds == 3600


def test_save_and_reload_applies_overrides(settings: Settings) -> None:
    path = settings.data_dir / "runtime_settings.json"
    store = RuntimeSettingsStore(path, settings)
    runtime = store.runtime.model_copy(
        update={
            "check_interval_seconds": 600,
            "email_enabled": True,
            "smtp_host": "smtp.example.com",
            "smtp_from": "tracker@example.com",
            "smtp_to": "owner@example.com",
        }
    )

    store.save(runtime)

    reloaded = RuntimeSettingsStore(path, settings)
    assert reloaded.runtime.check_interval_seconds == 600
    assert reloaded.effective_settings.check_interval_seconds == 600
    assert reloaded.effective_settings.email_configured is True
    assert reloaded.effective_settings.effective_email_enabled is True


def test_password_is_persisted_and_reported(settings: Settings) -> None:
    path = settings.data_dir / "runtime_settings.json"
    store = RuntimeSettingsStore(path, settings)
    runtime = store.runtime.model_copy(update={"smtp_password": SecretStr("local-secret")})

    store.save(runtime)

    reloaded = RuntimeSettingsStore(path, settings)
    assert reloaded.password_configured is True
    assert (
        reloaded.runtime.smtp_password is not None
        and reloaded.runtime.smtp_password.get_secret_value() == "local-secret"
    )


def test_invalid_file_falls_back_to_base_settings(settings: Settings) -> None:
    path = settings.data_dir / "runtime_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not valid json", encoding="utf-8")

    store = RuntimeSettingsStore(path, settings)

    assert store.runtime.check_interval_seconds == settings.check_interval_seconds


def test_malformed_runtime_settings_do_not_log_password(
    settings: Settings,
    caplog: pytest.LogCaptureFixture,
) -> None:
    path = settings.data_dir / "runtime_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    fake_password = "FAKE-SMTP-PASSWORD-DO-NOT-LOG"
    path.write_text(
        '{"smtp_password": "' + fake_password + '", "check_interval_seconds":',
        encoding="utf-8",
    )
    with caplog.at_level(
        logging.WARNING,
        logger="price_tracker.runtime_settings",
    ):
        store = RuntimeSettingsStore(path, settings)

    assert store.runtime.check_interval_seconds == settings.check_interval_seconds
    assert "Could not load runtime settings" in caplog.text
    assert "ValidationError" in caplog.text
    assert fake_password not in caplog.text


@pytest.mark.parametrize(
    "overrides",
    [
        {"check_interval_seconds": 10},
        {"smtp_port": 0},
        {"smtp_timeout_seconds": 0},
        {"smtp_from": "not-an-email"},
        {"smtp_security": "plain"},
    ],
)
def test_invalid_runtime_settings_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        RuntimeSettings(**overrides)
