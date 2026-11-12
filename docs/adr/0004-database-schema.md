# ADR 0004: Database Schema and Constraints

- Status: Accepted
- Date: 2026-11-10

## Context

The application needs a durable local store for products, successful price checks, and
notification history. The schema must preserve exact decimal prices, unambiguous UTC
timestamps, referential integrity, and safe deletion behavior on SQLite.

## Decision

Use three tables with SQLAlchemy 2.0 typed models and an initial Alembic migration:

- `products` stores the normalized URL, optional name and current price, store
  identifier, target price, monitoring state, scrape status, and timestamps.
- `price_history` stores one row per successful check, including a `change_type`
  (`initial`, `decrease`, `increase`, `unchanged`, `currency_changed`).
- `notifications` stores price-drop and target-price events, delivery status, currency,
  attempts, and error details.

Constraints:

- A unique constraint on normalized product URLs.
- A CHECK constraint requiring `current_price` and `currency` to be either both present
  or both absent.
- Three-letter currency checks on every currency column.
- Enum values are stored as `VARCHAR` with CHECK constraints.
- Price history and notifications reference products with `ON DELETE CASCADE`.
- Non-negative notification attempts and non-empty price text.
- Indexes on active products, stores, scrape status, product history, recent checks,
  change types, notification deduplication, and notification status.

SQLite is configured with WAL, foreign keys, a busy timeout, and `synchronous=NORMAL`.
Repositories flush but do not commit; services own transaction boundaries through
`session_scope`.

## Consequences

- Product deletion removes dependent history and notifications.
- Failed scrapes can be represented without inventing prices.
- Dashboard queries for recent decreases use `change_type` rather than casting text to
  a floating-point value.
- Schema changes must be delivered through explicit Alembic migrations.
