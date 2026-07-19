from pydantic_settings import BaseSettings
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):

    APP_NAME:str

    DATABASE_URL:str

    REDIS_URL:str

    JWT_SECRET:str

    JWT_ALGORITHM:str

    ACCESS_TOKEN_EXPIRE_MINUTES:int

    class Config:

        env_file=BASE_DIR / ".env"


settings=Settings()
