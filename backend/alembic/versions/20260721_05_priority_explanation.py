"""Persist structured rule evidence for audit and client explainability.

Revision ID: 20260721_05
Revises: 20260721_04
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_05"
down_revision = "20260721_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Store the matched weighted rules or model signals as bounded JSON text."""
    op.add_column(
        "email_messages",
        sa.Column("priority_explanation", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove persisted structured priority evidence."""
    op.drop_column("email_messages", "priority_explanation")
