# ADR 0005: Server-Rendered Web Interface and Local Assets

- Status: Accepted
- Date: 2026-11-10

## Context

The application needs a dark, responsive local dashboard without introducing a
separate frontend framework or a build pipeline. Forms must be safe against CSRF and
cross-origin browser requests. The interface must work offline and must not invent
product data before scraping exists.

## Decision

- Use FastAPI with Jinja2 templates and HTMX fragments.
- Keep web routes thin and delegate business logic to `ProductService`.
- Use synchronous SQLAlchemy sessions through a request-scoped dependency; FastAPI runs
  synchronous route handlers in its thread pool.
- Use a dark CSS design with responsive layouts and no external font or CSS CDN.
- Vendor HTMX and Chart.js locally with their license files.
- Protect state-changing requests with signed CSRF tokens stored in an HttpOnly,
  SameSite=Lax cookie. Validate the submitted token and Origin/Referer headers.
- Render product detail charts with clearly labeled demo data when no real price
  history exists. Do not insert fabricated history records.
- Store newly added products with `scrape_status='pending'`, no name, and no price.
- Render safe HTML error pages for 403, 404, and 500 responses. HTMX requests receive
  an error fragment instead of a full page.

## Consequences

- The application remains a single local process with no frontend build step.
- The UI is usable without JavaScript for basic form submissions, while HTMX improves
  list interactions.
- CSRF and Origin validation add protection for a localhost application that is still
  reachable from the user's browser.
- Demo chart data is visually distinct from real history and cannot be mistaken for
  scraped prices.
- Business logic remains testable without HTTP or template rendering.
