from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

class UserRepository:

    def __init__(

        self,
        db: AsyncSession
    ):
        self.db = db

    async def get_by_email(self,email: str):
        result = await self.db.execute(
            select(User).where(
                User.email == email
            )
        )

        return result.scalar_one_or_none()


    async def create(

        self,

        user: User

    ):

        self.db.add(user)

        await self.db.commit()

        await self.db.refresh(user)

        return user