import asyncio
from contextlib import suppress
from contextlib import asynccontextmanager

from fastapi import FastAPI
from app.api.email_accounts import router as email_accounts_router
from app.api.messages import router as messages_router
from app.api.routes import router as auth_router
from app.api.user import router as user_router
from app.api.whatsapp import router as whatsapp_router
from app.core.config import settings
from app.core.logger import logger
from app.workers.mail_sync_worker import run_mail_sync_worker

# Register every model before SQLAlchemy resolves relationship names at runtime.
import app.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the opt-in inbox worker and stop it cleanly during shutdown."""
    logger.info("Application started")
    stop_event = asyncio.Event()
    worker_task: asyncio.Task[None] | None = None
    if settings.MAIL_SYNC_ENABLED:
        worker_task = asyncio.create_task(run_mail_sync_worker(stop_event))
    try:
        yield
    finally:
        stop_event.set()
        if worker_task is not None:
            worker_task.cancel()
            with suppress(asyncio.CancelledError):
                await worker_task
        logger.info("Application stopped")


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan
)

app.include_router(
    auth_router,
    prefix="/api/v1/auth",
    tags=["Authentication"]
)

app.include_router(
    user_router,
    prefix="/api/v1/users",
    tags=["Users"],
)

app.include_router(
    email_accounts_router,
    prefix="/api/v1/email-accounts",
    tags=["Email accounts"],
)

app.include_router(
    messages_router,
    prefix="/api/v1/messages",
    tags=["Messages"],
)

app.include_router(
    whatsapp_router,
    prefix="/api/v1/whatsapp",
    tags=["WhatsApp"],
)

@app.get("/")
async def home():
    """Expose a lightweight service health response."""
    return {
        "status": "running"
    }
