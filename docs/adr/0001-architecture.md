# ADR 0001: Local Modular Monolith

- Status: Accepted
- Date: 2026-11-10

## Context

Price Tracker is a portfolio project and a local single-user application. It must run
on Arch Linux and Windows without cloud infrastructure, user accounts, or a separate
frontend build pipeline.

## Decision

Use a modular monolith with a layered architecture:

- Presentation: FastAPI routes, Jinja2 templates, HTMX fragments.
- Service: business logic for products, checks, monitoring, and notifications.
- Scraping: Playwright lifecycle, URL safety, adapters, BeautifulSoup parsing.
- Data: SQLAlchemy models, repositories, sessions, and Alembic migrations.
- Scheduling: one APScheduler instance with a global sweep.
- Notifications: console and optional SMTP channels.

The application runs as a single process bound to `127.0.0.1`. No React, Vue, Docker,
microservices, or message broker are used.

## Consequences

- The system is simple to run locally and easy to test.
- Multi-worker deployment is unsupported because it would duplicate the scheduler.
- Security controls compensate for the absence of authentication: trusted host checks,
  CSRF protection, Origin validation, security headers, and SSRF protection.
- The service layer remains framework-independent and directly testable.
