"""FastAPI application factory and entry point."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response

from .config import Settings
from .database.engine import create_engine_from_settings
from .database.schema import verify_database_schema
from .database.session import create_session_factory
from .logging_config import configure_logging
from .notifications.console import ConsoleNotifier
from .notifications.email import EmailNotifier
from .runtime_settings import RuntimeSettingsStore
from .scheduler.scheduler import MonitoringScheduler
from .scraper.browser import BrowserManager
from .scraper.registry import build_default_registry
from .scraper.service import ScraperService
from .services.monitoring_service import MonitoringService
from .services.notification_service import NotificationService
from .services.price_checker import PriceChecker
from .services.product_scrape_service import ProductScrapeService
from .services.product_service import ProductNotFoundError
from .web.csrf import CSRFError
from .web.errors import render_error
from .web.middleware import SecurityHeadersMiddleware
from .web.routes import dashboard, products
from .web.routes import settings as settings_routes

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    settings: Settings | None = None,
    *,
    browser_manager: BrowserManager | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""

    resolved_settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        resolved_settings.ensure_directories()
        configure_logging(resolved_settings)

        secret_key = resolved_settings.resolve_secret_key()
        app.state.settings = resolved_settings
        app.state.secret_key = secret_key

        runtime_store = RuntimeSettingsStore(
            resolved_settings.data_dir / "runtime_settings.json",
            resolved_settings,
        )
        app.state.runtime_settings = runtime_store

        engine = create_engine_from_settings(resolved_settings)
        try:
            verify_database_schema(engine)
        except Exception:
            engine.dispose()
            logger.exception("Database schema verification failed")
            raise

        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)

        def settings_provider() -> Settings:
            return runtime_store.effective_settings

        notification_service = NotificationService(
            app.state.session_factory,
            [
                ConsoleNotifier(),
                EmailNotifier(settings_provider),
            ],
            settings_provider,
        )
        app.state.notification_service = notification_service

        manager = browser_manager or BrowserManager(resolved_settings)
        scraper_service = ScraperService(
            manager,
            build_default_registry(),
            resolved_settings,
        )
        app.state.browser_manager = manager
        app.state.scraper_service = scraper_service
        app.state.product_scrape_service = ProductScrapeService(
            scraper_service,
            app.state.session_factory,
            resolved_settings,
        )
        price_checker = PriceChecker(
            scraper_service,
            app.state.session_factory,
            resolved_settings,
            notification_service=notification_service,
        )
        app.state.price_checker = price_checker
        monitoring_service = MonitoringService(
            price_checker,
            app.state.session_factory,
            resolved_settings,
        )
        monitoring_scheduler = MonitoringScheduler(
            monitoring_service,
            interval_seconds=runtime_store.effective_settings.check_interval_seconds,
        )
        app.state.monitoring_service = monitoring_service
        app.state.monitoring_scheduler = monitoring_scheduler

        warning = runtime_store.effective_settings.email_configuration_warning
        if warning:
            logger.warning(warning)

        logger.info(
            "Starting %s v%s on %s:%s",
            resolved_settings.app_name,
            resolved_settings.app_version,
            resolved_settings.app_host,
            resolved_settings.app_port,
        )
        logger.info("Database URL: %s", resolved_settings.effective_database_url)
        logger.info(
            "Check interval: %s seconds",
            runtime_store.effective_settings.check_interval_seconds,
        )

        try:
            await manager.start()
            if manager.available:
                monitoring_scheduler.start()
            else:
                logger.warning(
                    "Scraping and automatic monitoring are unavailable until "
                    "Chromium is installed with "
                    "`python -m playwright install chromium`."
                )
            yield
        finally:
            logger.info("Stopping %s", resolved_settings.app_name)
            monitoring_scheduler.stop()
            await monitoring_service.wait_idle(timeout_seconds=10.0)
            await manager.stop()
            engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        debug=resolved_settings.app_debug,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.allowed_hosts,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    app.mount(
        "/static",
        StaticFiles(directory=str(STATIC_DIR)),
        name="static",
    )

    app.include_router(dashboard.router)
    app.include_router(products.router)
    app.include_router(settings_routes.router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "name": resolved_settings.app_name,
            "version": resolved_settings.app_version,
        }

    @app.exception_handler(CSRFError)
    async def handle_csrf_error(
        request: Request,
        exc: CSRFError,
    ) -> Response:
        return render_error(
            request,
            403,
            "Request blocked",
            str(exc),
        )

    @app.exception_handler(ProductNotFoundError)
    async def handle_product_not_found(
        request: Request,
        exc: ProductNotFoundError,
    ) -> Response:
        return render_error(
            request,
            404,
            "Product not found",
            "The requested product does not exist.",
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request,
        exc: StarletteHTTPException,
    ) -> Response:
        if exc.status_code == 404:
            return render_error(
                request,
                404,
                "Page not found",
                "The requested page does not exist.",
            )
        return render_error(
            request,
            exc.status_code,
            "Request failed",
            str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_exception(
        request: Request,
        exc: Exception,
    ) -> Response:
        logger.exception(
            "Unhandled exception while processing %s %s",
            request.method,
            request.url.path,
        )
        return render_error(
            request,
            500,
            "Something went wrong",
            "An unexpected error occurred. Check the application logs for details.",
        )

    return app


app = create_app()


def run() -> None:
    """Run the local development server."""

    import uvicorn

    settings: Settings = app.state.settings
    settings.ensure_directories()
    configure_logging(settings)

    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
    )


if __name__ == "__main__":
    run()
