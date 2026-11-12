"""Scheduler and global sweep tests."""

from __future__ import annotations

from price_tracker.config import Settings
from price_tracker.database.session import SessionFactory
from price_tracker.main import create_app
from price_tracker.scheduler.scheduler import MonitoringScheduler
from price_tracker.services.monitoring_service import MonitoringService
from price_tracker.services.price_checker import (
    PriceCheckResult,
    PriceCheckStatus,
)
from tests.fakes import FakeBrowserManager
from tests.web_helpers import create_product


class FakeChecker:
    def __init__(self, status: PriceCheckStatus = PriceCheckStatus.SUCCESS) -> None:
        self.status = status
        self.checked: list[int] = []

    async def check_product(self, product_id: int) -> PriceCheckResult:
        self.checked.append(product_id)
        return PriceCheckResult(status=self.status, product_id=product_id)


class FakeMonitoring:
    def __init__(self) -> None:
        self.calls = 0

    async def run_sweep(self) -> None:
        self.calls += 1


async def test_sweep_checks_only_active_products(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    active = create_product(web_session_factory, is_active=True)
    create_product(
        web_session_factory,
        url="https://books.toscrape.com/catalogue/inactive.html",
        is_active=False,
    )
    checker = FakeChecker()
    service = MonitoringService(
        checker,
        web_session_factory,
        initialized_settings,
        min_delay_seconds=0,
    )

    summary = await service.run_sweep()

    assert checker.checked == [active.id]
    assert summary.total == 1
    assert summary.succeeded == 1
    await service.wait_idle(timeout_seconds=0.1)


async def test_sweep_counts_checker_errors(
    web_session_factory: SessionFactory,
    initialized_settings: Settings,
) -> None:
    create_product(web_session_factory)

    class FailingChecker:
        async def check_product(self, product_id: int):
            raise RuntimeError("checker failed")

    service = MonitoringService(
        FailingChecker(),
        web_session_factory,
        initialized_settings,
        min_delay_seconds=0,
    )

    summary = await service.run_sweep()

    assert summary.errors == 1
    assert summary.succeeded == 0


async def test_scheduler_lifecycle_and_reschedule() -> None:
    monitoring = FakeMonitoring()
    scheduler = MonitoringScheduler(monitoring, interval_seconds=3600)

    try:
        scheduler.start()
        assert scheduler.running is True
        assert scheduler.job_count == 1
        assert scheduler.next_run_time is not None

        scheduler.start()
        assert scheduler.job_count == 1

        scheduler.reschedule(600)
        assert scheduler.interval_seconds == 600
        assert scheduler.next_run_time is not None
    finally:
        scheduler.stop()

    assert scheduler.running is False


async def test_app_lifespan_starts_and_stops_scheduler(
    initialized_settings: Settings,
) -> None:
    app = create_app(
        initialized_settings,
        browser_manager=FakeBrowserManager(),
    )

    async with app.router.lifespan_context(app):
        assert app.state.monitoring_scheduler.running is True
        assert app.state.monitoring_scheduler.job_count == 1

    assert app.state.monitoring_scheduler.running is False
