# Price Tracker

Local web application for automated product price monitoring.

Price Tracker is a portfolio project built with Python, FastAPI, SQLite, SQLAlchemy,
Jinja2, HTMX, Playwright, and APScheduler. The application is designed to run on the
user's computer and be accessed through a browser at `http://127.0.0.1:8000`.

## Project status

**Stage 6 — Scheduler and notifications are implemented.** The repository currently
contains:

- A validated, environment-driven configuration layer.
- Console and rotating file logging.
- A FastAPI application with a dark, responsive dashboard.
- SQLAlchemy 2.0 models for products, price history, and notifications.
- Decimal-safe price storage and UTC-safe timestamp storage.
- Repositories for products, price history, and notifications.
- SQLite engine configuration with WAL, foreign keys, and busy timeout.
- An initial Alembic migration with upgrade and downgrade tests.
- Web pages for the dashboard, products list, product details, and settings.
- A validated Add Product form with duplicate detection and an initial scrape.
- Manual price checks from the product details page.
- Automatic periodic checks through one APScheduler global interval job.
- Safe scheduler startup, shutdown, overlap protection, and interval rescheduling.
- Successful checks stored in `price_history` with decimal-safe prices and UTC times.
- Price-change classification: initial, decrease, increase, unchanged, and currency
  changed.
- Latest price, previous price, and change amount displayed on product details.
- Real price-history charts from recorded checks; demo data only when no history exists.
- Price-drop and target-price notifications with persistence, cooldown deduplication,
  and bounded retries.
- Console notifications and optional SMTP email notifications.
- Editable scheduler interval and SMTP settings with live status indicators.
- CSRF protection, Origin/Referer validation, trusted hosts, and security headers.
- HTMX interactions for adding products, checking prices, toggling monitoring, and
  deleting products.
- A Playwright browser manager with application-lifetime startup and shutdown.
- DNS resolution and SSRF protection for product URLs, redirects, and subresources.
- A Books to Scrape adapter extracting product name, price, currency, and store.
- Pytest tests for configuration, security, database, web pages, forms, CSRF, scraper
  interfaces, browser lifecycle, DNS/SSRF protection, adapter parsing, price history,
  manual checks, scheduling, notifications, runtime settings, and error handling.
- A GitHub Actions CI workflow for Linux and Windows.

Final release documentation, screenshots, and repository publication preparation are
not complete yet.

## Features planned for v1.0

- Add and delete tracked products by URL.
- Store product metadata and price history in SQLite.
- Scrape supported stores through store-specific adapters.
- First supported store: Books to Scrape (`books.toscrape.com`).
- Scheduled price checks.
- Price-drop and target-price notifications.
- Console notifications and optional SMTP email notifications.
- Browser dashboard and product details page with a locally hosted price chart.
- Responsive desktop and mobile layout.
- Cross-platform support for Arch Linux and Windows 10/11.

## Technology stack

- Python 3.12–3.14
- FastAPI
- Jinja2 and HTMX
- SQLite and SQLAlchemy 2.0
- Alembic
- Pydantic and Pydantic Settings
- APScheduler 3.x
- Playwright
- BeautifulSoup 4
- Chart.js 4 (vendored locally)
- pytest, pytest-asyncio, Ruff

## Architecture overview

The application is a modular monolith with these layers:

- **Presentation:** FastAPI routes, Jinja2 templates, HTMX fragments, and a dark
  responsive interface.
- **Service:** business logic for products, price checks, monitoring, and notifications.
- **Scraping:** Playwright browser lifecycle, URL safety checks, store adapters, and
  BeautifulSoup-based parsing.
- **Data:** SQLAlchemy models, repositories, sessions, and Alembic migrations.
- **Scheduling:** one APScheduler global sweep with per-product concurrency guards.
- **Notifications:** console and SMTP channels with duplicate suppression.

Most web routes are synchronous and use request-scoped SQLAlchemy sessions. The Add
Product route is asynchronous so it can run Playwright while database work is executed
in worker threads. Business logic is kept in the service layer rather than route
handlers. The application is intentionally local-only and runs as a single process.
Multi-worker deployment is not supported because it would start multiple schedulers.

