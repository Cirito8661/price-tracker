"""Async orchestration for initial product scraping."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ..config import Settings
from ..database.session import SessionFactory
from ..models.product import Product
from ..scraper.base import ScrapedProduct
from ..scraper.errors import (
    DnsResolutionError,
    ScrapeError,
    UnsafeUrlError,
    UnsupportedStoreError,
)
from ..scraper.service import ScraperService
from ..scraper.url_safety import UrlValidationError, validate_public_url
from .product_service import PreparedProduct, ProductService, ProductValidationError


@dataclass(frozen=True)
class InitialScrapeResult:
    """Result of creating a product and attempting its first scrape."""

    product: Product
    scraped: bool
    error: str | None


class ProductScrapeService:
    """Coordinate validation, safe scraping, and product persistence."""

    def __init__(
        self,
        scraper_service: ScraperService,
        session_factory: SessionFactory,
        settings: Settings,
    ) -> None:
        self.scraper_service = scraper_service
        self.session_factory = session_factory
        self.settings = settings

    async def add_product(
        self,
        raw_url: str,
        raw_target_price: str | None = None,
    ) -> InitialScrapeResult:
        """Validate and create a product, then attempt its initial scrape."""

        try:
            adapter = self.scraper_service.get_adapter(raw_url)
        except (UnsafeUrlError, UnsupportedStoreError) as exc:
            raise ProductValidationError({"url": str(exc)}) from exc

        prepared = await asyncio.to_thread(
            self._prepare,
            raw_url,
            raw_target_price,
            adapter.store_id,
        )

        try:
            await validate_public_url(
                prepared.url,
                allowed_ports=self.settings.allowed_ports,
            )
        except DnsResolutionError as exc:
            error_message = str(exc)
            product = await asyncio.to_thread(
                self._persist,
                prepared,
                None,
                error_message,
            )
            return InitialScrapeResult(
                product=product,
                scraped=False,
                error=error_message,
            )
        except (UnsafeUrlError, UrlValidationError) as exc:
            raise ProductValidationError({"url": str(exc)}) from exc

        scrape_result = None
        scrape_error = None
        try:
            scrape_result = await self.scraper_service.scrape(prepared.url)
        except ScrapeError as exc:
            scrape_error = str(exc)

        product = await asyncio.to_thread(
            self._persist,
            prepared,
            scrape_result,
            scrape_error,
        )
        return InitialScrapeResult(
            product=product,
            scraped=scrape_result is not None,
            error=scrape_error,
        )

    def _prepare(
        self,
        raw_url: str,
        raw_target_price: str | None,
        store: str,
    ) -> PreparedProduct:
        with self.session_factory() as session:
            service = ProductService(
                session,
                recent_decrease_days=self.settings.recent_decrease_days,
            )
            return service.prepare_new_product(
                raw_url,
                raw_target_price,
                store=store,
            )

    def _persist(
        self,
        prepared: PreparedProduct,
        scrape_result: ScrapedProduct | None,
        scrape_error: str | None,
    ) -> Product:
        with self.session_factory() as session:
            service = ProductService(
                session,
                recent_decrease_days=self.settings.recent_decrease_days,
            )
            return service.persist_new_product(
                prepared,
                scrape_result,
                scrape_error,
                scrape_attempted=True,
            )
