# ADR 0008: Scheduler, Notifications, and Runtime Settings

- Status: Accepted
- Date: 2026-11-10

## Context

Stage 6 needs automatic periodic checks and notifications without changing the approved
database schema. The application also needs editable scheduler and SMTP settings.

## Decision

- Use one APScheduler `AsyncIOScheduler` job with a deterministic id, a global interval,
  `max_instances=1`, `coalesce=True`, and a bounded misfire grace time.
- Run active products sequentially in one sweep and keep the existing per-product check
  guard. Stop the scheduler before closing the browser and database engine.
- Persist editable scheduler and SMTP settings in `data/runtime_settings.json` rather
  than adding a database table. Validate them with Pydantic and write them atomically
  with owner-only permissions on POSIX systems.
- Reuse `PriceChecker` for both manual and automatic checks so history, change
  classification, and notifications are consistent.
- Add `NotificationService` with console and SMTP channels. Evaluate price drops and
  target-price crossings after successful checks, persist notification events, apply a
  cooldown-based deduplication rule, and retry failed notifications up to the configured
  attempt limit.
- Treat notification delivery as one event across channels. A partial channel failure is
  recorded in `error_message`; the event is marked sent if any channel succeeded.
- Automatically disable email when required SMTP values are missing and expose scheduler
  and email status on the Settings page.

## Consequences

- No database migration is required for Stage 6.
- Runtime settings survive restarts without modifying `.env`.
- Scheduler jobs cannot overlap within the single supported process.
- Email delivery is optional and never blocks price-check persistence or monitoring.
- Per-channel delivery status is a documented limitation because the notification model
  has one status per event.
