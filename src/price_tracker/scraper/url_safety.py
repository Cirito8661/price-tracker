"""URL normalization, DNS validation, and browser request guarding."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Collection
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .errors import DnsResolutionError, UnsafeUrlError

_MAX_URL_LENGTH = 2048
_BLOCKED_HOST_SUFFIXES = (".local", ".internal", ".home.arpa", ".localhost")
_DEFAULT_PORTS = {"http": 80, "https": 443}
_DNS_TIMEOUT_SECONDS = 5.0
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")


class UrlValidationError(ValueError):
    """Raised when a URL is syntactically invalid or clearly unsafe."""


@dataclass(frozen=True)
class ValidatedUrl:
    """A normalized URL with the DNS addresses validated at check time."""

    url: str
    scheme: str
    host: str
    port: int
    ips: frozenset[str]


def _validate_host(host: str) -> str:
    normalized = host.strip().lower().rstrip(".")
    if not normalized:
        raise UrlValidationError("Enter a URL with a valid hostname.")

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        try:
            normalized = normalized.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise UrlValidationError("The URL hostname is not valid.") from exc
    else:
        if not address.is_global:
            raise UrlValidationError("Local and private network addresses are not allowed.")
        return normalized

    if normalized == "localhost" or normalized.endswith(_BLOCKED_HOST_SUFFIXES):
        raise UrlValidationError("Local and private network addresses are not allowed.")
    return normalized


def normalize_product_url(raw_url: str) -> str:
    """Validate URL syntax and normalize it for storage and duplicate checks."""

    value = raw_url.strip()
    if not value:
        raise UrlValidationError("Enter a product URL.")
    if len(value) > _MAX_URL_LENGTH:
        raise UrlValidationError("The URL is too long.")
    if any(character.isspace() for character in value):
        raise UrlValidationError("The URL must not contain spaces.")

    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        username = parsed.username
        password = parsed.password
    except ValueError as exc:
        raise UrlValidationError("The URL is not valid.") from exc

    scheme = parsed.scheme.lower()
    if scheme not in _DEFAULT_PORTS:
        raise UrlValidationError("Only http and https URLs are supported.")
    if username or password:
        raise UrlValidationError("URLs with embedded credentials are not allowed.")
    if not hostname:
        raise UrlValidationError("Enter a URL with a valid hostname.")

    host = _validate_host(hostname)
    try:
        port = parsed.port
    except ValueError as exc:
        raise UrlValidationError("The URL contains an invalid port.") from exc

    netloc = f"[{host}]" if ":" in host else host
    if port is not None and port != _DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"

    path = parsed.path or "/"
    normalized = urlunsplit((scheme, netloc, path, parsed.query, ""))
    if len(normalized) > _MAX_URL_LENGTH:
        raise UrlValidationError("The URL is too long.")
    return normalized


def store_from_url(url: str) -> str:
    """Derive a provisional store identifier from a normalized URL."""

    host = (urlsplit(url).hostname or "unknown").lower().rstrip(".")
    return host[:64]


def is_public_ip(value: str) -> bool:
    """Return whether an IP is globally routable and not special-use."""

    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False

    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped

    if isinstance(address, ipaddress.IPv4Address) and address in _SHARED_ADDRESS_SPACE:
        return False

    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or not address.is_global
    )


async def resolve_host_ips(host: str, port: int) -> frozenset[str]:
    """Resolve a host to all current IP addresses."""

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return frozenset({str(literal)})

    loop = asyncio.get_running_loop()
    try:
        results = await asyncio.wait_for(
            loop.getaddrinfo(
                host,
                port,
                type=socket.SOCK_STREAM,
            ),
            timeout=_DNS_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise DnsResolutionError("DNS resolution timed out.") from exc
    except (socket.gaierror, OSError) as exc:
        raise DnsResolutionError("Could not resolve the product hostname.") from exc

    addresses = {result[4][0].split("%", 1)[0] for result in results if result[4]}
    if not addresses:
        raise DnsResolutionError("The product hostname did not resolve to an address.")
    return frozenset(addresses)


async def validate_public_url(
    url: str,
    *,
    allowed_ports: Collection[int] = (80, 443),
) -> ValidatedUrl:
    """Normalize a URL, resolve it, and require every address to be public."""

    normalized = normalize_product_url(url)
    parsed = urlsplit(normalized)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower().rstrip(".")
    port = parsed.port or _DEFAULT_PORTS[scheme]

    if port not in set(allowed_ports):
        raise UnsafeUrlError(f"Port {port} is not allowed for scraping.")

    ips = await resolve_host_ips(host, port)
    if not all(is_public_ip(ip) for ip in ips):
        raise UnsafeUrlError("The product hostname resolves to a non-public address.")

    return ValidatedUrl(
        url=normalized,
        scheme=scheme,
        host=host,
        port=port,
        ips=ips,
    )


class RequestGuard:
    """Validate redirects and subresource requests made by the browser.

    The guard re-resolves DNS for every request and, for the target host,
    requires the result to remain within the addresses validated before
    navigation. This mitigates DNS rebinding during a check. A small
    time-of-check/time-of-use window remains between validation and the
    browser's TCP connection because Playwright resolves DNS internally.
    """

    def __init__(
        self,
        target: ValidatedUrl,
        *,
        allowed_domains: Collection[str],
        allowed_ports: Collection[int] = (80, 443),
    ) -> None:
        self.target = target
        self.allowed_domains = {domain.lower().rstrip(".") for domain in allowed_domains}
        self.allowed_ports = set(allowed_ports)

    async def validate(self, url: str) -> None:
        """Raise :class:`UnsafeUrlError` when a browser request is not allowed."""

        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            username = parsed.username
            password = parsed.password
        except ValueError as exc:
            raise UnsafeUrlError("Blocked a malformed browser request URL.") from exc

        scheme = parsed.scheme.lower()
        if scheme not in _DEFAULT_PORTS:
            raise UnsafeUrlError("Blocked a non-HTTP(S) browser request.")
        if username or password:
            raise UnsafeUrlError("Blocked a browser request with credentials.")

        host = (hostname or "").lower().rstrip(".")
        if not host:
            raise UnsafeUrlError("Blocked a browser request without a host.")
        if host not in self.allowed_domains:
            raise UnsafeUrlError(f"Blocked a browser request to {host}.")

        try:
            port = parsed.port
        except ValueError as exc:
            raise UnsafeUrlError("Blocked a browser request with an invalid port.") from exc
        if port is None:
            port = _DEFAULT_PORTS[scheme]
        if port not in self.allowed_ports:
            raise UnsafeUrlError(f"Blocked a browser request on port {port}.")

        ips = await resolve_host_ips(host, port)
        if not all(is_public_ip(ip) for ip in ips):
            raise UnsafeUrlError("Blocked a browser request resolving to a non-public address.")
        if host == self.target.host and not ips.issubset(self.target.ips):
            raise UnsafeUrlError("Blocked a browser request after the DNS result changed.")
