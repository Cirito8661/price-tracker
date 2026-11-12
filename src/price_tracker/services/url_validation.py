"""Product target-price validation and URL safety re-exports."""

from __future__ import annotations

from decimal import Decimal

from ..database.types import parse_decimal
from ..scraper.url_safety import (
    UrlValidationError,
    normalize_product_url,
    store_from_url,
)

_TARGET_PRICE_ERROR = "Enter a valid non-negative price with up to 4 decimal places."


def parse_target_price(raw_value: str | None) -> Decimal | None:
    """Parse an optional user-entered target price."""

    if raw_value is None or not raw_value.strip():
        return None
    try:
        return parse_decimal(raw_value.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(_TARGET_PRICE_ERROR) from exc


__all__ = [
    "UrlValidationError",
    "normalize_product_url",
    "parse_target_price",
    "store_from_url",
]
