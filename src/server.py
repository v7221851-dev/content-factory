from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from src.api import router
from src.core.db import async_session
from src.core.migrations import ensure_schema
from src.core.settings import settings
from src.core.scheduler import start_scheduler, stop_scheduler
from src.services.ingest.rss import ensure_default_sources


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()

    async with async_session() as session:
        await ensure_default_sources(session)

    configured = settings.VK_GROUP_ID or settings.TELEGRAM_BOT_TOKEN
    if not configured:
        logger.warning(
            "Нет настроенных платформ. Заполните VK_* или TELEGRAM_* в content-factory/.env"
        )

    start_scheduler()

    yield

    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(
        title="MDSA Content Factory",
        description="Сбор health-новостей и публикация в соцсети",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
