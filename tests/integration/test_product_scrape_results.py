"""Product scrape persistence and preservation tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from price_tracker.models.enums import ScrapeStatus
from price_tracker.models.product import Product
from price_tracker.scraper.base import ScrapedProduct
from price_tracker.services.product_service import (
    PreparedProduct,
    ProductService,
    ProductValidationError,
)

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NEW_TIME = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)


def make_existing_product() -> Product:
    return Product(
        url="https://books.toscrape.com/catalogue/existing.html",
        name="Existing product",
        store="books_toscrape",
        current_price=Decimal("10.00"),
        currency="GBP",
        target_price=Decimal("8.00"),
        scrape_status=ScrapeStatus.OK,
        last_checked_at=OLD_TIME,
    )


def test_failed_scrape_preserves_existing_valid_data(db_session: Session) -> None:
    product = make_existing_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)

    service.apply_scrape_result(
        product.id,
        None,
        "Timed out while loading the product page.",
    )

    assert product.name == "Existing product"
    assert product.current_price == Decimal("10.00")
    assert product.currency == "GBP"
    assert product.store == "books_toscrape"
    assert product.last_checked_at == OLD_TIME
    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.last_error == "Timed out while loading the product page."
    assert product.last_attempt_at is not None


def test_successful_scrape_updates_existing_product(db_session: Session) -> None:
    product = make_existing_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)
    scraped = ScrapedProduct(
        name="Updated product",
        price=Decimal("9.00"),
        currency="GBP",
        url=product.url,
        store="books_toscrape",
        retrieved_at=NEW_TIME,
    )

    service.apply_scrape_result(product.id, scraped, None)

    assert product.name == "Updated product"
    assert product.current_price == Decimal("9.00")
    assert product.currency == "GBP"
    assert product.store == "books_toscrape"
    assert product.scrape_status is ScrapeStatus.OK
    assert product.last_error is None
    assert product.last_checked_at == NEW_TIME
    assert product.last_attempt_at == NEW_TIME


def test_failed_initial_scrape_persists_error_state(db_session: Session) -> None:
    service = ProductService(db_session)
    prepared = PreparedProduct(
        url="https://books.toscrape.com/catalogue/new-failure.html",
        store="books_toscrape",
        target_price=Decimal("5.00"),
    )

    product = service.persist_new_product(
        prepared,
        None,
        "The store returned HTTP 503.",
    )

    assert product.name is None
    assert product.current_price is None
    assert product.currency is None
    assert product.store == "books_toscrape"
    assert product.target_price == Decimal("5.00")
    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.last_error == "The store returned HTTP 503."
    assert product.last_checked_at is None
    assert product.last_attempt_at is not None


def test_successful_initial_scrape_populates_product(db_session: Session) -> None:
    service = ProductService(db_session)
    prepared = PreparedProduct(
        url="https://books.toscrape.com/catalogue/new-success.html",
        store="books_toscrape",
        target_price=None,
    )
    scraped = ScrapedProduct(
        name="New product",
        price=Decimal("12.34"),
        currency="GBP",
        url=prepared.url,
        store="books_toscrape",
        retrieved_at=NEW_TIME,
    )

    product = service.persist_new_product(prepared, scraped, None)

    assert product.name == "New product"
    assert product.current_price == Decimal("12.34")
    assert product.currency == "GBP"
    assert product.store == "books_toscrape"
    assert product.scrape_status is ScrapeStatus.OK
    assert product.last_error is None
    assert product.last_checked_at == NEW_TIME
    assert product.last_attempt_at == NEW_TIME


def test_dns_failure_preserves_existing_valid_data(db_session: Session) -> None:
    product = make_existing_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)

    service.apply_scrape_result(
        product.id,
        None,
        "Could not resolve the product hostname.",
    )

    assert product.name == "Existing product"
    assert product.current_price == Decimal("10.00")
    assert product.currency == "GBP"
    assert product.store == "books_toscrape"
    assert product.last_checked_at == OLD_TIME
    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.last_error == "Could not resolve the product hostname."
    assert product.last_attempt_at is not None


async def test_add_product_validates_public_dns(db_session: Session) -> None:
    service = ProductService(db_session)

    product = await service.add_product("https://books.toscrape.com/catalogue/pending-ok.html")

    assert product.scrape_status is ScrapeStatus.PENDING
    assert product.name is None
    assert product.current_price is None


async def test_add_product_rejects_private_dns(
    db_session: Session,
    monkeypatch,
) -> None:
    async def private_resolve(host: str, port: int) -> frozenset[str]:
        return frozenset({"127.0.0.1"})

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        private_resolve,
    )
    service = ProductService(db_session)

    with pytest.raises(ProductValidationError):
        await service.add_product("https://books.toscrape.com/catalogue/pending-private.html")

    assert service.products.count() == 0
