"""Chart data preparation for product detail pages."""

from __future__ import annotations

from dataclasses import dataclass

from ..models.price_history import PriceHistory

DEMO_CHART_LABELS = ["Demo 1", "Demo 2", "Demo 3", "Demo 4", "Demo 5", "Demo 6", "Demo 7"]
DEMO_CHART_VALUES = ["52.00", "51.50", "49.99", "50.25", "47.80", "46.50", "45.99"]


@dataclass(frozen=True)
class ChartData:
    """Labels and values passed to the local Chart.js instance."""

    labels: list[str]
    values: list[str]
    is_demo: bool


def build_chart_data(history: list[PriceHistory]) -> ChartData:
    """Use real history when available, otherwise clearly labeled demo data."""

    if not history:
        return ChartData(
            labels=DEMO_CHART_LABELS,
            values=DEMO_CHART_VALUES,
            is_demo=True,
        )

    return ChartData(
        labels=[entry.checked_at.strftime("%Y-%m-%d %H:%M") for entry in history],
        values=[str(entry.price) for entry in history],
        is_demo=False,
    )
