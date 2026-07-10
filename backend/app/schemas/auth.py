from pydantic import BaseModel
from pydantic import EmailStr


class RegisterSchema(BaseModel):

    username: str

    email: EmailStr

    password: str


class LoginSchema(BaseModel):

    email: EmailStr

    password: str


class UserResponse(BaseModel):

    id: int

    username: str

    email: str

    class Config:

        from_attributes = True