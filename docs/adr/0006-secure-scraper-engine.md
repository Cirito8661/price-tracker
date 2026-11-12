# ADR 0006: Secure Scraper Engine

- Status: Accepted
- Date: 2026-11-10

## Context

The application must fetch product pages from user-provided URLs without allowing
server-side request forgery or DNS rebinding. Playwright must remain alive for the
application's lifetime, and store-specific parsing must be testable without live
network access.

## Decision

- Use one Playwright Chromium browser per application process, started in the FastAPI
  lifespan and closed during shutdown.
- Use a new browser context for each check, a concurrency semaphore, blocked service
  workers, disabled downloads, and strict HTTPS certificate validation.
- Keep fetching in Playwright and parsing in BeautifulSoup. Each store adapter
  implements a pure `parse(html, url)` method.
- Resolve and validate DNS before navigation. Reject any address that is not globally
  routable and not a normal public address.
- Validate every redirect and subresource through Playwright route interception.
  Restrict requests to the adapter's declared domains and allowed ports, and block
  non-essential resource types.
- Re-resolve the target host for each browser request and require the result to remain
  within the addresses validated before navigation.
- Treat navigation, HTTP, parsing, currency, and browser-availability failures as safe
  scraper errors. Failed scrapes preserve existing valid product fields and record an
  error message.
- Do not bypass CAPTCHAs, authentication, paywalls, or anti-bot restrictions.

## Consequences

- The application can safely scrape the approved Books to Scrape domain while rejecting
  local, private, and unexpected destinations.
- Browser processes are closed during graceful application shutdown.
- Adapter parsing is covered by fast fixture tests; browser behavior is covered by
  mocked Playwright objects.
- A residual DNS time-of-check/time-of-use window remains because Chromium performs its
  own final DNS resolution. The application mitigates this with pre-validation,
  per-request re-resolution, and final-URL validation, and documents the limitation.
- Blocking images, media, and fonts reduces bandwidth and request surface but may need
  per-adapter adjustment for future stores.
