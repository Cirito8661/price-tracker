"""Price summary display tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from price_tracker.models.enums import PriceChangeType, ScrapeStatus
from price_tracker.models.price_history import PriceHistory
from price_tracker.models.product import Product
from price_tracker.web.price_summary import build_price_summary

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NEW_TIME = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def make_product(
    *,
    current_price: Decimal | None = Decimal("51.77"),
    currency: str | None = "GBP",
    last_checked_at: datetime | None = OLD_TIME,
) -> Product:
    return Product(
        id=1,
        url="https://books.toscrape.com/catalogue/item.html",
        name="A Light in the Attic",
        store="books_toscrape",
        current_price=current_price,
        currency=currency,
        scrape_status=ScrapeStatus.OK,
        last_checked_at=last_checked_at,
    )


def make_history(
    price: Decimal,
    change_type: PriceChangeType,
    checked_at: datetime,
    currency: str = "GBP",
) -> PriceHistory:
    return PriceHistory(
        product_id=1,
        price=price,
        currency=currency,
        change_type=change_type,
        checked_at=checked_at,
    )


def test_summary_without_history_uses_product_fields() -> None:
    summary = build_price_summary(make_product(), [])

    assert summary.latest_price == Decimal("51.77")
    assert summary.latest_currency == "GBP"
    assert summary.latest_checked_at == OLD_TIME
    assert summary.previous_price is None
    assert summary.change_type is None
    assert summary.change_amount is None


def test_summary_with_single_initial_history() -> None:
    history = [make_history(Decimal("51.77"), PriceChangeType.INITIAL, OLD_TIME)]

    summary = build_price_summary(make_product(), history)

    assert summary.latest_price == Decimal("51.77")
    assert summary.previous_price is None
    assert summary.change_type is PriceChangeType.INITIAL
    assert summary.change_amount is None


def test_summary_with_decrease() -> None:
    history = [
        make_history(Decimal("51.77"), PriceChangeType.INITIAL, OLD_TIME),
        make_history(Decimal("45.00"), PriceChangeType.DECREASE, NEW_TIME),
    ]

    summary = build_price_summary(make_product(), history)

    assert summary.latest_price == Decimal("45.00")
    assert summary.previous_price == Decimal("51.77")
    assert summary.change_type is PriceChangeType.DECREASE
    assert summary.change_amount == Decimal("-6.77")


def test_summary_with_currency_change_has_no_amount() -> None:
    history = [
        make_history(Decimal("51.77"), PriceChangeType.INITIAL, OLD_TIME),
        make_history(
            Decimal("45.00"),
            PriceChangeType.CURRENCY_CHANGED,
            NEW_TIME,
            currency="USD",
        ),
    ]

    summary = build_price_summary(make_product(), history)

    assert summary.latest_price == Decimal("45.00")
    assert summary.latest_currency == "USD"
    assert summary.previous_price == Decimal("51.77")
    assert summary.change_type is PriceChangeType.CURRENCY_CHANGED
    assert summary.change_amount is None
