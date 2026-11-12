"""Manual price checking with per-product overlap protection."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum

from ..config import Settings
from ..database.session import SessionFactory
from ..scraper.base import ScrapedProduct
from ..scraper.errors import ScrapeError
from ..scraper.service import ScraperService
from .notification_service import NotificationService
from .product_service import PriceCheckRecord, ProductService

logger = logging.getLogger(__name__)


class PriceCheckStatus(StrEnum):
    """Outcome of a manual price check request."""

    SUCCESS = "success"
    FAILED = "failed"
    BUSY = "busy"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class PriceCheckResult:
    """Result returned to the web layer after a manual check."""

    status: PriceCheckStatus
    product_id: int
    record: PriceCheckRecord | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProductSnapshot:
    """Minimal product data needed outside the database session."""

    id: int
    url: str


class PriceChecker:
    """Run one manual scrape per product without overlapping checks."""

    def __init__(
        self,
        scraper_service: ScraperService,
        session_factory: SessionFactory,
        settings: Settings,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.scraper_service = scraper_service
        self.session_factory = session_factory
        self.settings = settings
        self.notification_service = notification_service
        self._in_progress: set[int] = set()

    async def check_product(self, product_id: int) -> PriceCheckResult:
        """Scrape a product, record the result, and preserve data on failure."""

        if product_id in self._in_progress:
            return PriceCheckResult(
                status=PriceCheckStatus.BUSY,
                product_id=product_id,
            )

        self._in_progress.add(product_id)
        try:
            snapshot = await asyncio.to_thread(self._load_snapshot, product_id)
            if snapshot is None:
                return PriceCheckResult(
                    status=PriceCheckStatus.NOT_FOUND,
                    product_id=product_id,
                )

            try:
                scrape_result = await self.scraper_service.scrape(snapshot.url)
            except ScrapeError as exc:
                error = str(exc)
                await asyncio.to_thread(
                    self._record_failure,
                    product_id,
                    error,
                )
                return PriceCheckResult(
                    status=PriceCheckStatus.FAILED,
                    product_id=product_id,
                    error=error,
                )

            record = await asyncio.to_thread(
                self._record_success,
                product_id,
                scrape_result,
            )
            if self.notification_service is not None:
                try:
                    await self.notification_service.process_check(record)
                except Exception:
                    logger.exception(
                        "Notification processing failed for product %s",
                        product_id,
                    )
            return PriceCheckResult(
                status=PriceCheckStatus.SUCCESS,
                product_id=product_id,
                record=record,
            )
        finally:
            self._in_progress.discard(product_id)

    def _load_snapshot(self, product_id: int) -> ProductSnapshot | None:
        with self.session_factory() as session:
            service = ProductService(
                session,
                recent_decrease_days=self.settings.recent_decrease_days,
                allowed_ports=self.settings.allowed_ports,
            )
            product = service.get_product(product_id)
            if product is None:
                return None
            return ProductSnapshot(id=product.id, url=product.url)

    def _record_failure(self, product_id: int, error: str) -> None:
        with self.session_factory() as session:
            service = ProductService(
                session,
                recent_decrease_days=self.settings.recent_decrease_days,
                allowed_ports=self.settings.allowed_ports,
            )
            service.apply_scrape_result(product_id, None, error)

    def _record_success(
        self,
        product_id: int,
        scrape_result: ScrapedProduct,
    ) -> PriceCheckRecord:
        with self.session_factory() as session:
            service = ProductService(
                session,
                recent_decrease_days=self.settings.recent_decrease_days,
                allowed_ports=self.settings.allowed_ports,
            )
            return service.record_price_check(product_id, scrape_result)
