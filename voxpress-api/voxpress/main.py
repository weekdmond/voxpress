from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from voxpress import __version__
from voxpress.config import settings
from voxpress.errors import ApiError, api_error_handler
from voxpress.routers import (
    articles,
    creators,
    health,
    media,
    resolve,
    settings as settings_router,
    system_jobs,
    tasks,
    videos,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="VoxPress API", version=__version__, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(health.router)
    app.include_router(creators.router)
    app.include_router(videos.router)
    app.include_router(articles.router)
    app.include_router(tasks.router)
    app.include_router(system_jobs.router)
    app.include_router(media.router)
    app.include_router(resolve.router)
    app.include_router(settings_router.router)
    return app


app = create_app()
