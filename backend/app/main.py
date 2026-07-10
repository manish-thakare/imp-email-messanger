from fastapi import FastAPI
from app.core.config import settings
from app.core.logger import logger
from app.api.v1.auth.routes import router as auth_router

app=FastAPI(
    title=settings.APP_NAME
)

app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

@app.lifespan("startup")
async def startup():
    logger.info("Application Started")

@app.get("/")
async def home():
    return {
        "status":"running"
    }

