"""Controlled fakes for scraper and web integration tests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "html" / "books_to_scrape_product.html"
)
BOOKS_TO_SCRAPE_HTML = FIXTURE_PATH.read_text(encoding="utf-8")


def make_product_html(
    price: str = "£51.77",
    name: str = "A Light in the Attic",
) -> str:
    """Build a minimal controlled Books to Scrape product page."""

    return (
        "<!doctype html><html><body>"
        f"<h1>{name}</h1>"
        f'<p class="price_color">{price}</p>'
        "</body></html>"
    )


class FakeBrowserManager:
    """Browser manager double that returns controlled HTML."""

    def __init__(
        self,
        html: str = BOOKS_TO_SCRAPE_HTML,
        error: Exception | None = None,
    ) -> None:
        self.html = html
        self.error = error
        self.available = True
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True
        self.available = True

    async def stop(self) -> None:
        self.stopped = True
        self.available = False

    async def fetch(self, url: str, *, guard: Any, **kwargs: Any) -> str:
        if self.error is not None:
            raise self.error
        return self.html


class AllowAllGuard:
    """Request guard double used by BrowserManager unit tests."""

    async def validate(self, url: str) -> None:
        return None


@dataclass
class FakeResponse:
    url: str
    status: int = 200
    headers: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if self.headers is None:
            self.headers = {"content-type": "text/html; charset=utf-8"}


class FakePage:
    def __init__(
        self,
        *,
        html: str = "<html><body>ok</body></html>",
        response: FakeResponse | None = None,
        goto_error: Exception | None = None,
        wait_error: Exception | None = None,
        content_error: Exception | None = None,
    ) -> None:
        self.html = html
        self.response = response
        self.goto_error = goto_error
        self.wait_error = wait_error
        self.content_error = content_error
        self.goto_url: str | None = None
        self.goto_kwargs: dict[str, Any] = {}
        self.waited_selector: str | None = None

    async def goto(self, url: str, **kwargs: Any) -> FakeResponse | None:
        self.goto_url = url
        self.goto_kwargs = kwargs
        if self.goto_error is not None:
            raise self.goto_error
        return self.response

    async def wait_for_selector(self, selector: str, **kwargs: Any) -> None:
        self.waited_selector = selector
        if self.wait_error is not None:
            raise self.wait_error

    async def content(self) -> str:
        if self.content_error is not None:
            raise self.content_error
        return self.html


class FakeContext:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.closed = False
        self.route_pattern: str | None = None
        self.route_handler: Any | None = None

    async def route(self, pattern: str, handler: Any) -> None:
        self.route_pattern = pattern
        self.route_handler = handler

    async def new_page(self) -> FakePage:
        return self.page

    async def close(self) -> None:
        self.closed = True


class FakeBrowser:
    def __init__(self, context: FakeContext) -> None:
        self.context = context
        self.closed = False
        self.connected = True
        self.context_kwargs: dict[str, Any] = {}

    def is_connected(self) -> bool:
        return self.connected

    async def new_context(self, **kwargs: Any) -> FakeContext:
        self.context_kwargs = kwargs
        return self.context

    async def close(self) -> None:
        self.closed = True
        self.connected = False


class FakeChromium:
    def __init__(
        self,
        browser: FakeBrowser,
        *,
        launch_error: Exception | None = None,
    ) -> None:
        self.browser = browser
        self.launch_error = launch_error
        self.launch_kwargs: dict[str, Any] = {}

    async def launch(self, **kwargs: Any) -> FakeBrowser:
        self.launch_kwargs = kwargs
        if self.launch_error is not None:
            raise self.launch_error
        return self.browser


class FakePlaywright:
    def __init__(
        self,
        browser: FakeBrowser,
        *,
        start_error: Exception | None = None,
        launch_error: Exception | None = None,
    ) -> None:
        self.start_error = start_error
        self.stopped = False
        self.chromium = FakeChromium(browser, launch_error=launch_error)

    async def start(self) -> FakePlaywright:
        if self.start_error is not None:
            raise self.start_error
        return self

    async def stop(self) -> None:
        self.stopped = True


class FakeRoute:
    def __init__(self, url: str, resource_type: str = "document") -> None:
        self.request = type(
            "Request",
            (),
            {"url": url, "resource_type": resource_type},
        )()
        self.aborted: str | None = None
        self.continued = False

    async def abort(self, error_code: str) -> None:
        self.aborted = error_code

    async def continue_(self) -> None:
        self.continued = True


def make_playwright(
    *,
    page: FakePage | None = None,
    start_error: Exception | None = None,
    launch_error: Exception | None = None,
) -> tuple[FakePlaywright, FakeBrowser, FakeContext, FakePage]:
    """Build a connected fake Playwright object graph."""

    fake_page = page or FakePage()
    context = FakeContext(fake_page)
    browser = FakeBrowser(context)
    playwright = FakePlaywright(
        browser,
        start_error=start_error,
        launch_error=launch_error,
    )
    return playwright, browser, context, fake_page
