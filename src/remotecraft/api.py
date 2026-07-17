"""FastAPI application factory."""

from __future__ import annotations

import hmac
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from remotecraft import __version__
from remotecraft.config import Settings
from remotecraft.errors import RemoteCraftError
from remotecraft.models import ServerView
from remotecraft.service import MinecraftService
from remotecraft.store import ServerStore
from remotecraft.versions import VersionCatalog

bearer = HTTPBearer(auto_error=False)


class CreateServerRequest(BaseModel):
    name: str = Field(min_length=2, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]+$")
    version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z][0-9A-Za-z._-]*$")
    ram_gb: int = Field(ge=1, le=64)
    accept_eula: Literal[True]


class CommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=512)


def build_service(settings: Settings) -> MinecraftService:
    store = ServerStore(settings.data_dir)
    catalog = VersionCatalog(settings.data_dir / "versions.json")
    return MinecraftService(settings, store, catalog)


def create_app(
    settings: Settings | None = None, service: MinecraftService | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    service = service or build_service(settings)
    app = FastAPI(
        title="RemoteCraft API",
        summary="Manage Vanilla Minecraft servers on a trusted Linux host over SSH.",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.service = service

    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; connect-src 'self'; "
            "form-action 'self'; frame-ancestors 'none'; img-src 'self' data:; "
            "script-src 'self'; style-src 'self'"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(RemoteCraftError)
    async def handle_domain_error(_request: Request, exc: RemoteCraftError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.code, "detail": str(exc)},
        )

    def require_token(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> None:
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not hmac.compare_digest(credentials.credentials, settings.api_token)
        ):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    auth = [Depends(require_token)]

    @app.get("/api/health", include_in_schema=False)
    def health() -> dict[str, object]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/host", dependencies=auth)
    def host_status() -> dict[str, object]:
        return service.check_host()

    @app.get("/api/versions", dependencies=auth)
    def versions(limit: Annotated[int, Query(ge=1, le=100)] = 30) -> dict[str, list[str]]:
        return {"versions": service.catalog.list_releases(limit)}

    @app.get("/api/servers", dependencies=auth, response_model=list[ServerView])
    def list_servers() -> list[ServerView]:
        return service.list_servers()

    @app.post(
        "/api/servers",
        dependencies=auth,
        response_model=ServerView,
        status_code=status.HTTP_201_CREATED,
    )
    def create_server(payload: CreateServerRequest) -> ServerView:
        return service.create_server(**payload.model_dump())

    @app.post("/api/servers/{server_id}/start", dependencies=auth, response_model=ServerView)
    def start_server(server_id: str) -> ServerView:
        return service.start_server(server_id)

    @app.post("/api/servers/{server_id}/stop", dependencies=auth, response_model=ServerView)
    def stop_server(server_id: str) -> ServerView:
        return service.stop_server(server_id)

    @app.post("/api/servers/{server_id}/restart", dependencies=auth, response_model=ServerView)
    def restart_server(server_id: str) -> ServerView:
        return service.restart_server(server_id)

    @app.post("/api/servers/{server_id}/kill", dependencies=auth, response_model=ServerView)
    def kill_server(server_id: str) -> ServerView:
        return service.kill_server(server_id)

    @app.delete("/api/servers/{server_id}", dependencies=auth, response_model=ServerView)
    def delete_server(
        server_id: str, confirm: str = Query(min_length=2, max_length=32)
    ) -> ServerView:
        return service.delete_server(server_id, confirm=confirm)

    @app.post("/api/servers/{server_id}/command", dependencies=auth)
    def send_command(server_id: str, payload: CommandRequest) -> dict[str, str]:
        return service.send_command(server_id, payload.command)

    @app.get("/api/servers/{server_id}/logs", dependencies=auth)
    def logs(server_id: str, lines: Annotated[int, Query(ge=1, le=500)] = 100) -> dict[str, object]:
        return service.get_logs(server_id, lines)

    app.mount("/assets", StaticFiles(directory=settings.frontend_dir), name="assets")

    @app.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse(settings.frontend_dir / "index.html")

    return app
