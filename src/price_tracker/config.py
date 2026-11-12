"""Application configuration loaded from environment variables and .env."""

from __future__ import annotations

import contextlib
import ipaddress
import secrets
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import __version__

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


class Settings(BaseSettings):
    """Validated runtime settings.

    All values can be provided through environment variables using the ``PT_``
    prefix or through a ``.env`` file in the current working directory.
    """

    model_config = SettingsConfigDict(
        env_prefix="PT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Price Tracker"
    app_version: str = __version__
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    app_debug: bool = False
    public_base_url: str = "http://127.0.0.1:8000"

    data_dir: Path = Path("data")
    log_dir: Path = Path("logs")
    database_url: str | None = None
    secret_key: SecretStr | None = None

    log_level: str = "INFO"

    check_interval_seconds: int = 3600
    recent_decrease_days: int = 7

    scraper_timeout_ms: int = 30_000
    scraper_concurrency: int = 2
    scraper_min_delay_seconds: float = 2.0
    scraper_max_response_bytes: int = 5_000_000
    scraper_user_agent: str = "PriceTracker/0.1 (local portfolio project)"
    allowed_ports: list[int] = Field(default_factory=lambda: [80, 443])
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])

    notification_cooldown_hours: int = 24
    max_notification_attempts: int = 3

    email_enabled: bool = True
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None
    smtp_to: str | None = None
    smtp_security: Literal["starttls", "ssl"] = "starttls"
    smtp_timeout_seconds: int = 15

    @field_validator(
        "database_url",
        "smtp_host",
        "smtp_username",
        "smtp_from",
        "smtp_to",
        mode="before",
    )
    @classmethod
    def _empty_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("secret_key", "smtp_password", mode="before")
    @classmethod
    def _empty_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("app_name", "app_host", "scraper_user_agent")
    @classmethod
    def _non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be empty")
        return stripped

    @field_validator("app_host")
    @classmethod
    def _validate_local_bind_address(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "localhost":
            return normalized
        try:
            address = ipaddress.ip_address(normalized)
        except ValueError as exc:
            raise ValueError("app_host must be localhost or a loopback IP address") from exc
        if not address.is_loopback:
            raise ValueError("app_host must be a loopback address in v1.0")
        return normalized

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        if level not in _VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(_VALID_LOG_LEVELS))
            raise ValueError(f"log_level must be one of: {allowed}")
        return level

    @field_validator("public_base_url")
    @classmethod
    def _validate_public_base_url(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        parsed = urlsplit(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("public_base_url must be an absolute HTTP(S) URL")
        return normalized

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("sqlite"):
            raise ValueError("only SQLite database URLs are supported in v1.0")
        return value

    @field_validator("allowed_ports")
    @classmethod
    def _validate_allowed_ports(cls, value: list[int]) -> list[int]:
        if not value:
            raise ValueError("allowed_ports must not be empty")
        for port in value:
            if not 1 <= port <= 65535:
                raise ValueError("allowed_ports values must be between 1 and 65535")
        return sorted(set(value))

    @field_validator("allowed_hosts")
    @classmethod
    def _validate_allowed_hosts(cls, value: list[str]) -> list[str]:
        hosts = [host.strip().lower() for host in value if host.strip()]
        if not hosts:
            raise ValueError("allowed_hosts must not be empty")
        if "*" in hosts:
            raise ValueError("wildcard allowed_hosts values are not permitted")
        return hosts

    @field_validator("app_port", "smtp_port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return value

    @field_validator("check_interval_seconds")
    @classmethod
    def _validate_check_interval(cls, value: int) -> int:
        if value < 300:
            raise ValueError("check_interval_seconds must be at least 300")
        return value

    @field_validator("recent_decrease_days")
    @classmethod
    def _validate_recent_decrease_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("recent_decrease_days must be at least 1")
        return value

    @field_validator("scraper_timeout_ms")
    @classmethod
    def _validate_scraper_timeout(cls, value: int) -> int:
        if value < 1000:
            raise ValueError("scraper_timeout_ms must be at least 1000")
        return value

    @field_validator("scraper_concurrency")
    @classmethod
    def _validate_scraper_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("scraper_concurrency must be at least 1")
        return value

    @field_validator("scraper_min_delay_seconds")
    @classmethod
    def _validate_scraper_min_delay(cls, value: float) -> float:
        if value < 0:
            raise ValueError("scraper_min_delay_seconds must not be negative")
        return value

    @field_validator("scraper_max_response_bytes")
    @classmethod
    def _validate_max_response_bytes(cls, value: int) -> int:
        if value < 1024:
            raise ValueError("scraper_max_response_bytes must be at least 1024")
        return value

    @field_validator("notification_cooldown_hours")
    @classmethod
    def _validate_notification_cooldown(cls, value: int) -> int:
        if value < 0:
            raise ValueError("notification_cooldown_hours must not be negative")
        return value

    @field_validator("max_notification_attempts")
    @classmethod
    def _validate_notification_attempts(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_notification_attempts must be at least 1")
        return value

    @field_validator("smtp_timeout_seconds")
    @classmethod
    def _validate_smtp_timeout(cls, value: int) -> int:
        if value < 1:
            raise ValueError("smtp_timeout_seconds must be at least 1")
        return value

    @field_validator("smtp_from", "smtp_to")
    @classmethod
    def _validate_email_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        address = value.strip()
        local_part, separator, domain = address.partition("@")
        if not separator or not local_part or not domain or " " in address:
            raise ValueError("value must be a valid email address")
        return address

    @property
    def database_path(self) -> Path:
        """Default SQLite database path."""

        return self.data_dir / "price_tracker.db"

    @property
    def effective_database_url(self) -> str:
        """Database URL, defaulting to a local SQLite file."""

        if self.database_url:
            return self.database_url
        return f"sqlite+pysqlite:///{self.database_path.as_posix()}"

    @property
    def allowed_origins(self) -> set[str]:
        """Origins accepted for state-changing browser requests."""

        origins = {self.public_base_url}
        for host in ("127.0.0.1", "localhost", "[::1]"):
            origins.add(f"http://{host}:{self.app_port}")
        return origins

    @property
    def email_configured(self) -> bool:
        """Whether all required SMTP values are present."""

        if not self.smtp_host or not self.smtp_from or not self.smtp_to:
            return False
        return not (self.smtp_username and self.smtp_password is None)

    @property
    def effective_email_enabled(self) -> bool:
        """Whether email notifications can actually be used."""

        return self.email_enabled and self.email_configured

    @property
    def email_configuration_warning(self) -> str | None:
        """Return a safe warning when email is enabled but incomplete."""

        if not self.email_enabled:
            return None

        missing: list[str] = []
        if not self.smtp_host:
            missing.append("PT_SMTP_HOST")
        if not self.smtp_from:
            missing.append("PT_SMTP_FROM")
        if not self.smtp_to:
            missing.append("PT_SMTP_TO")
        if self.smtp_username and self.smtp_password is None:
            missing.append("PT_SMTP_PASSWORD")

        if missing:
            return "Email notifications are disabled; missing configuration: " + ", ".join(missing)
        return None

    def ensure_directories(self) -> None:
        """Create runtime data and log directories when missing."""

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def resolve_secret_key(self) -> SecretStr:
        """Return the configured secret or load/create ``data/.secret``."""

        if self.secret_key is not None:
            value = self.secret_key.get_secret_value().strip()
            if value:
                return SecretStr(value)

        secret_path = self.data_dir / ".secret"
        if secret_path.exists():
            value = secret_path.read_text(encoding="utf-8").strip()
            if value:
                return SecretStr(value)

        value = secrets.token_urlsafe(48)
        secret_path.parent.mkdir(parents=True, exist_ok=True)
        secret_path.write_text(value + "\n", encoding="utf-8")
        with contextlib.suppress(OSError):
            secret_path.chmod(0o600)
        return SecretStr(value)
