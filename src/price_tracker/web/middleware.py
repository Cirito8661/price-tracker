"""Security-related ASGI middleware."""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
    ]
)

_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=()"


class SecurityHeadersMiddleware:
    """Add conservative security headers to every HTTP response."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("Permissions-Policy", _PERMISSIONS_POLICY)
                headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
                headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
            await send(message)

        await self.app(scope, receive, send_with_headers)
