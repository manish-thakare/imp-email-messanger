from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    APP_NAME:str

    DATABASE_URL:str

    REDIS_URL:str

    JWT_SECRET:str

    JWT_ALGORITHM:str

    ACCESS_TOKEN_EXPIRE_MINUTES:int

    class Config:

        env_file=".env"


settings=Settings()