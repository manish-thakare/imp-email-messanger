from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

class UserRepository:
    """Read and write application users through the async database session."""

    def __init__(

        self,
        db: AsyncSession
    ):
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        """Find a user by their unique primary email address."""
        result = await self.db.execute(
            select(User).where(
                User.primary_email == email
            )
        )

        return result.scalar_one_or_none()


    async def get_by_username(self, username: str) -> User | None:
        """Find a user by the unique username used during sign-in."""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()


    async def get_by_id(self, user_id: int) -> User | None:
        """Find a user by the internal identifier stored in OAuth state."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """Persist a registered user and return it with its generated identifier."""
        self.db.add(user)

        await self.db.commit()

        await self.db.refresh(user)

        return user
