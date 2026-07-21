"""Add a cache key for repeatable email priority assessments.

Revision ID: 20260720_03
Revises: 20260720_02
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_03"
down_revision = "20260720_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Allow existing messages to be classified once under the new cache policy."""
    op.add_column(
        "email_messages",
        sa.Column("classification_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_email_messages_classification_fingerprint",
        "email_messages",
        ["classification_fingerprint"],
    )


def downgrade() -> None:
    """Remove the repeat-classification cache key."""
    op.drop_index("ix_email_messages_classification_fingerprint", table_name="email_messages")
    op.drop_column("email_messages", "classification_fingerprint")
