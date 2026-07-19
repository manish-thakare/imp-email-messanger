from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def get_database_url() -> str:
    """Return a URL that SQLAlchemy's async PostgreSQL driver can use."""
    if settings.DATABASE_URL.startswith("postgresql://"):
        return settings.DATABASE_URL.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1
        )
    return settings.DATABASE_URL


engine=create_async_engine(
    get_database_url(),
    echo=settings.SQL_ECHO
)

SessionLocal=sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    """Base class shared by every persisted application model."""
    pass

async def get_db():
    """Provide one database session for the lifetime of an API request."""
    async with SessionLocal() as session:
        yield session
