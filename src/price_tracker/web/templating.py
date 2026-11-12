"""Jinja2 template configuration and rendering helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.templating import Jinja2Templates
from starlette.responses import Response

from .csrf import get_or_create_csrf_token, set_csrf_cookie

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

_STORE_LABELS = {
    "books_toscrape": "Books to Scrape",
}


def format_price(value: Any, currency: str | None) -> str:
    if value is None:
        return "—"
    try:
        formatted = f"{value:.2f}"
    except (TypeError, ValueError):
        formatted = str(value)
    return f"{formatted} {currency}" if currency else formatted


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def format_change(value: Any, currency: str | None) -> str:
    if value is None:
        return "—"
    try:
        amount = f"{value:.2f}"
    except (TypeError, ValueError):
        amount = str(value)
    if value > 0:
        amount = f"+{amount}"
    return f"{amount} {currency}" if currency else amount


def url_host(value: str) -> str:
    return urlsplit(value).hostname or value


def store_label(value: str) -> str:
    return _STORE_LABELS.get(value, value)


templates.env.filters["format_price"] = format_price
templates.env.filters["format_datetime"] = format_datetime
templates.env.filters["format_change"] = format_change
templates.env.filters["url_host"] = url_host
templates.env.filters["store_label"] = store_label


def render_template(
    request: Request,
    name: str,
    context: dict[str, Any] | None = None,
    *,
    status_code: int = 200,
) -> Response:
    """Render a template and ensure the CSRF cookie is present."""

    data = dict(context or {})
    token, is_new = get_or_create_csrf_token(request)
    data.setdefault("csrf_token", token)
    data.setdefault("request", request)
    data.setdefault("settings", request.app.state.settings)

    response = templates.TemplateResponse(
        request=request,
        name=name,
        context=data,
        status_code=status_code,
    )
    if is_new:
        set_csrf_cookie(response, token)
    return response
