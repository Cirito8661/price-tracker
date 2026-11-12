"""Scraper exception hierarchy."""

from __future__ import annotations


class ScrapeError(Exception):
    """Base class for scraping failures."""


class UnsupportedStoreError(ScrapeError):
    """Raised when no adapter supports the URL host."""


class UnsafeUrlError(ScrapeError):
    """Raised when a URL or browser request fails security validation."""


class DnsResolutionError(UnsafeUrlError):
    """Raised when DNS resolution fails for a transient reason."""


class BrowserUnavailableError(ScrapeError):
    """Raised when Playwright is not available."""


class NavigationError(ScrapeError):
    """Raised when the browser cannot load the page."""


class HttpStatusError(NavigationError):
    """Raised when the store returns an HTTP error status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"The store returned HTTP {status_code}.")


class InvalidPageError(ScrapeError):
    """Raised when the page structure does not match the adapter."""


class PriceNotFoundError(ScrapeError):
    """Raised when the product price cannot be found."""


class InvalidPriceError(ScrapeError):
    """Raised when the price text is malformed."""


class CurrencyParseError(ScrapeError):
    """Raised when the currency cannot be determined."""


class PageTooLargeError(ScrapeError):
    """Raised when the fetched HTML exceeds the configured limit."""
