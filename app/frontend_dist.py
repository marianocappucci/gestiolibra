"""Donde esta el build del frontend.

Lo usan `asgi.py` (para servirlo) y `main.py` (el manifest de la marca cae al `manifest.webmanifest` del build).

Busca primero `/opt/frontend-dist` (donde el Dockerfile hornea el build, ADR-022) y despues `frontend/dist` (para armar y
mirar en local sin Docker). El dist esta fuera de `/app` porque el compose de dev monta `./:/app` entero para el `--reload`.
"""
from pathlib import Path

_DOCKER_FRONTEND_DIST = Path("/opt/frontend-dist")
_LOCAL_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def frontend_dist() -> Path:
    return _DOCKER_FRONTEND_DIST if _DOCKER_FRONTEND_DIST.is_dir() else _LOCAL_FRONTEND_DIST
