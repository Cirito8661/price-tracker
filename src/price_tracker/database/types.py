"""Custom SQLAlchemy types for decimal prices and UTC timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import DateTime, String
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator

_MAX_FRACTIONAL_DIGITS = 4
_MAX_ABS_VALUE = Decimal("999999999999.9999")


def parse_decimal(value: Any) -> Decimal:
    """Validate and return a non-negative decimal value."""

    if isinstance(value, bool):
        raise TypeError("boolean values are not valid decimal prices")
    if isinstance(value, float):
        raise TypeError("float values are not allowed for decimal prices")

    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValueError("value must be a valid decimal number") from exc
    else:
        raise TypeError("value must be a Decimal, int, or numeric string")

    if not decimal_value.is_finite():
        raise ValueError("decimal value must be finite")
    if decimal_value < 0:
        raise ValueError("decimal value must not be negative")
    if abs(decimal_value) > _MAX_ABS_VALUE:
        raise ValueError("decimal value is too large")

    exponent = decimal_value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -_MAX_FRACTIONAL_DIGITS:
        raise ValueError(
            f"decimal value must have at most {_MAX_FRACTIONAL_DIGITS} fractional digits"
        )

    return decimal_value


def canonical_decimal(value: Any) -> str:
    """Return the canonical text representation of a validated decimal."""

    decimal_value = parse_decimal(value)
    if decimal_value == 0:
        return "0"
    return format(decimal_value.normalize(), "f")


class DecimalText(TypeDecorator):
    """Store a non-negative decimal as canonical text.

    SQLite has no native decimal type, and its numeric affinity can round-trip
    values through floating point. This type stores a canonical decimal string
    and returns :class:`~decimal.Decimal` values, rejecting floats explicitly.
    """

    impl = String(32)
    cache_ok = True

    def process_bind_param(
        self,
        value: Any,
        dialect: Dialect | None,
    ) -> str | None:
        if value is None:
            return None
        return canonical_decimal(value)

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect | None,
    ) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @property
    def python_type(self) -> type[Decimal]:
        return Decimal


class UtcDateTime(TypeDecorator):
    """Store timezone-aware datetimes as naive UTC and return aware UTC."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(
        self,
        value: Any,
        dialect: Dialect | None,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("value must be a datetime")
        if value.tzinfo is None:
            raise ValueError("datetime values must be timezone-aware")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(
        self,
        value: Any,
        dialect: Dialect | None,
    ) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise TypeError("database value must be a datetime")
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @property
    def python_type(self) -> type[datetime]:
        return datetime
