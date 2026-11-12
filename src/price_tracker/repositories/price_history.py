"""Price history repository."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.enums import PriceChangeType
from ..models.price_history import PriceHistory
from ..models.product import Product


class PriceHistoryRepository:
    """Persistence and reporting queries for price history."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entry: PriceHistory) -> PriceHistory:
        self.session.add(entry)
        self.session.flush()
        return entry

    def list_for_product(
        self,
        product_id: int,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[PriceHistory]:
        statement = (
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.checked_at.asc(), PriceHistory.id.asc())
        )
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def latest_for_product(self, product_id: int) -> PriceHistory | None:
        statement = (
            select(PriceHistory)
            .where(PriceHistory.product_id == product_id)
            .order_by(PriceHistory.checked_at.desc(), PriceHistory.id.desc())
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def recent_changes(self, *, limit: int = 10) -> list[tuple[PriceHistory, Product]]:
        statement = (
            select(PriceHistory, Product)
            .join(Product, PriceHistory.product_id == Product.id)
            .order_by(PriceHistory.checked_at.desc(), PriceHistory.id.desc())
            .limit(limit)
        )
        return [(row[0], row[1]) for row in self.session.execute(statement)]

    def recent_decreases(
        self,
        since: datetime,
        *,
        limit: int = 10,
    ) -> list[PriceHistory]:
        statement = (
            select(PriceHistory)
            .where(
                PriceHistory.change_type == PriceChangeType.DECREASE,
                PriceHistory.checked_at >= since,
            )
            .order_by(PriceHistory.checked_at.desc(), PriceHistory.id.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def count_recent_decreases(self, since: datetime) -> int:
        statement = (
            select(func.count())
            .select_from(PriceHistory)
            .where(
                PriceHistory.change_type == PriceChangeType.DECREASE,
                PriceHistory.checked_at >= since,
            )
        )
        return int(self.session.scalar(statement) or 0)

    def count_for_product(self, product_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(PriceHistory)
            .where(PriceHistory.product_id == product_id)
        )
        return int(self.session.scalar(statement) or 0)
