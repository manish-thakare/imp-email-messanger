"""Create the core user, monitored inbox, and fetched email tables.

Revision ID: 20260720_01
Revises:
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the initial schema for a fresh AI Email Guardian database."""
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("primary_email", sa.String(length=255), nullable=False),
        sa.Column("password", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("primary_email", name="uq_users_primary_email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_primary_email", "users", ["primary_email"])

    op.create_table(
        "monitored_email_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("email_address", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "email_address", name="uq_provider_email_address"),
    )
    op.create_index("ix_monitored_email_accounts_user_id", "monitored_email_accounts", ["user_id"])
    op.create_index("ix_monitored_email_accounts_provider", "monitored_email_accounts", ["provider"])
    op.create_index("ix_monitored_email_accounts_email_address", "monitored_email_accounts", ["email_address"])

    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=512), nullable=False),
        sa.Column("provider_thread_id", sa.String(length=512), nullable=True),
        sa.Column("subject", sa.String(length=1024), nullable=False),
        sa.Column("sender", sa.String(length=512), nullable=True),
        sa.Column("recipients", sa.Text(), nullable=True),
        sa.Column("body_preview", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("priority_score", sa.Integer(), nullable=False),
        sa.Column("priority_label", sa.String(length=20), nullable=False),
        sa.Column("is_priority", sa.Boolean(), nullable=False),
        sa.Column("priority_reason", sa.Text(), nullable=True),
        sa.Column("classification_source", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["monitored_email_accounts.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("account_id", "provider_message_id", name="uq_account_provider_message"),
    )
    op.create_index("ix_email_messages_account_id", "email_messages", ["account_id"])
    op.create_index("ix_email_messages_received_at", "email_messages", ["received_at"])
    op.create_index("ix_email_messages_priority_score", "email_messages", ["priority_score"])
    op.create_index("ix_email_messages_priority_label", "email_messages", ["priority_label"])
    op.create_index("ix_email_messages_is_priority", "email_messages", ["is_priority"])


def downgrade() -> None:
    """Remove the core schema created by this fresh-database revision."""
    op.drop_table("email_messages")
    op.drop_table("monitored_email_accounts")
    op.drop_table("users")