Architecture decision records are stored in [`docs/adr`](docs/adr).

## Requirements

- Python 3.12, 3.13, or 3.14
- Git
- Internet access for installing dependencies
- Chromium for Playwright, installed with `python -m playwright install chromium`

## Installation on Arch Linux

```bash
cd /path/to/price-tracker
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
```

Playwright Chromium installation is required for scraping:

```bash
python -m playwright install chromium
```

On Arch Linux, Playwright may report that the OS is not officially supported and
download its Ubuntu fallback build. If Chromium reports missing shared libraries,
install the required system packages with `pacman`.

## Installation on Windows

Run these commands in PowerShell from the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
```

Playwright Chromium installation is required for scraping:

```powershell
python -m playwright install chromium
```

## Running the application

From the project root, with the virtual environment activated:

```bash
alembic upgrade head
python -m price_tracker.main
```

Alternatively, after installation:

```bash
price-tracker
```

Open `http://127.0.0.1:8000/` for the dashboard. The health endpoint is available at
`http://127.0.0.1:8000/health`.

The application fails fast at startup if the database schema is missing. Run
`alembic upgrade head` first.

For development with automatic reload:

```bash
uvicorn price_tracker.main:app --reload
```

The application must be started from the project root so that the `.env` file and the
relative `data/` and `logs/` directories are resolved consistently. Absolute paths can
be configured with `PT_DATA_DIR` and `PT_LOG_DIR`.

## Web interface

- **Dashboard:** tracked products, active monitoring, products awaiting their first
  check, recent price changes, and recent decreases.
- **Products:** list, validated Add Product form, duplicate detection, initial scrape,
  monitoring toggle, and deletion.
- **Product details:** latest price, previous price, price change, target price, scrape
  status, timestamps, a manual check button, a local price-history chart, and recorded
  checks.
- **Settings:** editable scheduler interval and SMTP configuration with live scheduler
  and email status indicators, plus read-only application, database, scraper, and
  security summaries.
- **HTMX:** partial row updates for monitoring toggles and deletion, redirects after
  Add Product and manual checks, and an inline busy message for overlapping checks.
- **CSRF:** signed tokens are required for state-changing requests, with Origin/Referer
  validation and trusted-host checks.
- **Chart.js:** the library is vendored locally with its MIT license. Charts use real
  recorded history whenever it exists and clearly labeled demo data only when no
  history is available.

Adding a supported product performs an initial Playwright scrape. A successful initial
scrape populates the product and creates its first `price_history` record. A failed
initial scrape still saves the product, preserves any existing valid values, records a
meaningful error, and sets the status to `error`.

## Price monitoring

Manual checks are available from the product details page.

- A successful check appends a `price_history` row with the price, currency, UTC
  timestamp, and change type.
- Change types are `initial`, `decrease`, `increase`, `unchanged`, and
  `currency_changed`.
- The product details page shows the latest price, previous price, and change amount.
- The chart switches from demo data to real history as soon as history exists.
- Products created before Stage 5 with a current price but no history get a one-time
  initial history backfill from their stored price and last successful check time.
- A failed check updates only the attempt timestamp, error message, and scrape status.
  Existing name, price, currency, store, and last successful check remain intact.
- A per-product in-process guard prevents overlapping checks for the same product.
- Automatic periodic checks use one global configurable interval.

## Scheduler and notifications

- One APScheduler `AsyncIOScheduler` job runs a global sweep with `max_instances=1`,
  `coalesce=True`, and a deterministic job id.
- The sweep checks active products sequentially and skips inactive products.
- The scheduler starts during the FastAPI lifespan and stops before the browser and
  database engine are closed.
- The interval can be changed from the Settings page without restarting the process.
- Price-drop notifications are created when a successful check lowers the price.
- Target-price notifications are created only when a check crosses the configured
  target (`old > target >= new`).
- Notifications are persisted with type, old/new prices, currency, status, attempts,
  timestamps, and sanitized error text.
- Duplicate notifications are suppressed by a cooldown window and by retrying existing
  open notifications for the same price.
