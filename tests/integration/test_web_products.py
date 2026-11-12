"""Product web route tests."""

from __future__ import annotations

from decimal import Decimal

import httpx
from sqlalchemy import select

from price_tracker.database.session import SessionFactory
from price_tracker.models.enums import PriceChangeType, ScrapeStatus
from price_tracker.models.product import Product
from price_tracker.scraper.errors import DnsResolutionError, NavigationError
from tests.fakes import FakeBrowserManager
from tests.web_helpers import (
    count_products,
    create_history,
    create_product,
    extract_csrf_token,
    load_product,
)


async def _token(client: httpx.AsyncClient) -> str:
    response = await client.get("/products")
    assert response.status_code == 200
    return extract_csrf_token(response.text)


async def test_products_page_empty_state(client: httpx.AsyncClient) -> None:
    response = await client.get("/products")

    assert response.status_code == 200
    assert "Products" in response.text
    assert "No products tracked" in response.text
    assert "Add a product" in response.text


async def test_add_product_success(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            "target_price": "40.00",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/products?created=")
    assert "scrape=ok" in response.headers["location"]

    with web_session_factory() as session:
        product = session.scalars(select(Product)).one()

    assert product.url == (
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    )
    assert product.name == "A Light in the Attic"
    assert product.current_price == Decimal("51.77")
    assert product.currency == "GBP"
    assert product.target_price == Decimal("40.00")
    assert product.scrape_status is ScrapeStatus.OK
    assert product.store == "books_toscrape"
    assert product.last_checked_at is not None
    assert product.last_error is None


async def test_add_product_validation_errors(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    token = await _token(client)

    cases = [
        ("", "", "Enter a product URL."),
        ("ftp://example.com/item", "", "Only http and https URLs are supported."),
        ("http://localhost/item", "", "Local and private network addresses"),
        (
            "https://example.com/item",
            "",
            "This store is not supported yet",
        ),
        (
            "https://books.toscrape.com/catalogue/target-price.html",
            "not-a-price",
            "Enter a valid non-negative price",
        ),
        (
            "https://[192.0.0.9]/item",
            "",
            "not valid",
        ),
        (
            "https://[::1/item",
            "",
            "not valid",
        ),
    ]

    for url, target_price, expected_error in cases:
        response = await client.post(
            "/products",
            data={
                "url": url,
                "target_price": target_price,
                "csrf_token": token,
            },
        )
        assert response.status_code == 422
        assert expected_error in response.text

    assert count_products(web_session_factory) == 0


async def test_add_duplicate_product(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    create_product(
        web_session_factory,
        url="https://books.toscrape.com/catalogue/duplicate.html",
    )
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/duplicate.html",
            "csrf_token": token,
        },
    )

    assert response.status_code == 422
    assert "already tracked" in response.text
    assert count_products(web_session_factory) == 1


async def test_add_product_htmx_redirect(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/htmx.html",
            "csrf_token": token,
        },
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 204
    assert response.headers["HX-Redirect"].startswith("/products?created=")
    assert "scrape=ok" in response.headers["HX-Redirect"]
    assert count_products(web_session_factory) == 1


async def test_add_product_scrape_failure_saves_error(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    fake_browser_manager: FakeBrowserManager,
) -> None:
    fake_browser_manager.error = NavigationError("Timed out while loading.")
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/failure.html",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "scrape=failed" in response.headers["location"]

    with web_session_factory() as session:
        product = session.scalars(select(Product)).one()

    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.name is None
    assert product.current_price is None
    assert product.last_error is not None
    assert "Timed out" in product.last_error


async def test_add_product_invalid_html_saves_error(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    fake_browser_manager: FakeBrowserManager,
) -> None:
    fake_browser_manager.html = "<html><body>No product here</body></html>"
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/invalid.html",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "scrape=failed" in response.headers["location"]

    with web_session_factory() as session:
        product = session.scalars(select(Product)).one()

    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.last_error is not None
    assert "Product name" in product.last_error


async def test_dns_failure_saves_error_product(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
    monkeypatch,
) -> None:
    async def failing_resolve(host: str, port: int) -> frozenset[str]:
        raise DnsResolutionError("Could not resolve the product hostname.")

    monkeypatch.setattr(
        "price_tracker.scraper.url_safety.resolve_host_ips",
        failing_resolve,
    )
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://books.toscrape.com/catalogue/dns-failure.html",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "scrape=failed" in response.headers["location"]

    with web_session_factory() as session:
        product = session.scalars(select(Product)).one()

    assert product.scrape_status is ScrapeStatus.ERROR
    assert product.name is None
    assert product.current_price is None
    assert product.last_error is not None
    assert "Could not resolve" in product.last_error


async def test_unsupported_store_is_rejected(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    token = await _token(client)

    response = await client.post(
        "/products",
        data={
            "url": "https://example.com/item",
            "csrf_token": token,
        },
    )

    assert response.status_code == 422
    assert "This store is not supported yet" in response.text
    assert count_products(web_session_factory) == 0


async def test_product_detail_page_with_demo_chart(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(
        web_session_factory,
        name="A Light in the Attic",
        current_price=Decimal("51.77"),
        currency="GBP",
        target_price=Decimal("40.00"),
        scrape_status=ScrapeStatus.OK,
    )

    response = await client.get(f"/products/{product.id}")

    assert response.status_code == 200
    assert "A Light in the Attic" in response.text
    assert "51.77 GBP" in response.text
    assert "Demo data" in response.text
    assert 'id="price-history-chart"' in response.text
    assert "/static/vendor/chartjs/chart.umd.min.js" in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert "cdnjs.cloudflare.com" not in response.text


async def test_product_detail_with_real_history(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(
        web_session_factory,
        name="History product",
        current_price=Decimal("45.00"),
        currency="GBP",
        scrape_status=ScrapeStatus.OK,
    )
    create_history(
        web_session_factory,
        product,
        price=Decimal("45.00"),
        change_type=PriceChangeType.DECREASE,
    )

    response = await client.get(f"/products/{product.id}")

    assert response.status_code == 200
    assert "Demo data" not in response.text
    assert "45.00 GBP" in response.text
    assert "2026-01-02 03:04" in response.text


async def test_invalid_product_id_returns_404(client: httpx.AsyncClient) -> None:
    response = await client.get("/products/99999")

    assert response.status_code == 404
    assert "Product not found" in response.text


async def test_toggle_product_redirects(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(web_session_factory)
    token = await _token(client)

    response = await client.post(
        f"/products/{product.id}/toggle",
        data={"csrf_token": token, "next": "/products"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    updated = load_product(web_session_factory, product.id)
    assert updated is not None
    assert updated.is_active is False


async def test_toggle_product_htmx_returns_row(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(web_session_factory)
    token = await _token(client)

    response = await client.post(
        f"/products/{product.id}/toggle",
        data={"csrf_token": token, "next": "/products"},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert f'id="product-row-{product.id}"' in response.text
    assert "Paused" in response.text
    updated = load_product(web_session_factory, product.id)
    assert updated is not None
    assert updated.is_active is False


async def test_delete_product_redirects(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(web_session_factory)
    token = await _token(client)

    response = await client.post(
        f"/products/{product.id}/delete",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert count_products(web_session_factory) == 0


async def test_delete_product_htmx_removes_row(
    client: httpx.AsyncClient,
    web_session_factory: SessionFactory,
) -> None:
    product = create_product(web_session_factory)
    token = await _token(client)

    response = await client.post(
        f"/products/{product.id}/delete",
        data={"csrf_token": token},
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    assert response.text == ""
    assert count_products(web_session_factory) == 0


async def test_local_static_assets_are_served(client: httpx.AsyncClient) -> None:
    paths = [
        "/static/css/app.css",
        "/static/js/app.js",
        "/static/vendor/htmx/htmx.min.js",
        "/static/vendor/htmx/LICENSE",
        "/static/vendor/chartjs/chart.umd.min.js",
        "/static/vendor/chartjs/LICENSE.md",
    ]

    for path in paths:
        response = await client.get(path)
        assert response.status_code == 200
        assert response.content
