"""Unit tests for DecimalText and UtcDateTime."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from price_tracker.database.types import DecimalText, UtcDateTime


def test_decimal_bind_canonicalizes_values() -> None:
    decimal_type = DecimalText()

    assert decimal_type.process_bind_param(Decimal("10.00"), None) == "10"
    assert decimal_type.process_bind_param(Decimal("10.50"), None) == "10.5"
    assert decimal_type.process_bind_param(Decimal("0.0000"), None) == "0"
    assert decimal_type.process_bind_param(Decimal("0.0001"), None) == "0.0001"
    assert decimal_type.process_bind_param(Decimal("1000.00"), None) == "1000"
    assert decimal_type.process_bind_param(10, None) == "10"
    assert decimal_type.process_bind_param("10.50", None) == "10.5"
    assert decimal_type.process_bind_param(None, None) is None


def test_decimal_bind_normalizes_negative_zero() -> None:
    assert DecimalText().process_bind_param(Decimal("-0"), None) == "0"


@pytest.mark.parametrize("value", [1.5, True, False])
def test_decimal_rejects_float_and_bool(value: object) -> None:
    with pytest.raises(TypeError):
        DecimalText().process_bind_param(value, None)


@pytest.mark.parametrize(
    "value",
    [
        "not-a-number",
        "NaN",
        "Infinity",
        "-Infinity",
        "-1",
        "1.23456",
        "1000000000000",
    ],
)
def test_decimal_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        DecimalText().process_bind_param(value, None)


def test_decimal_result_returns_decimal() -> None:
    decimal_type = DecimalText()

    assert decimal_type.process_result_value("10.5", None) == Decimal("10.5")
    assert decimal_type.process_result_value(None, None) is None


def test_utc_bind_converts_aware_datetime_to_naive_utc() -> None:
    source = datetime(
        2026,
        1,
        2,
        5,
        4,
        5,
        tzinfo=timezone(timedelta(hours=2)),
    )

    result = UtcDateTime().process_bind_param(source, None)

    assert result == datetime(2026, 1, 2, 3, 4, 5)
    assert result is not None
    assert result.tzinfo is None


def test_utc_bind_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        UtcDateTime().process_bind_param(datetime(2026, 1, 2), None)


def test_utc_result_attaches_utc() -> None:
    result = UtcDateTime().process_result_value(
        datetime(2026, 1, 2, 3, 4, 5),
        None,
    )

    assert result == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert result is not None
    assert result.tzinfo is UTC


def test_utc_result_converts_aware_datetime_to_utc() -> None:
    result = UtcDateTime().process_result_value(
        datetime(2026, 1, 2, 5, 4, 5, tzinfo=timezone(timedelta(hours=2))),
        None,
    )

    assert result == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_utc_none_roundtrip() -> None:
    utc_type = UtcDateTime()

    assert utc_type.process_bind_param(None, None) is None
    assert utc_type.process_result_value(None, None) is None