- Failed notifications are retried up to the configured maximum attempt count.
- Console notifications are always enabled. Email notifications use SMTP with
  STARTTLS or SSL and are automatically disabled when required settings are missing.
- Scheduler and email status are shown on the Settings page.

## Runtime settings

The Settings page edits the global check interval and SMTP configuration. These values
are stored in `data/runtime_settings.json` with owner-only permissions on POSIX
systems. The SMTP password is never displayed in the UI or written to logs. Other
configuration remains in `.env`.

## Scraper engine

- **Supported store:** Books to Scrape (`books.toscrape.com`) only.
- **Browser lifecycle:** one Chromium browser is started in the FastAPI lifespan,
  shared across checks, and closed on application shutdown.
- **Fetching:** Playwright loads the page; BeautifulSoup parses the HTML. JavaScript is
  disabled for the Books to Scrape adapter.
- **URL safety:** URLs are normalized, DNS-resolved, and rejected unless every address
  is public. Loopback, private, link-local, multicast, reserved, and unspecified
  addresses are blocked.
- **Redirects and subresources:** every browser request is validated. Requests to
  undeclared domains, non-default ports, non-HTTP(S) schemes, or private addresses are
  aborted. Images, media, fonts, and other non-essential resource types are blocked.
- **DNS rebinding mitigation:** the target host is re-resolved for each browser
  request, and results must remain within the addresses validated before navigation.
  A small time-of-check/time-of-use window remains because Chromium resolves DNS
  internally; this limitation is documented below.
- **Failure handling:** navigation timeouts, HTTP errors, invalid HTML, missing prices,
  currency errors, and unavailable browsers are converted into safe error messages.
- **Restrictions:** the scraper does not bypass CAPTCHAs, authentication, paywalls,
  anti-bot protections, or other access restrictions.

## Configuration

Copy `.env.example` to `.env` and adjust the values. Environment variables use the
`PT_` prefix. Important settings include:

| Variable | Default | Purpose |
|---|---|---|
| `PT_APP_HOST` | `127.0.0.1` | Bind address. Keep local-only. |
| `PT_APP_PORT` | `8000` | HTTP port. |
| `PT_PUBLIC_BASE_URL` | `http://127.0.0.1:8000` | Origin used for CSRF/Origin validation. |
| `PT_DATA_DIR` | `data` | SQLite database and generated secret location. |
| `PT_LOG_DIR` | `logs` | Rotating log files. |
| `PT_DATABASE_URL` | empty | Optional SQLite URL override; otherwise `data/price_tracker.db`. |
| `PT_SECRET_KEY` | empty | CSRF/signing secret. If empty, `data/.secret` is generated. |
| `PT_ALLOWED_HOSTS` | `["127.0.0.1","localhost"]` | Trusted HTTP Host values. |
| `PT_ALLOWED_PORTS` | `[80,443]` | Permitted outbound URL ports. |
| `PT_CHECK_INTERVAL_SECONDS` | `3600` | Global monitoring interval; minimum 300. |
| `PT_SCRAPER_TIMEOUT_MS` | `30000` | Playwright navigation and selector timeout. |
| `PT_SCRAPER_CONCURRENCY` | `2` | Maximum concurrent browser fetches. |
| `PT_SCRAPER_MIN_DELAY_SECONDS` | `2.0` | Minimum delay between requests to one store. |
| `PT_SCRAPER_MAX_RESPONSE_BYTES` | `5000000` | Maximum accepted HTML response size. |
| `PT_EMAIL_ENABLED` | `true` | Email intent; automatically disabled if SMTP is incomplete. |
| `PT_SMTP_SECURITY` | `starttls` | `starttls` (port 587) or `ssl` (port 465). |

List values use JSON syntax, for example:

```dotenv
PT_ALLOWED_HOSTS=["127.0.0.1","localhost"]
PT_ALLOWED_PORTS=[80,443]
```

If `PT_EMAIL_ENABLED=true` but required SMTP values are missing, email is disabled at
startup and a warning is written to the log. The application continues to run.

## Database

The application uses SQLite through SQLAlchemy 2.0. By default the database file is
`data/price_tracker.db`; set `PT_DATABASE_URL` to use a different SQLite file or an
in-memory database for local experiments. Database files are ignored by Git.

