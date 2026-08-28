"""Project Runtime configuration and build endpoints for notebooks."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth
from core.notebook_runtime import (
    ProjectRuntimeSpec,
    RuntimeBuildError,
    RuntimeConfigError,
    build_runtime,
    runtime_status,
    save_runtime_spec,
)
from core.routes.nb_exec import _safe_resolve


router = APIRouter()


class RuntimeSaveBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the workspace root")
    spec: ProjectRuntimeSpec


class RuntimeBuildBody(BaseModel):
    path: str = Field(..., description="Notebook path relative to the workspace root")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RuntimeConfigError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, RuntimeBuildError):
        detail: dict[str, str] = {"message": exc.detail}
        if exc.log:
            detail["log"] = exc.log[-20000:]
        return HTTPException(status_code=422, detail=detail)
    return HTTPException(status_code=500, detail=str(exc))


@router.get("/api/nb/runtime")
def get_runtime(path: str, request: Request) -> dict:
    root = auth.request_root(request)
    _safe_resolve(root, path)
    try:
        return runtime_status(root, path)
    except (RuntimeConfigError, RuntimeBuildError) as exc:
        raise _map_error(exc) from exc


@router.put("/api/nb/runtime")
def put_runtime(body: RuntimeSaveBody, request: Request) -> dict:
    root = auth.request_root(request)
    _safe_resolve(root, body.path)
    try:
        target = save_runtime_spec(root, body.path, body.spec)
        status = runtime_status(root, body.path)
    except (RuntimeConfigError, RuntimeBuildError) as exc:
        raise _map_error(exc) from exc
    return {**status, "config_path": str(target.relative_to(root))}


@router.post("/api/nb/runtime/build")
async def post_runtime_build(body: RuntimeBuildBody, request: Request) -> dict:
    root = auth.request_root(request)
    _safe_resolve(root, body.path)
    try:
        built = await asyncio.to_thread(build_runtime, root, body.path)
        return {"built": built, "runtime": runtime_status(root, body.path)}
    except (RuntimeConfigError, RuntimeBuildError) as exc:
        raise _map_error(exc) from exc
