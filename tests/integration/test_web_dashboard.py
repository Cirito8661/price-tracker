"""Dashboard and database lifecycle tests."""

from __future__ import annotations

from decimal import Decimal

import httpx
from sqlalchemy import func, select

from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import ScrapeStatus
from price_tracker.models.product import Product
from tests.web_helpers import create_product


async def test_dashboard_renders_empty_state(client: httpx.AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "No products yet" in response.text
    assert "No price checks yet" in response.text
    assert 'data-stat="total">0<' in response.text
    assert 'data-stat="decreases">0<' in response.text


async def test_dashboard_counts_products(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    create_product(web_session_factory)
    create_product(
        web_session_factory,
        url="https://books.toscrape.com/catalogue/checked.html",
        name="Checked product",
        current_price=Decimal("12.50"),
        currency="GBP",
        scrape_status=ScrapeStatus.OK,
        is_active=False,
    )

    response = await client.get("/")

    assert response.status_code == 200
    assert 'data-stat="total">2<' in response.text
    assert 'data-stat="active">1<' in response.text
    assert 'data-stat="awaiting">1<' in response.text
    assert "Checked product" in response.text
    assert "Untitled product" in response.text


async def test_dashboard_shows_recent_change(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    from tests.web_helpers import create_history

    product = create_product(
        web_session_factory,
        name="History product",
        current_price=Decimal("45.00"),
        currency="GBP",
        scrape_status=ScrapeStatus.OK,
    )
    create_history(web_session_factory, product, price=Decimal("45.00"))

    response = await client.get("/")

    assert response.status_code == 200
    assert "History product" in response.text
    assert "45.00 GBP" in response.text


async def test_app_database_lifecycle(
    client: httpx.AsyncClient,
    app,
) -> None:
    assert app.state.engine is not None
    assert app.state.session_factory is not None

    with app.state.session_factory() as session:
        count = session.scalar(select(func.count()).select_from(Product))

    assert count == 0
