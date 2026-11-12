"""HTML error rendering for web requests."""

from __future__ import annotations

import html

from fastapi import Request
from starlette.responses import HTMLResponse, Response

from .htmx import is_htmx_request
from .templating import render_template


def render_error(
    request: Request,
    status_code: int,
    title: str,
    message: str,
) -> Response:
    """Render a safe error page or HTMX error fragment."""

    context = {
        "error_code": status_code,
        "error_title": title,
        "error_message": message,
        "page_title": title,
    }
    template = "partials/error.html" if is_htmx_request(request) else "errors/error.html"

    try:
        return render_template(
            request,
            template,
            context,
            status_code=status_code,
        )
    except Exception:
        fallback = f"<h1>{status_code} {html.escape(title)}</h1><p>{html.escape(message)}</p>"
        return HTMLResponse(fallback, status_code=status_code)
