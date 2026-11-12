"""High-level scraper orchestration: adapter lookup, safety, fetch, and parse."""

from __future__ import annotations

from ..config import Settings
from .base import BaseScraper, ScrapedProduct
from .browser import BrowserManager
from .errors import UnsafeUrlError
from .registry import ScraperRegistry
from .url_safety import (
    RequestGuard,
    UrlValidationError,
    normalize_product_url,
    validate_public_url,
)


class ScraperService:
    """Run the safe fetch-and-parse pipeline for a supported store."""

    def __init__(
        self,
        browser_manager: BrowserManager,
        registry: ScraperRegistry,
        settings: Settings,
    ) -> None:
        self.browser_manager = browser_manager
        self.registry = registry
        self.settings = settings

    def get_adapter(self, url: str) -> BaseScraper:
        """Return the adapter for a URL or raise a safe validation error."""

        try:
            normalized = normalize_product_url(url)
        except UrlValidationError as exc:
            raise UnsafeUrlError(str(exc)) from exc
        return self.registry.get_adapter(normalized)

    async def scrape(self, url: str) -> ScrapedProduct:
        """Validate, fetch, and parse a product page."""

        try:
            normalized = normalize_product_url(url)
        except UrlValidationError as exc:
            raise UnsafeUrlError(str(exc)) from exc

        adapter = self.registry.get_adapter(normalized)
        validated = await validate_public_url(
            normalized,
            allowed_ports=self.settings.allowed_ports,
        )

        allowed_domains = set(adapter.domains) | set(adapter.allowed_subresource_domains)
        guard = RequestGuard(
            validated,
            allowed_domains=allowed_domains,
            allowed_ports=self.settings.allowed_ports,
        )

        html = await self.browser_manager.fetch(
            validated.url,
            guard=guard,
            wait_for_selector=adapter.wait_for_selector,
            timeout_ms=self.settings.scraper_timeout_ms,
            java_script_enabled=adapter.requires_javascript,
            max_response_bytes=self.settings.scraper_max_response_bytes,
        )
        return adapter.parse(html, validated.url)
