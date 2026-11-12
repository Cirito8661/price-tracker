"""Product repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models.product import Product


class ProductRepository:
    """Persistence operations for products."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, product: Product) -> Product:
        self.session.add(product)
        self.session.flush()
        return product

    def get(self, product_id: int) -> Product | None:
        return self.session.get(Product, product_id)

    def get_by_url(self, url: str) -> Product | None:
        statement = select(Product).where(Product.url == url)
        return self.session.scalars(statement).first()

    def list(
        self,
        *,
        active_only: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Product]:
        statement = select(Product).order_by(
            Product.created_at.desc(),
            Product.id.desc(),
        )
        if active_only:
            statement = statement.where(Product.is_active.is_(True))
        if offset:
            statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_active_ids(self) -> list[int]:
        statement = select(Product.id).where(Product.is_active.is_(True)).order_by(Product.id)
        return list(self.session.scalars(statement))

    def count(self, *, active_only: bool = False) -> int:
        statement = select(func.count()).select_from(Product)
        if active_only:
            statement = statement.where(Product.is_active.is_(True))
        return int(self.session.scalar(statement) or 0)

    def count_awaiting_first_check(self) -> int:
        statement = select(func.count()).select_from(Product).where(Product.current_price.is_(None))
        return int(self.session.scalar(statement) or 0)

    def delete(self, product: Product) -> None:
        self.session.delete(product)
        self.session.flush()
