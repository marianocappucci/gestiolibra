"""ASGI entrypoint for production/dev containers: `create_app()` takes a
required `database_url` argument, so it can't be used directly as
uvicorn's factory target -- this module reads it from the environment
once at import time and exposes the built `app` instance uvicorn expects
(`uvicorn app.asgi:app`).

Bridges two env var conventions: the `docker-compose.yml` of this repo
(DATABASE_URL/GESTIOLIBRA_*, set explicitly) for local dev, and the
generic contract `libracore.provisioning` writes for real clients
(DATA_DIR/ADMIN_USER/ADMIN_PASSWORD/ADMIN_NOMBRE -- same names Contalibra/
Restolibra already read directly, see wiki/entities/libracore.md). When
DATA_DIR is present it takes precedence for anything not already set
explicitly, so a provisioned client container needs no Gestiolibra-
specific env vars at all.

Also serves the built frontend SPA (`frontend/dist`, produced by the
Dockerfile's node build stage) if present -- API routes are already
registered by `create_app()` and take priority; anything else falls
through to `index.html` for client-side routing (see ADR-019). Running
`uvicorn app.asgi:app` locally without ever building the frontend still
works as a pure API -- the mount is skipped silently."""
import os
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR")
if DATA_DIR:
    os.makedirs(DATA_DIR, exist_ok=True)
    database_url = os.environ.get("DATABASE_URL", f"sqlite:///{DATA_DIR}/gestiolibra.db")
    os.environ.setdefault(
        "GESTIOLIBRA_LIBRACORE_DB_PATH", f"{DATA_DIR}/gestiolibra_libracore.db"
    )
    if os.environ.get("ADMIN_USER"):
        os.environ.setdefault("GESTIOLIBRA_ADMIN_USERNAME", os.environ["ADMIN_USER"])
    if os.environ.get("ADMIN_PASSWORD"):
        os.environ.setdefault("GESTIOLIBRA_ADMIN_PASSWORD", os.environ["ADMIN_PASSWORD"])
else:
    database_url = os.environ["DATABASE_URL"]

app = create_app(database_url)

FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets"
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        del full_path  # unused: catch-all for client-side routing
        return FileResponse(FRONTEND_DIST / "index.html")
