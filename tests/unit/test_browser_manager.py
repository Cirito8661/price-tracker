"""BrowserManager lifecycle and request-guard tests."""

from __future__ import annotations

import pytest
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from price_tracker.scraper.browser import BrowserManager, guarded_route
from price_tracker.scraper.errors import (
    BrowserUnavailableError,
    HttpStatusError,
    InvalidPageError,
    NavigationError,
    PageTooLargeError,
    UnsafeUrlError,
)
from price_tracker.scraper.url_safety import RequestGuard, ValidatedUrl
from tests.fakes import (
    AllowAllGuard,
    FakePage,
    FakeResponse,
    FakeRoute,
    make_playwright,
)

PRODUCT_URL = "https://books.toscrape.com/catalogue/item.html"
PUBLIC_IP = "93.184.216.34"


class DenyGuard:
    async def validate(self, url: str) -> None:
        raise UnsafeUrlError("denied")


def make_manager(settings, **kwargs):
    playwright, browser, context, page = make_playwright(**kwargs)
    manager = BrowserManager(
        settings,
        playwright_factory=lambda: playwright,
    )
    return manager, playwright, browser, context, page


async def test_start_and_stop_lifecycle(settings) -> None:
    manager, playwright, browser, _, _ = make_manager(settings)

    await manager.start()

    assert manager.available is True
    assert browser.closed is False
    assert playwright.stopped is False

    await manager.stop()

    assert manager.available is False
    assert browser.closed is True
    assert playwright.stopped is True


async def test_start_failure_sets_unavailable(settings) -> None:
    manager, _, _, _, _ = make_manager(
        settings,
        start_error=RuntimeError("startup failed"),
    )

    await manager.start()

    assert manager.available is False

    with pytest.raises(BrowserUnavailableError):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())

    await manager.stop()


async def test_fetch_unavailable_manager(settings) -> None:
    manager = BrowserManager(settings)

    with pytest.raises(BrowserUnavailableError):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())


async def test_fetch_returns_html_and_closes_context(settings) -> None:
    page = FakePage(
        html="<html><body>product</body></html>",
        response=FakeResponse(url=PRODUCT_URL),
    )
    manager, _, browser, context, fake_page = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    html = await manager.fetch(
        PRODUCT_URL,
        guard=AllowAllGuard(),
        wait_for_selector="h1",
        java_script_enabled=False,
    )

    assert html == "<html><body>product</body></html>"
    assert fake_page.goto_url == PRODUCT_URL
    assert fake_page.goto_kwargs["wait_until"] == "domcontentloaded"
    assert fake_page.waited_selector == "h1"
    assert context.route_pattern == "**/*"
    assert context.route_handler is not None
    assert context.closed is True
    assert browser.context_kwargs["java_script_enabled"] is False
    assert browser.context_kwargs["service_workers"] == "block"
    assert browser.context_kwargs["accept_downloads"] is False
    assert browser.context_kwargs["ignore_https_errors"] is False

    await manager.stop()


async def test_fetch_http_error_closes_context(settings) -> None:
    page = FakePage(
        response=FakeResponse(url=PRODUCT_URL, status=404),
    )
    manager, _, _, context, _ = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    with pytest.raises(HttpStatusError, match="HTTP 404"):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())

    assert context.closed is True
    await manager.stop()


async def test_fetch_timeout_raises_navigation_error(settings) -> None:
    page = FakePage(
        response=FakeResponse(url=PRODUCT_URL),
        goto_error=PlaywrightTimeoutError("timed out"),
    )
    manager, _, _, context, _ = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    with pytest.raises(NavigationError, match="Timed out"):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())

    assert context.closed is True
    await manager.stop()


async def test_wait_for_selector_timeout_raises_invalid_page(settings) -> None:
    page = FakePage(
        response=FakeResponse(url=PRODUCT_URL),
        wait_error=PlaywrightTimeoutError("timed out"),
    )
    manager, _, _, context, _ = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    with pytest.raises(InvalidPageError):
        await manager.fetch(
            PRODUCT_URL,
            guard=AllowAllGuard(),
            wait_for_selector="h1",
        )

    assert context.closed is True
    await manager.stop()


async def test_page_size_limit(settings) -> None:
    page = FakePage(
        html="x" * 100,
        response=FakeResponse(url=PRODUCT_URL),
    )
    manager, _, _, _, _ = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    with pytest.raises(PageTooLargeError):
        await manager.fetch(
            PRODUCT_URL,
            guard=AllowAllGuard(),
            max_response_bytes=10,
        )

    await manager.stop()


async def test_final_url_is_validated(settings) -> None:
    page = FakePage(
        response=FakeResponse(url="https://evil.example/redirected"),
    )
    manager, _, _, _, _ = make_manager(
        settings,
        page=page,
    )
    await manager.start()

    target = ValidatedUrl(
        url=PRODUCT_URL,
        scheme="https",
        host="books.toscrape.com",
        port=443,
        ips=frozenset({PUBLIC_IP}),
    )
    guard = RequestGuard(
        target,
        allowed_domains={"books.toscrape.com"},
    )

    with pytest.raises(UnsafeUrlError):
        await manager.fetch(PRODUCT_URL, guard=guard)

    await manager.stop()


async def test_guarded_route_allows_document() -> None:
    route = FakeRoute(PRODUCT_URL, "document")

    await guarded_route(route, AllowAllGuard())

    assert route.continued is True
    assert route.aborted is None


async def test_guarded_route_blocks_images() -> None:
    route = FakeRoute(
        "https://books.toscrape.com/media/product.jpg",
        "image",
    )

    await guarded_route(route, AllowAllGuard())

    assert route.aborted == "blockedbyclient"
    assert route.continued is False


async def test_guarded_route_blocks_unsafe_request() -> None:
    route = FakeRoute("https://evil.example/tracker.js", "script")

    await guarded_route(route, DenyGuard())

    assert route.aborted == "blockedbyclient"
    assert route.continued is False


async def test_disconnected_browser_is_marked_unavailable(settings) -> None:
    manager, _, browser, _, _ = make_manager(settings)
    await manager.start()
    browser.connected = False

    with pytest.raises(BrowserUnavailableError):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())

    assert manager.available is False
    await manager.stop()


async def test_new_context_disconnect_marks_unavailable(settings) -> None:
    manager, _, browser, _, _ = make_manager(settings)
    await manager.start()

    async def failing_new_context(**kwargs):
        browser.connected = False
        raise PlaywrightError("browser disconnected")

    browser.new_context = failing_new_context

    with pytest.raises(BrowserUnavailableError):
        await manager.fetch(PRODUCT_URL, guard=AllowAllGuard())

    assert manager.available is False
    await manager.stop()
