"""Books to Scrape adapter."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import ClassVar

from bs4 import BeautifulSoup

from ...database.types import parse_decimal
from ..base import BaseScraper, ScrapedProduct
from ..errors import (
    CurrencyParseError,
    InvalidPageError,
    InvalidPriceError,
    PriceNotFoundError,
    UnsupportedStoreError,
)

_SYMBOL_TO_CURRENCY = {
    "£": "GBP",
    "$": "USD",
    "€": "EUR",
    "¥": "JPY",
}
_AMOUNT_PATTERN = re.compile(r"^\d[\d,]*(?:\.\d{1,4})?$")


def parse_price_text(text: str) -> tuple[Decimal, str]:
    """Parse a store price string such as ``£51.77``."""

    normalized = " ".join(text.split())
    symbol = next(
        (candidate for candidate in _SYMBOL_TO_CURRENCY if candidate in normalized),
        None,
    )
    if symbol is None:
        raise CurrencyParseError("Could not determine the product currency from the price text.")

    amount_text = normalized.replace(symbol, "", 1).strip()
    if not _AMOUNT_PATTERN.match(amount_text):
        raise InvalidPriceError("The product price is not in a recognized format.")

    try:
        price = parse_decimal(amount_text.replace(",", ""))
    except (TypeError, ValueError) as exc:
        raise InvalidPriceError("The product price is invalid.") from exc

    return price, _SYMBOL_TO_CURRENCY[symbol]


class BooksToScrapeAdapter(BaseScraper):
    """Adapter for the Books to Scrape demonstration store."""

    store_id: ClassVar[str] = "books_toscrape"
    store_name: ClassVar[str] = "Books to Scrape"
    domains: ClassVar[tuple[str, ...]] = (
        "books.toscrape.com",
        "www.books.toscrape.com",
    )
    allowed_subresource_domains: ClassVar[tuple[str, ...]] = domains
    requires_javascript: ClassVar[bool] = False
    wait_for_selector: ClassVar[str | None] = "h1"

    def parse(self, html: str, url: str) -> ScrapedProduct:
        if not self.supports(url):
            raise UnsupportedStoreError(f"{self.store_name} does not support this URL.")

        soup = BeautifulSoup(html, "html.parser")

        heading = soup.find("h1")
        name = " ".join(heading.get_text(" ", strip=True).split()) if heading is not None else ""
        if not name:
            raise InvalidPageError("Product name was not found on the page.")

        price_element = soup.select_one("p.price_color")
        if price_element is None:
            raise PriceNotFoundError("Product price was not found on the page.")

        price, currency = parse_price_text(price_element.get_text(" ", strip=True))
        return ScrapedProduct(
            name=name,
            price=price,
            currency=currency,
            url=url,
            store=self.store_id,
        )
