# ADR 0003: Scraping and Scheduling Model

- Status: Accepted
- Date: 2026-11-10

## Context

Playwright starts a browser process and requires careful lifecycle management.
APScheduler must not launch overlapping sweeps, and manual checks must not race with
scheduled checks for the same product. Parsing must be testable without a live browser
or a live website.

## Decision

- `BrowserManager` starts one Playwright browser in the FastAPI lifespan, limits
  concurrency with a semaphore, isolates each check in a new browser context, and closes
  the browser on shutdown.
- Playwright is responsible only for fetching HTML.
- BeautifulSoup is responsible for parsing HTML. Each store adapter implements a pure
  `parse(html, url)` method and is tested with local HTML fixtures.
- Adapters are selected by an explicit domain registry. Unsupported stores are rejected;
  there is no universal scraper.
- One `AsyncIOScheduler` job runs a global sweep with `max_instances=1` and
  `coalesce=True`.
- A shared per-product `asyncio.Lock` prevents duplicate scheduled and manual checks.
- The sweep is sequential by default and enforces a per-store minimum delay.

## Consequences

- Browser processes cannot leak across requests or shutdowns.
- Adapter parsing is fast to test and independent of network access.
- Scheduler overlap and duplicate product checks are prevented in a single process.
- Per-product intervals and parallel sweeps are intentionally deferred beyond v1.0.
