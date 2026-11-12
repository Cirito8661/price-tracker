"""Playwright browser lifecycle and guarded page fetching."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import (
    Route,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from ..config import Settings
from .errors import (
    BrowserUnavailableError,
    HttpStatusError,
    InvalidPageError,
    NavigationError,
    PageTooLargeError,
    UnsafeUrlError,
)
from .url_safety import RequestGuard

logger = logging.getLogger(__name__)

BLOCKED_RESOURCE_TYPES = frozenset(
    {
        "image",
        "media",
        "font",
        "texttrack",
        "manifest",
        "websocket",
        "eventsource",
        "other",
    }
)


def _safe_url_for_log(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


async def guarded_route(route: Route, guard: RequestGuard) -> None:
    """Abort blocked resource types and any request failing URL validation."""

    request = route.request
    if request.resource_type in BLOCKED_RESOURCE_TYPES:
        await route.abort("blockedbyclient")
        return

    try:
        await guard.validate(request.url)
    except UnsafeUrlError:
        logger.warning("Blocked browser request to %s", _safe_url_for_log(request.url))
        await route.abort("blockedbyclient")
        return

    await route.continue_()


class BrowserManager:
    """Own one Playwright browser for the application's lifetime."""

    def __init__(
        self,
        settings: Settings,
        *,
        playwright_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.settings = settings
        self._playwright_factory = playwright_factory or async_playwright
        self._playwright: Any | None = None
        self._browser: Any | None = None
        self._semaphore = asyncio.Semaphore(settings.scraper_concurrency)
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    async def start(self) -> None:
        """Start Playwright and Chromium, logging instead of crashing on failure."""

        if self._available:
            return

        try:
            self._playwright = await self._playwright_factory().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            if not self._browser.is_connected():
                raise RuntimeError("Chromium launched but is not connected.")
        except Exception:
            logger.exception(
                "Playwright browser startup failed. Install Chromium with "
                "`python -m playwright install chromium`."
            )
            await self._cleanup()
            return

        self._available = True
        logger.info("Playwright Chromium browser started")

    async def stop(self) -> None:
        """Close the browser and Playwright process."""

        await self._cleanup()
        logger.info("Playwright Chromium browser stopped")

    async def _cleanup(self) -> None:
        browser = self._browser
        self._browser = None
        if browser is not None:
            with contextlib.suppress(Exception):
                await browser.close()

        playwright = self._playwright
        self._playwright = None
        if playwright is not None:
            with contextlib.suppress(Exception):
                await playwright.stop()

        self._available = False

    def _browser_is_connected(self) -> bool:
        browser = self._browser
        if browser is None:
            return False
        try:
            return bool(browser.is_connected())
        except Exception:
            return False

    async def fetch(
        self,
        url: str,
        *,
        guard: RequestGuard,
        wait_for_selector: str | None = None,
        timeout_ms: int | None = None,
        java_script_enabled: bool = False,
        max_response_bytes: int | None = None,
    ) -> str:
        """Fetch HTML with redirect and subresource validation."""

        if not self._available or not self._browser_is_connected():
            self._available = False
            raise BrowserUnavailableError(
                "Playwright is not available. Install Chromium with "
                "`python -m playwright install chromium`."
            )

        timeout = timeout_ms or self.settings.scraper_timeout_ms
        max_bytes = max_response_bytes or self.settings.scraper_max_response_bytes

        async with self._semaphore:
            if not self._available or not self._browser_is_connected():
                self._available = False
                raise BrowserUnavailableError("The Playwright browser is not available.")

            try:
                context = await self._browser.new_context(
                    user_agent=self.settings.scraper_user_agent,
                    java_script_enabled=java_script_enabled,
                    service_workers="block",
                    accept_downloads=False,
                    ignore_https_errors=False,
                )
            except PlaywrightError as exc:
                if not self._browser_is_connected():
                    self._available = False
                    logger.warning("Playwright browser disconnected")
                    raise BrowserUnavailableError("The Playwright browser disconnected.") from exc
                raise BrowserUnavailableError("Could not open a browser context.") from exc

            try:

                async def route_handler(route: Route) -> None:
                    await guarded_route(route, guard)

                try:
                    await context.route("**/*", route_handler)
                    page = await context.new_page()
                except PlaywrightError as exc:
                    if not self._browser_is_connected():
                        self._available = False
                        logger.warning("Playwright browser disconnected")
                        raise BrowserUnavailableError(
                            "The Playwright browser disconnected."
                        ) from exc
                    raise NavigationError("Could not open a page in the browser.") from exc

                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=timeout,
                    )
                except PlaywrightTimeoutError as exc:
                    if not self._browser_is_connected():
                        self._available = False
                        logger.warning("Playwright browser disconnected")
                        raise BrowserUnavailableError(
                            "The Playwright browser disconnected."
                        ) from exc
                    raise NavigationError("Timed out while loading the product page.") from exc
                except PlaywrightError as exc:
                    if not self._browser_is_connected():
                        self._available = False
                        logger.warning("Playwright browser disconnected")
                        raise BrowserUnavailableError(
                            "The Playwright browser disconnected."
                        ) from exc
                    raise NavigationError("The browser could not load the product page.") from exc

                if response is None:
                    raise NavigationError("The store did not return a response.")
                if response.status >= 400:
                    raise HttpStatusError(response.status)

                content_type = response.headers.get("content-type", "")
                if content_type and "html" not in content_type.lower():
                    raise InvalidPageError("The store did not return an HTML page.")

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except ValueError:
                        declared_size = 0
                    if declared_size > max_bytes:
                        raise PageTooLargeError(
                            "The product page is larger than the configured limit."
                        )

                await guard.validate(response.url)

                if wait_for_selector:
                    try:
                        await page.wait_for_selector(
                            wait_for_selector,
                            timeout=timeout,
                        )
                    except PlaywrightTimeoutError as exc:
                        raise InvalidPageError(
                            "The expected product content did not load."
                        ) from exc

                try:
                    html = await page.content()
                except PlaywrightError as exc:
                    if not self._browser_is_connected():
                        self._available = False
                        logger.warning("Playwright browser disconnected")
                        raise BrowserUnavailableError(
                            "The Playwright browser disconnected."
                        ) from exc
                    raise NavigationError("Could not read the page content.") from exc

                if len(html.encode("utf-8")) > max_bytes:
                    raise PageTooLargeError("The product page is larger than the configured limit.")
                return html
            finally:
                with contextlib.suppress(Exception):
                    await context.close()
                if not self._browser_is_connected():
                    self._available = False
                    logger.warning("Playwright browser disconnected")
