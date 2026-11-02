"""OpsPilot 365 local case service and Microsoft Graph gateway."""

from __future__ import annotations

import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from app.api.deps import SESSION_COOKIE
from app.api.routes import router
from app.auth.entra import EntraAuth
from app.auth.graph_client import GraphClient
from app.clock import Clock
from app.config import Settings
from app.errors import OpsError, public_error
from app.logging_config import configure_logging
from app.services.engine import Engine
from app.services.seed import run_seed
from app.store.db import Store


def create_app(settings: Settings | None = None, clock: Clock | None = None, transport=None) -> FastAPI:
    settings = settings or Settings()
    clock = clock or Clock()
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store = Store(settings.db_path)
        store.init()
        graph = GraphClient(settings, transport=transport)
        engine = Engine(store, settings, clock, graph)
        if settings.seed and store.count_requests() == 0:
            run_seed(engine)
        app.state.store = store
        app.state.engine = engine
        app.state.settings = settings
        app.state.clock = clock
        app.state.graph = graph
        app.state.entra = EntraAuth(settings)
        yield
        store.close()

    app = FastAPI(
        title="OpsPilot 365",
        version="0.1.0",
        summary="Local case service and delegated Microsoft Graph gateway.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.public_app_url, "http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    @app.exception_handler(OpsError)
    async def ops_error(_request: Request, exc: OpsError):
        return JSONResponse(status_code=exc.status, content=public_error(exc))

    app.include_router(router)
    _register_auth(app)
    return app


def _register_auth(app: FastAPI) -> None:
    @app.get("/auth/login")
    def login(request: Request):
        settings: Settings = request.app.state.settings
        if not settings.entra_configured:
            raise OpsError(
                "entra_not_configured",
                "Set OPSPILOT_AZURE_TENANT_ID and OPSPILOT_AZURE_CLIENT_ID before signing in.",
                503,
            )
        url = request.app.state.entra.authorization_url()
        return RedirectResponse(url)

    @app.get("/auth/callback")
    def callback(request: Request):
        try:
            session = request.app.state.entra.complete(dict(request.query_params))
        except RuntimeError as exc:
            raise OpsError("signin_failed", "Microsoft sign-in did not return a token.", 400) from exc
        response = RedirectResponse(request.app.state.settings.public_app_url + "/connections")
        response.set_cookie(
            SESSION_COOKIE,
            session.id,
            httponly=True,
            samesite="lax",
            max_age=3600,
            path="/",
        )
        return response


if "pytest" not in sys.modules:
    app = create_app()
