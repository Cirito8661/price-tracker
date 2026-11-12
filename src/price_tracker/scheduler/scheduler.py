"""APScheduler lifecycle for automatic price sweeps."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from ..services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)

_JOB_ID = "price-sweep"


class MonitoringScheduler:
    """Own one global interval job for automatic price checks."""

    def __init__(
        self,
        monitoring_service: MonitoringService,
        interval_seconds: int,
    ) -> None:
        self.monitoring_service = monitoring_service
        self._interval_seconds = interval_seconds
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._started = False

    @property
    def running(self) -> bool:
        return self._started and self._scheduler.running

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    @property
    def next_run_time(self):
        if not self._started:
            return None
        job = self._scheduler.get_job(_JOB_ID)
        return job.next_run_time if job is not None else None

    @property
    def job_count(self) -> int:
        return len(self._scheduler.get_jobs())

    def start(self) -> None:
        """Start the single global sweep job."""

        if self._scheduler.running:
            return

        try:
            self._scheduler.add_job(
                self._run_sweep,
                trigger=IntervalTrigger(seconds=self._interval_seconds),
                id=_JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                misfire_grace_time=300,
            )
            self._scheduler.start()
        except Exception:
            logger.exception("Could not start the monitoring scheduler")
            return

        self._started = True
        logger.info(
            "Monitoring scheduler started with a %s second interval",
            self._interval_seconds,
        )

    def stop(self) -> None:
        """Stop the scheduler without waiting for a running sweep."""

        if not self._started:
            return
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            logger.exception("Could not stop the monitoring scheduler")
        finally:
            self._started = False
        logger.info("Monitoring scheduler stopped")

    def reschedule(self, interval_seconds: int) -> None:
        """Change the global interval, applying it immediately if running."""

        self._interval_seconds = interval_seconds
        if not self._scheduler.running:
            return
        try:
            self._scheduler.reschedule_job(
                _JOB_ID,
                trigger=IntervalTrigger(seconds=interval_seconds),
            )
        except Exception:
            logger.exception("Could not reschedule the monitoring job")
            return
        logger.info(
            "Monitoring scheduler interval changed to %s seconds",
            interval_seconds,
        )

    async def _run_sweep(self) -> None:
        try:
            await self.monitoring_service.run_sweep()
        except Exception:
            logger.exception("Automatic price sweep failed")
