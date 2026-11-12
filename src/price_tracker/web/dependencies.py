"""FastAPI dependencies for the web layer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..services.price_checker import PriceChecker
from ..services.product_scrape_service import ProductScrapeService
from ..services.product_service import ProductService


def get_session(request: Request) -> Iterator[Session]:
    """Provide a request-scoped database session."""

    session_factory = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_settings(request: Request) -> Settings:
    """Return the application settings."""

    return request.app.state.settings


def get_product_service(
    session: Annotated[Session, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProductService:
    """Build the product service for a request."""

    return ProductService(
        session,
        recent_decrease_days=settings.recent_decrease_days,
        allowed_ports=settings.allowed_ports,
    )


def get_product_scrape_service(request: Request) -> ProductScrapeService:
    """Return the application-level initial scraping coordinator."""

    return request.app.state.product_scrape_service


def get_price_checker(request: Request) -> PriceChecker:
    """Return the application-level manual price checker."""

    return request.app.state.price_checker


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
ProductScrapeServiceDep = Annotated[
    ProductScrapeService,
    Depends(get_product_scrape_service),
]
PriceCheckerDep = Annotated[PriceChecker, Depends(get_price_checker)]
