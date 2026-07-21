"""Alembic environment configured for the application's PostgreSQL schema."""

from logging.config import fileConfig
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Let `alembic -c alembic.ini ...` work consistently from the repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.core.database import Base
import app.models  # noqa: F401


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _sync_database_url(database_url: str) -> str:
    """Convert the application's async URL into Alembic's synchronous URL."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return database_url


config.set_main_option("sqlalchemy.url", _sync_database_url(settings.DATABASE_URL))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without opening a database connection when Alembic runs offline."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect with psycopg2 and apply the ordered migration revisions."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
