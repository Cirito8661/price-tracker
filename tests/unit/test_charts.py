"""Chart data preparation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from price_tracker.models.enums import PriceChangeType
from price_tracker.models.price_history import PriceHistory
from price_tracker.web.charts import build_chart_data


def test_empty_history_uses_labeled_demo_data() -> None:
    chart = build_chart_data([])

    assert chart.is_demo is True
    assert len(chart.labels) == len(chart.values)
    assert chart.labels[0].startswith("Demo")


def test_real_history_is_used_when_available() -> None:
    entry = PriceHistory(
        product_id=1,
        price=Decimal("45.00"),
        currency="GBP",
        change_type=PriceChangeType.DECREASE,
        checked_at=datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
    )

    chart = build_chart_data([entry])

    assert chart.is_demo is False
    assert chart.labels == ["2026-01-02 03:04"]
    assert chart.values == ["45.00"]
