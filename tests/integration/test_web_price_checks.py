"""Manual price check web route tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select

from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import (
    NotificationStatus,
    NotificationType,
    PriceChangeType,
    ScrapeStatus,
)
from price_tracker.models.product import Product
from price_tracker.repositories.notifications import NotificationRepository
from price_tracker.repositories.price_history import PriceHistoryRepository
from price_tracker.scraper.errors import NavigationError
from tests.fakes import FakeBrowserManager, make_product_html
from tests.web_helpers import (
    create_history,
    create_product,
    extract_csrf_token,
)

OLD_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


async def _detail_token(client: httpx.AsyncClient, product_id: int) -> str:
    response = await client.get(f"/products/{product_id}")
    assert response.status_code == 200
    return extract_csrf_token(response.text)


def make_valid_product(session_factory: SessionFactory) -> Product:
    return create_product(
        session_factory,
        name="A Light in the Attic",
        current_price=Decimal("51.77"),
        currency="GBP",
        target_price=Decimal("40.00"),
        scrape_status=ScrapeStatus.OK,
        last_checked_at=OLD_TIME,
    )


async def test_manual_check_records_history_and_updates_chart(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    fake_browser_manager: FakeBrowserManager,
) -> None:
    product = make_valid_product(web_session_factory)
    fake_browser_manager.html = make_product_html("£45.00")
    token = await _detail_token(client, product.id)

    response = await client.post(
        f"/products/{product.id}/check",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert f"/products/{product.id}?check=ok" in response.headers["location"]

    with web_session_factory() as session:
        updated = session.get(Product, product.id)
        history = PriceHistoryRepository(session).list_for_product(product.id)
        notifications = NotificationRepository(session).list_for_product(product.id)

    assert updated is not None
    assert updated.current_price == Decimal("45.00")
    assert updated.last_checked_at is not None
    assert updated.last_checked_at != OLD_TIME
    assert len(history) == 2
    assert history[0].price == Decimal("51.77")
    assert history[0].change_type is PriceChangeType.INITIAL
    assert history[0].checked_at == OLD_TIME
    assert history[1].price == Decimal("45.00")
    assert history[1].change_type is PriceChangeType.DECREASE
    assert len(notifications) == 1
    assert notifications[0].notification_type is NotificationType.PRICE_DROP
    assert notifications[0].status is NotificationStatus.SENT

    detail = await client.get(f"/products/{product.id}?check=ok")
    assert detail.status_code == 200
    assert "Price check completed successfully." in detail.text
    assert "Demo data" not in detail.text
    assert "45.00 GBP" in detail.text
    assert "51.77 GBP" in detail.text
    assert "Decrease" in detail.text
    assert "-6.77 GBP" in detail.text
    assert "Check price now" in detail.text

    dashboard = await client.get("/")
    assert "A Light in the Attic" in dashboard.text
    assert "45.00 GBP" in dashboard.text


async def test_manual_check_failure_preserves_data(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    fake_browser_manager: FakeBrowserManager,
) -> None:
    product = make_valid_product(web_session_factory)
    create_history(web_session_factory, product, price=Decimal("51.77"))
    fake_browser_manager.error = NavigationError("Timed out while loading.")
    token = await _detail_token(client, product.id)

    response = await client.post(
        f"/products/{product.id}/check",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert f"/products/{product.id}?check=failed" in response.headers["location"]

    with web_session_factory() as session:
        updated = session.get(Product, product.id)
        history = PriceHistoryRepository(session).list_for_product(product.id)

    assert updated is not None
    assert updated.name == "A Light in the Attic"
    assert updated.current_price == Decimal("51.77")
    assert updated.currency == "GBP"
    assert updated.last_checked_at == OLD_TIME
    assert updated.scrape_status is ScrapeStatus.ERROR
    assert updated.last_error is not None
    assert "Timed out" in updated.last_error
    assert len(history) == 1

    detail = await client.get(f"/products/{product.id}?check=failed")
    assert "Price check failed" in detail.text
    assert "The last check failed: Timed out" in detail.text


async def test_manual_check_requires_csrf(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = make_valid_product(web_session_factory)

    response = await client.post(
        f"/products/{product.id}/check",
        data={},
    )

    assert response.status_code == 403
    with web_session_factory() as session:
        assert PriceHistoryRepository(session).count_for_product(product.id) == 0


async def test_new_product_initial_history_removes_demo_chart(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    products = await client.get("/products")
    token = extract_csrf_token(products.text)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/initial-history.html",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "scrape=ok" in response.headers["location"]

    with web_session_factory() as session:
        product = session.scalars(select(Product)).one()
        history = PriceHistoryRepository(session).list_for_product(product.id)

    assert len(history) == 1
    assert history[0].price == Decimal("51.77")
    assert history[0].change_type is PriceChangeType.INITIAL

    detail = await client.get(f"/products/{product.id}")
    assert "Demo data" not in detail.text
    assert "51.77 GBP" in detail.text
    assert "Initial" in detail.text


async def test_manual_check_htmx_redirect(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    fake_browser_manager: FakeBrowserManager,
) -> None:
    product = make_valid_product(web_session_factory)
    fake_browser_manager.html = make_product_html("£45.00")
    token = await _detail_token(client, product.id)

    response = await client.post(
        f"/products/{product.id}/check",
        data={"csrf_token": token},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 204
    assert f"/products/{product.id}?check=ok" in response.headers["HX-Redirect"]

    with web_session_factory() as session:
        updated = session.get(Product, product.id)

    assert updated is not None
    assert updated.current_price == Decimal("45.00")
