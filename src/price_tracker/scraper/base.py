"""Common scraper interface and extracted product value object."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import ClassVar
from urllib.parse import urlsplit

from ..clock import utcnow


@dataclass(frozen=True)
class ScrapedProduct:
    """Product data extracted from a store page."""

    name: str
    price: Decimal
    currency: str
    url: str
    store: str
    retrieved_at: datetime = field(default_factory=utcnow)


class BaseScraper(ABC):
    """Interface implemented by every store-specific adapter."""

    store_id: ClassVar[str]
    store_name: ClassVar[str]
    domains: ClassVar[tuple[str, ...]]
    allowed_subresource_domains: ClassVar[tuple[str, ...]] = ()
    requires_javascript: ClassVar[bool] = False
    wait_for_selector: ClassVar[str | None] = None

    def supports(self, url: str) -> bool:
        """Return whether this adapter supports the URL host."""

        try:
            host = urlsplit(url).hostname
        except ValueError:
            return False
        if not host:
            return False
        return host.lower().rstrip(".") in self.domains

    @abstractmethod
    def parse(self, html: str, url: str) -> ScrapedProduct:
        """Parse a fetched product page."""
