"""Editable runtime settings persisted outside the database schema."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from .config import Settings

logger = logging.getLogger(__name__)


class RuntimeSettings(BaseModel):
    """User-editable scheduler and email settings."""

    model_config = ConfigDict(extra="ignore")

    check_interval_seconds: int = 3600
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

    @field_validator("smtp_password", mode="before")
    @classmethod
    def _empty_password_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("check_interval_seconds")
    @classmethod
    def _validate_interval(cls, value: int) -> int:
        if value < 300:
            raise ValueError("check_interval_seconds must be at least 300")
        return value

    @field_validator("smtp_port")
    @classmethod
    def _validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("smtp_port must be between 1 and 65535")
        return value

    @field_validator("smtp_timeout_seconds")
    @classmethod
    def _validate_timeout(cls, value: int) -> int:
        if value < 1:
            raise ValueError("smtp_timeout_seconds must be at least 1")
        return value

    @field_validator("smtp_from", "smtp_to")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        local_part, separator, domain = value.partition("@")
        if not separator or not local_part or not domain or " " in value:
            raise ValueError("value must be a valid email address")
        return value

    @classmethod
    def from_settings(cls, settings: Settings) -> RuntimeSettings:
        return cls(
            check_interval_seconds=settings.check_interval_seconds,
            email_enabled=settings.email_enabled,
            smtp_host=settings.smtp_host,
            smtp_port=settings.smtp_port,
            smtp_username=settings.smtp_username,
            smtp_password=settings.smtp_password,
            smtp_from=settings.smtp_from,
            smtp_to=settings.smtp_to,
            smtp_security=settings.smtp_security,
            smtp_timeout_seconds=settings.smtp_timeout_seconds,
        )


class RuntimeSettingsStore:
    """Load, apply, and atomically persist runtime setting overrides."""

    def __init__(self, path: Path, base_settings: Settings) -> None:
        self.path = path
        self._base_settings = base_settings
        self._runtime = self._load()

    @property
    def runtime(self) -> RuntimeSettings:
        return self._runtime

    @property
    def password_configured(self) -> bool:
        return self._runtime.smtp_password is not None

    @property
    def effective_settings(self) -> Settings:
        runtime = self._runtime
        return self._base_settings.model_copy(
            update={
                "check_interval_seconds": runtime.check_interval_seconds,
                "email_enabled": runtime.email_enabled,
                "smtp_host": runtime.smtp_host,
                "smtp_port": runtime.smtp_port,
                "smtp_username": runtime.smtp_username,
                "smtp_password": runtime.smtp_password,
                "smtp_from": runtime.smtp_from,
                "smtp_to": runtime.smtp_to,
                "smtp_security": runtime.smtp_security,
                "smtp_timeout_seconds": runtime.smtp_timeout_seconds,
            }
        )

    def save(self, runtime: RuntimeSettings) -> None:
        """Persist settings atomically with owner-only permissions."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = runtime.model_dump()
        data["smtp_password"] = (
            runtime.smtp_password.get_secret_value() if runtime.smtp_password is not None else None
        )
        temporary_path = self.path.with_name(self.path.name + ".tmp")
        temporary_path.write_text(
            json.dumps(data, indent=2) + "\n",
            encoding="utf-8",
        )
        with contextlib.suppress(OSError):
            temporary_path.chmod(0o600)
        temporary_path.replace(self.path)
        self._runtime = runtime

    def _load(self) -> RuntimeSettings:
        if not self.path.exists():
            return RuntimeSettings.from_settings(self._base_settings)
        try:
            return RuntimeSettings.model_validate_json(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Could not load runtime settings (%s); using base settings.",
                type(exc).__name__,
            )
            return RuntimeSettings.from_settings(self._base_settings)
