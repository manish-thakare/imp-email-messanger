from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterSchema(BaseModel):
    """Information required to create an application account."""
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    primary_email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginSchema(BaseModel):
    """Credentials used to sign in to the application."""
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    """Safe user details returned to the client."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    primary_email: EmailStr


class AccessTokenResponse(BaseModel):
    """Bearer token returned after a successful sign-in."""
    access_token: str
    token_type: str = "bearer"
