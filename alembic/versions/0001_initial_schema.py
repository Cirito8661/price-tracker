"""Initial database schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("store", sa.String(length=64), nullable=False),
        sa.Column("current_price", sa.String(length=32), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("target_price", sa.String(length=32), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column(
            "scrape_status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "(current_price IS NULL AND currency IS NULL) OR "
            "(current_price IS NOT NULL AND currency IS NOT NULL)",
            name="price_currency_pair",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="currency_len",
        ),
        sa.CheckConstraint(
            "length(store) > 0",
            name="store_len",
        ),
        sa.CheckConstraint(
            "scrape_status IN ('pending', 'ok', 'error')",
            name="scrape_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_products"),
        sa.UniqueConstraint("url", name="uq_products_url"),
    )
    op.create_index(
        "ix_products_is_active",
        "products",
        ["is_active"],
        unique=False,
    )
    op.create_index("ix_products_store", "products", ["store"], unique=False)
    op.create_index(
        "ix_products_scrape_status",
        "products",
        ["scrape_status"],
        unique=False,
    )

    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("price", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("change_type", sa.String(length=16), nullable=False),
        sa.Column("checked_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "length(currency) = 3",
            name="currency_len",
        ),
        sa.CheckConstraint(
            "length(price) > 0",
            name="price_nonempty",
        ),
        sa.CheckConstraint(
            "change_type IN ('initial', 'decrease', 'increase', 'unchanged', 'currency_changed')",
            name="change_type",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_price_history_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_price_history"),
    )
    op.create_index(
        "ix_price_history_product_checked",
        "price_history",
        ["product_id", "checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_price_history_checked_at",
        "price_history",
        ["checked_at"],
        unique=False,
    )
    op.create_index(
        "ix_price_history_change_type",
        "price_history",
        ["change_type"],
        unique=False,
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column("old_price", sa.String(length=32), nullable=False),
        sa.Column("new_price", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "length(currency) = 3",
            name="currency_len",
        ),
        sa.CheckConstraint(
            "length(old_price) > 0 AND length(new_price) > 0",
            name="prices_nonempty",
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name="attempts_nonnegative",
        ),
        sa.CheckConstraint(
            "notification_type IN ('price_drop', 'target_reached')",
            name="notification_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'skipped')",
            name="status",
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name="fk_notifications_product_id_products",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notifications"),
    )
    op.create_index(
        "ix_notifications_product_type_created",
        "notifications",
        ["product_id", "notification_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_notifications_status",
        "notifications",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_table("price_history")
    op.drop_table("products")
