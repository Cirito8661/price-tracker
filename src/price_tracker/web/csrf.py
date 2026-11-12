"""CSRF protection for local browser forms and HTMX requests."""

from __future__ import annotations

import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import Request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.responses import Response

CSRF_COOKIE_NAME = "pt_csrf"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_MAX_AGE_SECONDS = 2 * 60 * 60
_CSRF_SALT = "price-tracker-csrf"


class CSRFError(Exception):
    """Raised when a state-changing request fails CSRF validation."""


def _serializer(request: Request) -> URLSafeTimedSerializer:
    secret = request.app.state.secret_key.get_secret_value()
    return URLSafeTimedSerializer(secret, salt=_CSRF_SALT)


def get_or_create_csrf_token(request: Request) -> tuple[str, bool]:
    """Return a valid token and whether a new cookie must be set."""

    serializer = _serializer(request)
    token = request.cookies.get(CSRF_COOKIE_NAME)
    if token:
        try:
            serializer.loads(token, max_age=CSRF_MAX_AGE_SECONDS)
            return token, False
        except BadSignature:
            pass
    return serializer.dumps(secrets.token_urlsafe(32)), True


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE_NAME,
        token,
        max_age=CSRF_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )


def _validate_origin(request: Request) -> None:
    allowed_origins = request.app.state.settings.allowed_origins
    origin = request.headers.get("origin")
    if origin:
        if origin not in allowed_origins:
            raise CSRFError("Request origin is not allowed.")
        return

    referer = request.headers.get("referer")
    if referer:
        parsed = urlsplit(referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}"
        if referer_origin not in allowed_origins:
            raise CSRFError("Request referrer is not allowed.")


def validate_csrf(request: Request, submitted_token: str | None) -> None:
    """Validate origin, cookie, and submitted CSRF token."""

    _validate_origin(request)

    token = request.cookies.get(CSRF_COOKIE_NAME)
    if not token or not submitted_token:
        raise CSRFError("CSRF token is missing.")
    if not hmac.compare_digest(token, submitted_token):
        raise CSRFError("CSRF token is invalid.")

    try:
        _serializer(request).loads(token, max_age=CSRF_MAX_AGE_SECONDS)
    except BadSignature as exc:
        raise CSRFError("CSRF token has expired. Reload the page and try again.") from exc


def submitted_csrf_token(
    request: Request,
    form_token: str | None,
) -> str | None:
    """Read a CSRF token from the HTMX header or a form field."""

    return request.headers.get(CSRF_HEADER_NAME) or form_token
