"""add failure and cooldown fields

Revision ID: 0002_failure_fields
Revises: 0001_initial
Create Date: 2026-03-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_failure_fields"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trade_attempts", sa.Column("failure_category", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("trade_attempts", sa.Column("is_fatal_failure", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("trade_attempts", sa.Column("cooldown_triggered", sa.Boolean(), nullable=False, server_default=sa.false()))

    op.add_column("executions", sa.Column("failure_category", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("executions", sa.Column("is_fatal_failure", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("executions", sa.Column("cooldown_triggered", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("executions", "cooldown_triggered")
    op.drop_column("executions", "is_fatal_failure")
    op.drop_column("executions", "failure_category")

    op.drop_column("trade_attempts", "cooldown_triggered")
    op.drop_column("trade_attempts", "is_fatal_failure")
    op.drop_column("trade_attempts", "failure_category")
