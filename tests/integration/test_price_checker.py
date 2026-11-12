"""PriceChecker concurrency and failure tests."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from price_tracker.config import Settings
from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import PriceChangeType, ScrapeStatus
from price_tracker.scraper.base import ScrapedProduct
from price_tracker.scraper.errors import NavigationError
from price_tracker.services.price_checker import (
    PriceChecker,
    PriceCheckStatus,
)
from tests.web_helpers import create_history, create_product

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NEW_TIME = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


class FakeScraper:
    def __init__(self, result=None, error=None, gate=None) -> None:
        self.result = result
        self.error = error
        self.gate = gate

    async def scrape(self, url: str) -> ScrapedProduct:
        if self.gate is not None:
            await self.gate()
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


def make_scraped(price: Decimal = Decimal("45.00")) -> ScrapedProduct:
    return ScrapedProduct(
        name="A Light in the Attic",
        price=price,
        currency="GBP",
        url="https://books.toscrape.com/catalogue/item.html",
        store="books_toscrape",
        retrieved_at=NEW_TIME,
    )


async def test_busy_check_returns_busy(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    product = create_product(
        web_session_factory,
        name="A Light in the Attic",
        current_price=Decimal("51.77"),
        currency="GBP",
        scrape_status=ScrapeStatus.OK,
        last_checked_at=OLD_TIME,
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def gate() -> None:
        started.set()
        await release.wait()

    checker = PriceChecker(
        FakeScraper(result=make_scraped(), gate=gate),
        web_session_factory,
        initialized_settings,
    )

    task = asyncio.create_task(checker.check_product(product.id))
    await asyncio.wait_for(started.wait(), timeout=2)

    busy = await checker.check_product(product.id)
    assert busy.status is PriceCheckStatus.BUSY

    release.set()
    result = await asyncio.wait_for(task, timeout=5)

    assert result.status is PriceCheckStatus.SUCCESS
    assert result.record is not None
    assert result.record.change_type is PriceChangeType.DECREASE


async def test_missing_product_returns_not_found(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    checker = PriceChecker(
        FakeScraper(result=make_scraped()),
        web_session_factory,
        initialized_settings,
    )

    result = await checker.check_product(99999)

    assert result.status is PriceCheckStatus.NOT_FOUND


async def test_failed_check_preserves_valid_data(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    product = create_product(
        web_session_factory,
        name="A Light in the Attic",
        current_price=Decimal("51.77"),
        currency="GBP",
        scrape_status=ScrapeStatus.OK,
        last_checked_at=OLD_TIME,
    )
    create_history(web_session_factory, product, price=Decimal("51.77"))
    checker = PriceChecker(
        FakeScraper(error=NavigationError("Timed out while loading.")),
        web_session_factory,
        initialized_settings,
    )

    result = await checker.check_product(product.id)

    assert result.status is PriceCheckStatus.FAILED
    assert result.error is not None
    with web_session_factory() as session:
        updated = session.get(type(product), product.id)
        assert updated is not None
        assert updated.name == "A Light in the Attic"
        assert updated.current_price == Decimal("51.77")
        assert updated.currency == "GBP"
        assert updated.last_checked_at == OLD_TIME
        assert updated.scrape_status is ScrapeStatus.ERROR
        assert updated.last_error is not None
