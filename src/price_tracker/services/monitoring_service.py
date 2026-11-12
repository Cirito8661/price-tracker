"""Global automatic price sweep coordination."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from ..config import Settings
from ..database.session import SessionFactory
from ..repositories.products import ProductRepository
from .price_checker import PriceChecker, PriceCheckStatus

logger = logging.getLogger(__name__)


@dataclass
class SweepSummary:
    """Counts produced by one automatic price sweep."""

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    busy: int = 0
    not_found: int = 0
    errors: int = 0


class MonitoringService:
    """Run one sequential sweep over active products."""

    def __init__(
        self,
        price_checker: PriceChecker,
        session_factory: SessionFactory,
        settings: Settings,
        *,
        min_delay_seconds: float | None = None,
    ) -> None:
        self.price_checker = price_checker
        self.session_factory = session_factory
        self.settings = settings
        self.min_delay_seconds = (
            settings.scraper_min_delay_seconds if min_delay_seconds is None else min_delay_seconds
        )
        self._running = False
        self._idle_event = asyncio.Event()
        self._idle_event.set()

    async def run_sweep(self) -> SweepSummary:
        """Check every active product once without overlapping sweeps."""

        if self._running:
            logger.warning("A price sweep is already running; skipping this run.")
            return SweepSummary()

        self._running = True
        self._idle_event.clear()
        try:
            product_ids = await asyncio.to_thread(self._active_product_ids)
            summary = SweepSummary(total=len(product_ids))

            for index, product_id in enumerate(product_ids):
                if index and self.min_delay_seconds:
                    await asyncio.sleep(self.min_delay_seconds)
                try:
                    result = await self.price_checker.check_product(product_id)
                except Exception:
                    logger.exception(
                        "Automatic price check failed for product %s",
                        product_id,
                    )
                    summary.errors += 1
                    continue

                if result.status is PriceCheckStatus.SUCCESS:
                    summary.succeeded += 1
                elif result.status is PriceCheckStatus.FAILED:
                    summary.failed += 1
                elif result.status is PriceCheckStatus.BUSY:
                    summary.busy += 1
                elif result.status is PriceCheckStatus.NOT_FOUND:
                    summary.not_found += 1

            logger.info(
                "Price sweep completed: total=%s succeeded=%s failed=%s "
                "busy=%s not_found=%s errors=%s",
                summary.total,
                summary.succeeded,
                summary.failed,
                summary.busy,
                summary.not_found,
                summary.errors,
            )
            return summary
        finally:
            self._running = False
            self._idle_event.set()

    async def wait_idle(self, timeout_seconds: float = 10.0) -> None:
        """Wait for the current sweep to finish during shutdown."""

        if self._idle_event.is_set():
            return
        try:
            await asyncio.wait_for(
                self._idle_event.wait(),
                timeout=timeout_seconds,
            )
        except TimeoutError:
            logger.warning("Timed out waiting for the current price sweep to finish.")

    def _active_product_ids(self) -> list[int]:
        with self.session_factory() as session:
            return ProductRepository(session).list_active_ids()