The initial schema contains:

- `products`: tracked URLs, store identifiers, current and target prices, monitoring
  state, scrape status, and timestamps.
- `price_history`: one record per successful price check, including the change type.
- `notifications`: price-drop and target-price events with delivery status and retry
  metadata.

Prices are stored as canonical decimal text and converted to `Decimal` in Python.
Timestamps are stored as UTC and returned as timezone-aware UTC datetimes. SQLite is
configured with `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000`, and
`synchronous=NORMAL`.

### Migrations

Run Alembic commands from the project root with the virtual environment activated:

```bash
alembic upgrade head
alembic current
alembic history
alembic check
```

`alembic check` verifies that the ORM metadata and the migrated database schema are in
sync. `alembic downgrade base` removes the application tables and should only be used
intentionally.

The database file is created by running the migration; the application does not
silently auto-migrate the schema.

## Testing

The test suite includes database type, model constraint, repository, SQLite pragma,
Alembic migration, web page, form validation, CSRF, error page, application lifecycle,
scraper interface, browser lifecycle, DNS/SSRF, redirect/request guard, adapter
parsing, price summary, price history recording, manual check, overlap-guard,
scheduler, notification, SMTP, and runtime-settings tests. Automated tests use
temporary SQLite databases, controlled HTML fixtures, mocked DNS, fake browser
objects, and fake SMTP clients. They do not depend on live websites or real email.

A separate manual live test of Books to Scrape was performed during Stage 4 using the
real Playwright browser and network. It is not part of the automated test suite.

```bash
pytest
```

With coverage:

```bash
pytest --cov=price_tracker --cov-report=term-missing
```

Linting and formatting:

```bash
ruff check .
ruff format --check .
```

## Security notes

- The application binds to `127.0.0.1` only.
- Trusted host validation rejects unexpected `Host` headers.
- CSRF tokens protect state-changing forms and HTMX requests.
- Origin and Referer headers are validated for state-changing requests.
- Security headers include a restrictive Content Security Policy, frame denial,
  MIME sniffing protection, and a no-referrer policy.
- URL validation, DNS resolution, and SSRF protection reject loopback, private,
  link-local, multicast, reserved, unspecified, and non-public addresses.
- Redirects and browser subresources are validated against the adapter's declared
  domains and allowed ports. Non-essential resource types are blocked.
- The target host is re-resolved for browser requests to reduce DNS rebinding risk.
  A residual time-of-check/time-of-use window exists because Chromium resolves DNS
  internally after the application validates it.
- Secrets are loaded from environment variables or a generated `data/.secret` file.
  Runtime SMTP settings are stored in `data/runtime_settings.json`; the password is
  never displayed or logged, and the file is restricted to the owner on POSIX systems.
- The application does not bypass CAPTCHAs, authentication, paywalls, or anti-bot
  protections. Users are responsible for respecting website terms of service.

## Project limitations

- Only one store adapter is implemented in v1.0: Books to Scrape.
- Manual and automatic checks, price history, scheduler, and console/email
  notifications are implemented.
- Notification delivery status is tracked per event, not per channel. If console
  delivery succeeds but email fails, the event is marked sent with an error summary and
  is not retried per channel.
- Scheduler overlap protection is in-process only; multi-worker deployment remains
  unsupported.
- Product detail charts use real history when available and clearly labeled demo data
  only when no history exists.
- DNS rebinding protection is best-effort: the application re-resolves and validates
  requests, but Chromium performs the final DNS resolution, leaving a small
  time-of-check/time-of-use window.
- The Books to Scrape adapter disables JavaScript and blocks images, media, and fonts.
  Other stores will need their own adapters and resource policies.
- The application is single-user and has no authentication. It must not be exposed to
  a network or the public internet.
- Product images are not included in v1.0.
- Per-product check intervals are not included in v1.0.
- SQLite is the only supported database.
- Multi-worker deployment is not supported.
- Scraping is inherently fragile; store page changes may require adapter updates.

## License

MIT License. See [LICENSE](LICENSE).

Copyright (c) 2026 Cirito8661.
