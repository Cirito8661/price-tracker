"""Product business logic for the web interface."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..clock import utcnow
from ..models.enums import PriceChangeType, ScrapeStatus
from ..models.price_history import PriceHistory
from ..models.product import Product
from ..repositories.price_history import PriceHistoryRepository
from ..repositories.products import ProductRepository
from ..scraper.base import ScrapedProduct
from ..scraper.errors import UnsafeUrlError
from ..scraper.url_safety import validate_public_url
from .url_validation import (
    UrlValidationError,
    normalize_product_url,
    parse_target_price,
    store_from_url,
)

_MAX_ERROR_LENGTH = 2000


class ProductServiceError(Exception):
    """Base class for product service errors."""


class ProductValidationError(ProductServiceError):
    """Raised when submitted product data is invalid."""

    def __init__(
        self,
        errors: dict[str, str],
        message: str = "Please correct the errors below.",
    ) -> None:
        super().__init__(message)
        self.errors = errors
        self.message = message


class DuplicateProductError(ProductServiceError):
    """Raised when a product URL is already tracked."""

    def __init__(self, existing_product_id: int | None = None) -> None:
        super().__init__("This product is already tracked.")
        self.existing_product_id = existing_product_id


class ProductNotFoundError(ProductServiceError):
    """Raised when a product does not exist."""

    def __init__(self, product_id: int) -> None:
        super().__init__(f"Product {product_id} was not found.")
        self.product_id = product_id


@dataclass(frozen=True)
class PreparedProduct:
    """Validated values needed to create a new product record."""

    url: str
    store: str
    target_price: Decimal | None


@dataclass(frozen=True)
class PriceCheckRecord:
    """Result of recording one successful price check."""

    product: Product
    history: PriceHistory
    previous_price: Decimal | None
    previous_currency: str | None
    previous_checked_at: datetime | None
    change_type: PriceChangeType


@dataclass(frozen=True)
class DashboardSummary:
    """Data required to render the dashboard."""

    total_products: int
    active_products: int
    awaiting_first_check: int
    recent_decrease_count: int
    products: list[Product]
    recent_changes: list[tuple[PriceHistory, Product]]
    recent_decreases: list[PriceHistory]


def _truncate_error(message: str | None) -> str | None:
    if message is None:
        return None
    cleaned = " ".join(message.split())
    return cleaned[:_MAX_ERROR_LENGTH] if cleaned else None


class ProductService:
    """Application-level product operations."""

    def __init__(
        self,
        session: Session,
        *,
        recent_decrease_days: int = 7,
        allowed_ports: Collection[int] = (80, 443),
    ) -> None:
        self.session = session
        self.recent_decrease_days = recent_decrease_days
        self.allowed_ports = tuple(allowed_ports)
        self.products = ProductRepository(session)
        self.history = PriceHistoryRepository(session)

    def list_products(self) -> list[Product]:
        return self.products.list()

    def get_product(self, product_id: int) -> Product | None:
        return self.products.get(product_id)

    def get_product_or_raise(self, product_id: int) -> Product:
        product = self.get_product(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product

    def get_price_history(self, product_id: int) -> list[PriceHistory]:
        return self.history.list_for_product(product_id)

    def prepare_new_product(
        self,
        raw_url: str,
        raw_target_price: str | None = None,
        *,
        store: str | None = None,
    ) -> PreparedProduct:
        """Validate a new product and check for duplicates without writing."""

        errors: dict[str, str] = {}

        try:
            normalized_url = normalize_product_url(raw_url)
        except UrlValidationError as exc:
            errors["url"] = str(exc)
            normalized_url = ""

        try:
            target_price = parse_target_price(raw_target_price)
        except ValueError as exc:
            errors["target_price"] = str(exc)
            target_price = None

        if errors:
            raise ProductValidationError(errors)

        existing = self.products.get_by_url(normalized_url)
        if existing is not None:
            raise DuplicateProductError(existing.id)

        resolved_store = (store or store_from_url(normalized_url))[:64]
        return PreparedProduct(
            url=normalized_url,
            store=resolved_store,
            target_price=target_price,
        )

    def persist_new_product(
        self,
        prepared: PreparedProduct,
        scrape_result: ScrapedProduct | None,
        scrape_error: str | None,
        *,
        scrape_attempted: bool = True,
    ) -> Product:
        """Create a product record after validation and optional scraping."""

        product = Product(
            url=prepared.url,
            name=None,
            store=prepared.store,
            current_price=None,
            currency=None,
            target_price=prepared.target_price,
            is_active=True,
            scrape_status=ScrapeStatus.PENDING,
            last_error=None,
            last_checked_at=None,
            last_attempt_at=None,
        )

        if scrape_attempted and scrape_result is not None:
            self._apply_success_fields(product, scrape_result)
        elif scrape_attempted:
            product.scrape_status = ScrapeStatus.ERROR
            product.last_error = _truncate_error(scrape_error or "The initial price check failed.")
            product.last_attempt_at = utcnow()

        try:
            self.products.add(product)
            if scrape_attempted and scrape_result is not None:
                self.history.add(
                    PriceHistory(
                        product=product,
                        price=scrape_result.price,
                        currency=scrape_result.currency,
                        change_type=PriceChangeType.INITIAL,
                        checked_at=scrape_result.retrieved_at,
                    )
                )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateProductError() from exc

        return product

    def _apply_success_fields(
        self,
        product: Product,
        scrape_result: ScrapedProduct,
    ) -> None:
        product.name = scrape_result.name
        product.current_price = scrape_result.price
        product.currency = scrape_result.currency
        product.store = scrape_result.store
        product.scrape_status = ScrapeStatus.OK
        product.last_error = None
        product.last_checked_at = scrape_result.retrieved_at
        product.last_attempt_at = scrape_result.retrieved_at

    def record_price_check(
        self,
        product_id: int,
        scrape_result: ScrapedProduct,
    ) -> PriceCheckRecord:
        """Record a successful manual check and update the product."""

        product = self.get_product_or_raise(product_id)
        latest = self.history.latest_for_product(product_id)

        if (
            latest is None
            and product.current_price is not None
            and product.currency is not None
            and product.last_checked_at is not None
        ):
            latest = PriceHistory(
                product=product,
                price=product.current_price,
                currency=product.currency,
                change_type=PriceChangeType.INITIAL,
                checked_at=product.last_checked_at,
            )
            self.history.add(latest)

        previous_price = latest.price if latest is not None else None
        previous_currency = latest.currency if latest is not None else None
        previous_checked_at = latest.checked_at if latest is not None else None

        if previous_price is None:
            change_type = PriceChangeType.INITIAL
        elif previous_currency != scrape_result.currency:
            change_type = PriceChangeType.CURRENCY_CHANGED
        elif scrape_result.price < previous_price:
            change_type = PriceChangeType.DECREASE
        elif scrape_result.price > previous_price:
            change_type = PriceChangeType.INCREASE
        else:
            change_type = PriceChangeType.UNCHANGED

        entry = PriceHistory(
            product=product,
            price=scrape_result.price,
            currency=scrape_result.currency,
            change_type=change_type,
            checked_at=scrape_result.retrieved_at,
        )
        self.history.add(entry)
        self._apply_success_fields(product, scrape_result)
        self.session.commit()

        return PriceCheckRecord(
            product=product,
            history=entry,
            previous_price=previous_price,
            previous_currency=previous_currency,
            previous_checked_at=previous_checked_at,
            change_type=change_type,
        )

    def apply_scrape_result(
        self,
        product_id: int,
        scrape_result: ScrapedProduct | None,
        scrape_error: str | None,
    ) -> Product:
        """Apply a scrape result to an existing product.

        Failures update only attempt metadata and the error message. Existing
        valid name, price, currency, store, and last successful check are kept.
        """

        product = self.get_product_or_raise(product_id)

        if scrape_result is not None:
            self._apply_success_fields(product, scrape_result)
        else:
            product.scrape_status = ScrapeStatus.ERROR
            product.last_error = _truncate_error(scrape_error or "The price check failed.")
            product.last_attempt_at = utcnow()

        self.session.commit()
        return product

    async def add_product(
        self,
        raw_url: str,
        raw_target_price: str | None = None,
    ) -> Product:
        """Add a pending product only after DNS safety validation."""

        prepared = self.prepare_new_product(raw_url, raw_target_price)
        try:
            await validate_public_url(
                prepared.url,
                allowed_ports=self.allowed_ports,
            )
        except (UnsafeUrlError, UrlValidationError) as exc:
            raise ProductValidationError({"url": str(exc)}) from exc

        return self.persist_new_product(
            prepared,
            None,
            None,
            scrape_attempted=False,
        )

    def toggle_active(self, product_id: int) -> Product:
        product = self.get_product_or_raise(product_id)
        product.is_active = not product.is_active
        self.session.commit()
        return product

    def delete_product(self, product_id: int) -> None:
        product = self.get_product_or_raise(product_id)
        self.products.delete(product)
        self.session.commit()

    def dashboard_summary(self) -> DashboardSummary:
        since = utcnow() - timedelta(days=self.recent_decrease_days)
        return DashboardSummary(
            total_products=self.products.count(),
            active_products=self.products.count(active_only=True),
            awaiting_first_check=self.products.count_awaiting_first_check(),
            recent_decrease_count=self.history.count_recent_decreases(since),
            products=self.products.list(limit=5),
            recent_changes=self.history.recent_changes(limit=5),
            recent_decreases=self.history.recent_decreases(since, limit=5),
        )
