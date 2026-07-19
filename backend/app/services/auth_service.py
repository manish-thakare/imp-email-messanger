from app.models.user import User

from app.repositories.user_repository import UserRepository

from app.core.security import hash_password

from app.core.security import verify_password

from app.core.security import create_access_token

class AuthService:
    """Own registration and sign-in decisions for application users."""

    def __init__(

        self,

        repo: UserRepository

    ):

        self.repo = repo


    async def register(self, username: str, primary_email: str, password: str) -> User:
        """Register a user after ensuring username and primary email are unused."""

        existing_username = await self.repo.get_by_username(

            username

        )

        if existing_username:

            raise ValueError(

                "Username already exists"

            )

        existing_email = await self.repo.get_by_email(

            primary_email

        )

        if existing_email:

            raise ValueError(

                "Primary email already exists"

            )

        user = User(

            username=username,

            primary_email=primary_email,

            password=hash_password(password)

        )

        return await self.repo.create(user)


    async def login(self, username: str, password: str) -> str | None:
        """Validate credentials and issue a bearer token when they are correct."""

        user = await self.repo.get_by_username(

            username

        )

        if not user:

            return None

        if not verify_password(

            password,

            user.password

        ):

            return None

        token = create_access_token(

            {

                "sub": user.username

            }

        )

        return token
