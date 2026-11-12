"""Small helpers for HTMX request detection."""

from __future__ import annotations

from fastapi import Request


def is_htmx_request(request: Request) -> bool:
    """Return whether the request was issued by HTMX."""

    return request.headers.get("HX-Request", "").lower() == "true"
