"""Price history recording and change classification tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from price_tracker.models.enums import PriceChangeType, ScrapeStatus
from price_tracker.models.price_history import PriceHistory
from price_tracker.models.product import Product
from price_tracker.scraper.base import ScrapedProduct
from price_tracker.services.product_service import ProductService

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
NEW_TIME = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
LATER_TIME = datetime(2026, 1, 3, 12, 0, 0, tzinfo=UTC)


def make_product(
    *,
    current_price: Decimal | None = Decimal("51.77"),
    currency: str | None = "GBP",
    last_checked_at: datetime | None = OLD_TIME,
) -> Product:
    return Product(
        url="https://books.toscrape.com/catalogue/item.html",
        name="A Light in the Attic",
        store="books_toscrape",
        current_price=current_price,
        currency=currency,
        scrape_status=ScrapeStatus.OK,
        last_checked_at=last_checked_at,
    )


def make_scrape(
    price: Decimal,
    *,
    currency: str = "GBP",
    retrieved_at: datetime = NEW_TIME,
) -> ScrapedProduct:
    return ScrapedProduct(
        name="A Light in the Attic",
        price=price,
        currency=currency,
        url="https://books.toscrape.com/catalogue/item.html",
        store="books_toscrape",
        retrieved_at=retrieved_at,
    )


def seed_initial_history(
    service: ProductService,
    product: Product,
    price: Decimal = Decimal("51.77"),
) -> None:
    service.history.add(
        PriceHistory(
            product=product,
            price=price,
            currency="GBP",
            change_type=PriceChangeType.INITIAL,
            checked_at=OLD_TIME,
        )
    )
    service.session.commit()


def test_record_check_backfills_legacy_initial_price(db_session: Session) -> None:
    product = make_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)

    record = service.record_price_check(product.id, make_scrape(Decimal("45.00")))

    history = service.history.list_for_product(product.id)
    assert len(history) == 2
    assert history[0].price == Decimal("51.77")
    assert history[0].change_type is PriceChangeType.INITIAL
    assert history[0].checked_at == OLD_TIME
    assert history[1].price == Decimal("45.00")
    assert history[1].change_type is PriceChangeType.DECREASE
    assert record.previous_price == Decimal("51.77")
    assert record.change_type is PriceChangeType.DECREASE
    assert product.current_price == Decimal("45.00")
    assert product.last_checked_at == NEW_TIME
    assert product.scrape_status is ScrapeStatus.OK


def test_record_check_increase_then_unchanged(db_session: Session) -> None:
    product = make_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)
    seed_initial_history(service, product)

    increase = service.record_price_check(
        product.id,
        make_scrape(Decimal("60.00"), retrieved_at=NEW_TIME),
    )
    unchanged = service.record_price_check(
        product.id,
        make_scrape(Decimal("60.00"), retrieved_at=LATER_TIME),
    )

    assert increase.change_type is PriceChangeType.INCREASE
    assert unchanged.change_type is PriceChangeType.UNCHANGED
    assert unchanged.previous_price == Decimal("60.00")
    assert unchanged.history.checked_at == LATER_TIME
    assert service.history.count_for_product(product.id) == 3


def test_record_check_currency_change(db_session: Session) -> None:
    product = make_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)
    seed_initial_history(service, product)

    record = service.record_price_check(
        product.id,
        make_scrape(Decimal("45.00"), currency="USD"),
    )

    assert record.change_type is PriceChangeType.CURRENCY_CHANGED
    assert record.previous_currency == "GBP"
    assert product.currency == "USD"
    assert product.current_price == Decimal("45.00")


def test_record_check_without_previous_price_is_initial(db_session: Session) -> None:
    product = make_product(
        current_price=None,
        currency=None,
        last_checked_at=None,
    )
    product.scrape_status = ScrapeStatus.PENDING
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)

    record = service.record_price_check(
        product.id,
        make_scrape(Decimal("45.00")),
    )

    assert record.previous_price is None
    assert record.change_type is PriceChangeType.INITIAL
    assert service.history.count_for_product(product.id) == 1
    assert product.current_price == Decimal("45.00")


def test_failed_check_preserves_history_and_product(db_session: Session) -> None:
    product = make_product()
    db_session.add(product)
    db_session.commit()
    service = ProductService(db_session)
    seed_initial_history(service, product)
    original_checked_at = product.last_checked_at

    service.apply_scrape_result(
        product.id,
        None,
        "Timed out while loading the product page.",
    )

    assert product.name == "A Light in the Attic"
    assert product.current_price == Decimal("51.77")
    assert product.currency == "GBP"
    assert product.store == "books_toscrape"
    assert product.last_checked_at == original_checked_at
    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.last_error == "Timed out while loading the product page."
    assert service.history.count_for_product(product.id) == 1
