"""Compose the gateway using the services available on the sprint baseline."""

import os
from contextlib import asynccontextmanager
from pathlib import Path
from secrets import token_urlsafe

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from api.exception_handlers import register_exception_handlers
from api.routes import auth, documents, exams, health
from api.storage import PrototypeStore
from core.config import Settings, get_settings
from services.ai import OfflineMockAIAdapter, QuestionGenerationService
from services.ai.live_adapter import build_default_ai_adapter

DEFAULT_DEV_SECRET = "examify-development-secret-key-change-in-production"
CLIENT_PATH = Path(__file__).resolve().parent.parent / "client"


def init_db(store: PrototypeStore, *, initialize_domain: bool) -> None:
    if initialize_domain:
        try:
            from domain.persistence.database import init_db as init_domain_db
        except ModuleNotFoundError as exc:
            if exc.name not in {"domain.persistence", "domain.persistence.database"}:
                raise
        else:
            init_domain_db()
    store.init_db()


def create_app(
    settings: Settings | None = None,
    *,
    database_path: Path | None = None,
) -> FastAPI:
    initialize_domain = settings is None and database_path is None
    settings = settings or get_settings()
    if database_path is None:
        sqlite_path = settings.database_url.removeprefix("sqlite:///")
        database_path = Path(
            sqlite_path if sqlite_path != settings.database_url else "./examify.db"
        )
    store = PrototypeStore(database_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await run_in_threadpool(init_db, store, initialize_domain=initialize_domain)
        yield

    app = FastAPI(title="Examify", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.jwt_secret = (
        token_urlsafe(48)
        if settings.jwt_secret in {"", DEFAULT_DEV_SECRET}
        else settings.jwt_secret
    )
    mock = OfflineMockAIAdapter()
    app.state.offline_generation = QuestionGenerationService(mock)
    app.state.live_generation = QuestionGenerationService(
        mock if settings.offline_mode else build_default_ai_adapter(settings=settings)
    )
    register_exception_handlers(app)
    origins = os.environ.get("EXAMIFY_CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in origins.split(",")
            if origin.strip() and origin.strip() != "*"
        ],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    for router in (health.router, auth.router, documents.router, exams.router):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(CLIENT_PATH / "index.html")

    app.mount("/static", StaticFiles(directory=CLIENT_PATH), name="static")
    return app
