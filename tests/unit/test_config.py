"""Configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from price_tracker.config import Settings


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "data_dir": tmp_path / "data",
        "log_dir": tmp_path / "logs",
        "email_enabled": False,
        "secret_key": "test-secret",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(**values)


def test_defaults(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    assert settings.app_host == "127.0.0.1"
    assert settings.app_port == 8000
    assert settings.check_interval_seconds == 3600
    assert settings.allowed_ports == [80, 443]
    assert settings.allowed_hosts == ["127.0.0.1", "localhost"]
    assert settings.log_level == "WARNING"


def test_check_interval_has_minimum(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, check_interval_seconds=299)


def test_invalid_app_port_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, app_port=70_000)


def test_non_loopback_app_host_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, app_host="0.0.0.0")


def test_loopback_app_hosts_allowed(tmp_path: Path) -> None:
    assert make_settings(tmp_path, app_host="127.0.0.1").app_host == "127.0.0.1"
    assert make_settings(tmp_path, app_host="localhost").app_host == "localhost"
    assert make_settings(tmp_path, app_host="::1").app_host == "::1"


def test_wildcard_allowed_host_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, allowed_hosts=["*"])


def test_invalid_smtp_port_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, smtp_port=0)


def test_empty_allowed_ports_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, allowed_ports=[])


def test_invalid_allowed_port_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, allowed_ports=[80, 70_000])


def test_invalid_log_level_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, log_level="LOUD")


def test_invalid_public_base_url_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(tmp_path, public_base_url="not-a-url")


def test_non_sqlite_database_url_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        make_settings(
            tmp_path,
            database_url="postgresql://user:pass@example.com/db",
        )


def test_database_path_and_url(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    assert settings.database_path == tmp_path / "data" / "price_tracker.db"
    assert settings.effective_database_url.startswith("sqlite+pysqlite:///")
    assert settings.effective_database_url.endswith("price_tracker.db")


def test_database_url_override(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        database_url="sqlite+pysqlite:///:memory:",
    )

    assert settings.effective_database_url == "sqlite+pysqlite:///:memory:"


def test_email_disabled_when_smtp_missing(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, email_enabled=True)

    assert settings.email_configured is False
    assert settings.effective_email_enabled is False
    warning = settings.email_configuration_warning
    assert warning is not None
    assert "PT_SMTP_HOST" in warning
    assert "PT_SMTP_FROM" in warning
    assert "PT_SMTP_TO" in warning


def test_email_enabled_when_configured(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        email_enabled=True,
        smtp_host="smtp.example.com",
        smtp_from="tracker@example.com",
        smtp_to="owner@example.com",
    )

    assert settings.email_configured is True
    assert settings.effective_email_enabled is True
    assert settings.email_configuration_warning is None


def test_email_requires_password_when_username_is_set(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        email_enabled=True,
        smtp_host="smtp.example.com",
        smtp_from="tracker@example.com",
        smtp_to="owner@example.com",
        smtp_username="tracker",
    )

    assert settings.email_configured is False
    assert settings.effective_email_enabled is False
    warning = settings.email_configuration_warning
    assert warning is not None
    assert "PT_SMTP_PASSWORD" in warning


def test_ensure_directories_creates_paths(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    settings.ensure_directories()

    assert settings.data_dir.is_dir()
    assert settings.log_dir.is_dir()


def test_resolve_secret_key_generates_and_reuses(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, secret_key=None)

    first = settings.resolve_secret_key()
    secret_path = tmp_path / "data" / ".secret"
    assert secret_path.exists()
    assert first.get_secret_value()

    second = settings.resolve_secret_key()
    assert second.get_secret_value() == first.get_secret_value()


def test_configured_secret_key_is_used_without_file(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, secret_key="configured-secret")

    resolved = settings.resolve_secret_key()

    assert resolved.get_secret_value() == "configured-secret"
    assert not (tmp_path / "data" / ".secret").exists()


def test_public_base_url_trailing_slash_removed(tmp_path: Path) -> None:
    settings = make_settings(
        tmp_path,
        public_base_url="http://127.0.0.1:8000/",
    )

    assert settings.public_base_url == "http://127.0.0.1:8000"
