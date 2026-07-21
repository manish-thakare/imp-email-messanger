"""Persist bounded notification content at queue time.

Revision ID: 20260721_04
Revises: 20260720_03
Create Date: 2026-07-21
"""

from alembic import op
import sqlalchemy as sa


revision = "20260721_04"
down_revision = "20260720_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Make queued notifications durable even if the source message is later edited."""
    op.add_column(
        "whatsapp_notifications",
        sa.Column("payload_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Remove the persisted notification snapshot."""
    op.drop_column("whatsapp_notifications", "payload_json")
