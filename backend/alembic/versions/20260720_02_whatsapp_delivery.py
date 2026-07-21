"""Create opted-in WhatsApp contacts and priority-alert notification outbox.

Revision ID: 20260720_02
Revises: 20260720_01
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_02"
down_revision = "20260720_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the user opt-in and durable delivery records for WhatsApp alerts."""
    op.create_table(
        "whatsapp_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("is_opted_in", sa.Boolean(), nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", name="uq_whatsapp_contacts_user_id"),
        sa.UniqueConstraint("phone_number", name="uq_whatsapp_contacts_phone_number"),
    )
    op.create_index("ix_whatsapp_contacts_user_id", "whatsapp_contacts", ["user_id"])
    op.create_index("ix_whatsapp_contacts_phone_number", "whatsapp_contacts", ["phone_number"])

    op.create_table(
        "whatsapp_notifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("email_message_id", sa.Integer(), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["email_message_id"], ["email_messages.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("email_message_id", name="uq_whatsapp_notifications_email_message_id"),
    )
    op.create_index("ix_whatsapp_notifications_user_id", "whatsapp_notifications", ["user_id"])
    op.create_index("ix_whatsapp_notifications_email_message_id", "whatsapp_notifications", ["email_message_id"])
    op.create_index("ix_whatsapp_notifications_status", "whatsapp_notifications", ["status"])
    op.create_index("ix_whatsapp_notifications_provider_message_id", "whatsapp_notifications", ["provider_message_id"])


def downgrade() -> None:
    """Remove the WhatsApp contact and notification tables."""
    op.drop_table("whatsapp_notifications")
    op.drop_table("whatsapp_contacts")
