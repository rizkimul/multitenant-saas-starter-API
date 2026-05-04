from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import engine
from app.core.exceptions import AppError
from app.core.logging import get_logger, setup_logging
from app.routers import auth

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    setup_logging(debug=settings.debug)
    logger.info("Application starting up")
    yield
    await engine.dispose()
    logger.info("Application shutting down")


app = FastAPI(
    title="SaaS Starter API",
    version="0.1.0",
    description="Multi-tenant SaaS backend boilerplate",
    lifespan=lifespan,
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Convert any AppError subclass into a consistent JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


app.include_router(auth.router)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Return service liveness status."""
    return {"status": "ok"}
