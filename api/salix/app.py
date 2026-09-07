"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .middleware import (
    ApiKeyMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from .providers import build_providers, get_providers
from .providers.base import ProviderError
from .routers import calls, deals, dojo, meta, plays, reports, reps
from .store import db, repo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)-24s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("salix.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await db.init_db()
    providers = build_providers(settings)
    app.state.providers = providers

    # Nothing is running yet, so anything the database still believes is
    # mid-analysis was orphaned by the last shutdown. Left alone it spins on
    # the call page forever.
    async with db.session_scope() as session:
        interrupted = await repo.fail_interrupted_calls(session)
    if interrupted:
        log.warning(
            "closed %d call(s) left mid-analysis by the last shutdown: %s",
            len(interrupted),
            ", ".join(interrupted[:5]) + ("..." if len(interrupted) > 5 else ""),
        )

    log.info(
        "Salix API ready | providers=%s | db=%s | auth=%s | rate-limit=%s",
        providers.mode.upper(),
        settings.database_url.split("://")[0],
        "key required" if settings.api_key else "OPEN",
        "on" if settings.rate_limit_enabled else "off",
    )
    if not settings.api_key:
        # Said once, at the top, where somebody about to expose a port will
        # see it. Silence here is how a demo ends up public.
        log.warning(
            "No SALIX_API_KEY set: every call in this database is readable by "
            "anyone who can reach this port. Fine on a laptop; set a key "
            "before binding to anything else."
        )
    if settings.database_url.startswith("sqlite"):
        log.info(
            "SQLite is the store. Good for one process; set SALIX_DATABASE_URL "
            "to Postgres before more than one writer."
        )

    yield
    await db.dispose()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Salix API",
        description=(
            "Sales conversation intelligence. Transcribes and diarizes calls, "
            "measures them deterministically, reads their anatomy, mines the "
            "narrative plays that win, and coaches from them."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )

    # Order matters: Starlette runs these outermost-last, so the request id is
    # attached first and is therefore available to everything that follows,
    # and CORS is outermost so even a rejected request answers a preflight.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, enabled=settings.rate_limit_enabled)
    app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "X-API-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Retry-After"],
    )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request, exc: ProviderError):
        """An upstream failure is a 502, never an opaque 500.

        The frontend uses `retryable` to decide between offering a retry and
        degrading the panel, so it is part of the contract rather than a log
        line.
        """
        log.warning("provider error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=502,
            content={
                "error": "provider_unavailable",
                "provider": exc.provider,
                "detail": exc.detail,
                "retryable": exc.retryable,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request, exc: Exception):
        """Never hand a stack trace to a browser.

        The traceback is already in the log with this request's id, so support
        can find it from the id alone without the client having been shown the
        inside of the process.
        """
        request_id = getattr(request.state, "request_id", "unknown")
        log.exception("unhandled on %s [%s]", request.url.path, request_id)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "Something failed on our side. Quote this id if you report it.",
                "request_id": request_id,
            },
        )

    for router in (meta, calls, reps, plays, deals, reports, dojo):
        app.include_router(router.router, prefix="/api")

    # Audio is served straight from disk so the call page can scrub a
    # waveform without a signed-URL round trip in local development.
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/audio", StaticFiles(directory=str(settings.audio_dir)), name="audio"
    )

    return app


app = create_app()
