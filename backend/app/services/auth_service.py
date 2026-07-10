from app.models.user import User

from app.repositories.user_repository import UserRepository

from app.core.security import hash_password

from app.core.security import verify_password

from app.core.security import create_access_token

class AuthService:

    def __init__(

        self,

        repo: UserRepository

    ):

        self.repo = repo


    async def register(

        self,

        username,

        email,

        password

    ):

        exists = await self.repo.get_by_email(

            email

        )

        if exists:

            raise Exception(

                "Email already exists"

            )

        user = User(

            username=username,

            email=email,

            password=hash_password(password)

        )

        return await self.repo.create(user)


    async def login(

        self,

        email,

        password

    ):

        user = await self.repo.get_by_email(

            email

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

                "sub": user.email

            }

        )

        return token