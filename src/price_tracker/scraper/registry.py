"""Store adapter registry."""

from __future__ import annotations

from collections.abc import Iterable

from .adapters.books_to_scrape import BooksToScrapeAdapter
from .base import BaseScraper
from .errors import UnsupportedStoreError


class ScraperRegistry:
    """Resolve a URL to its explicit store adapter."""

    def __init__(self, adapters: Iterable[BaseScraper]) -> None:
        self.adapters = tuple(adapters)

    def get_adapter(self, url: str) -> BaseScraper:
        for adapter in self.adapters:
            if adapter.supports(url):
                return adapter

        supported = ", ".join(adapter.store_name for adapter in self.adapters)
        raise UnsupportedStoreError(
            f"This store is not supported yet. Supported stores: {supported or 'none'}."
        )

    @property
    def supported_store_names(self) -> tuple[str, ...]:
        return tuple(adapter.store_name for adapter in self.adapters)


def build_default_registry() -> ScraperRegistry:
    """Build the registry for the stores supported in v1.0."""

    return ScraperRegistry([BooksToScrapeAdapter()])
