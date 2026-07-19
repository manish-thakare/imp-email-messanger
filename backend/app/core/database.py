from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


def get_database_url():
    if settings.DATABASE_URL.startswith("postgresql://"):
        return settings.DATABASE_URL.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1
        )
    return settings.DATABASE_URL


engine=create_async_engine(
    get_database_url(),
    echo=True
)

SessionLocal=sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with SessionLocal() as session:
        yield session
