"""Scraper engine: browser lifecycle, safety checks, and store adapters."""

from .base import BaseScraper, ScrapedProduct
from .browser import BrowserManager
from .errors import (
    BrowserUnavailableError,
    CurrencyParseError,
    HttpStatusError,
    InvalidPageError,
    InvalidPriceError,
    NavigationError,
    PageTooLargeError,
    PriceNotFoundError,
    ScrapeError,
    UnsafeUrlError,
    UnsupportedStoreError,
)
from .registry import ScraperRegistry, build_default_registry
from .service import ScraperService
from .url_safety import (
    RequestGuard,
    UrlValidationError,
    ValidatedUrl,
    is_public_ip,
    normalize_product_url,
    resolve_host_ips,
    validate_public_url,
)

__all__ = [
    "BaseScraper",
    "BrowserManager",
    "BrowserUnavailableError",
    "CurrencyParseError",
    "HttpStatusError",
    "InvalidPageError",
    "InvalidPriceError",
    "NavigationError",
    "PageTooLargeError",
    "PriceNotFoundError",
    "RequestGuard",
    "ScrapeError",
    "ScrapedProduct",
    "ScraperRegistry",
    "ScraperService",
    "UnsafeUrlError",
    "UnsupportedStoreError",
    "UrlValidationError",
    "ValidatedUrl",
    "build_default_registry",
    "is_public_ip",
    "normalize_product_url",
    "resolve_host_ips",
    "validate_public_url",
]
