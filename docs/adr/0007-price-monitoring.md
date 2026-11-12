# ADR 0007: Manual Price Checks and History Recording

- Status: Accepted
- Date: 2026-11-10

## Context

Stage 4 could perform an initial scrape but did not record price history. Stage 5 must
support manual checks, store successful observations, classify price changes, and show
real history without introducing the scheduler or notifications.

## Decision

- Add `PriceChecker`, which runs one scrape per product and prevents overlapping checks
  for the same product within the application process.
- Record every successful manual check in `price_history` with the scraped price,
  currency, UTC timestamp, and a change type.
- Classify changes as `initial`, `decrease`, `increase`, `unchanged`, or
  `currency_changed` using `Decimal` comparisons.
- Record an initial history row when a newly added product is scraped successfully.
- Backfill one initial history row for legacy products that have a current price and a
  last successful check but no history, using those stored values.
- On failure, update only `scrape_status`, `last_error`, and `last_attempt_at`; never
  overwrite valid product fields or add a history row.
- Build the product page summary from history: latest price, previous price, change
  type, and decimal-safe change amount.
- Keep Chart.js vendored locally. Use real history when available and clearly labeled
  demo data only when history is empty.
- Do not add scheduler jobs or notifications in this stage.

## Consequences

- Manual checks produce an auditable price timeline.
- Charts become real as soon as the initial scrape or a manual check succeeds.
- Legacy products gain a history point from their stored initial observation on the
  first successful manual check.
- Overlapping manual checks are rejected with a busy result.
- Automatic monitoring remains a later-stage concern.
