from pydantic import BaseModel
from pydantic import EmailStr


class RegisterSchema(BaseModel):

    username: str

    primary_email: EmailStr

    password: str


class LoginSchema(BaseModel):

    username: str

    password: str


class UserResponse(BaseModel):

    id: int

    username: str

    primary_email: str

    class Config:

        from_attributes = True
