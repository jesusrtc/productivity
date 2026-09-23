"""Admin-only host resource view and explicit Lab process controls."""
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from core import auth

router = APIRouter()


class StopRequest(BaseModel):
    pid: int = Field(gt=1)
    created: float = Field(gt=0, allow_inf_nan=False)
    action: Literal["stop", "kill"] = "stop"


class ScanRequest(BaseModel):
    paused: bool


@router.get("/api/resources")
def resources(request: Request) -> dict:
    auth.require_admin(request)
    return {**request.app.state.resource_monitor.snapshot(),
            "files": request.app.state.workspace_snapshots.resource_status()}


@router.post("/api/resources/stop")
def stop(body: StopRequest, request: Request) -> dict:
    auth.require_admin(request)
    return request.app.state.resource_monitor.stop(body.pid, body.created, body.action == "kill")


@router.post("/api/resources/scans")
def scans(body: ScanRequest, request: Request) -> dict:
    auth.require_admin(request)
    store = request.app.state.workspace_snapshots
    store.pause(body.paused)
    return store.resource_status()
