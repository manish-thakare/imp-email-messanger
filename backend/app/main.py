from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.core.config import settings
from app.core.logger import logger
from app.api.v1.auth.routes import router as auth_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application started")
    yield


app=FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

@app.get("/")
async def home():
    return {
        "status":"running"
    }

