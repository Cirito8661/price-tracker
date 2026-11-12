# ADR 0002: Decimal and UTC Storage Types

- Status: Accepted
- Date: 2026-11-10

## Context

SQLite has no native decimal type. SQLAlchemy's `Numeric` can round-trip values through
SQLite numeric affinity, which risks binary floating-point behavior. SQLite also drops
timezone information from `DATETIME` values.

Financial calculations and timestamp comparisons must be exact and consistent across
Linux and Windows.

## Decision

- Store prices as canonical decimal strings using a custom SQLAlchemy `TypeDecorator`
  backed by `TEXT`.
- Reject `float` inputs at the type boundary and use `Decimal` for all price logic.
- Store timestamps as naive UTC in SQLite through a custom `UtcDateTime` type and return
  timezone-aware UTC values.
- Use a single `utcnow()` clock helper for testability.

## Consequences

- Price comparisons are exact and independent of platform floating-point behavior.
- Timestamps remain comparable and unambiguous across time zones and DST changes.
- Queries that need change direction use an explicit `change_type` column rather than
  casting price text to a numeric type.
