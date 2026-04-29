from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.common import SuccessResponse
from ..models.investigation import BackgroundInvestigation, ResumeResult

router = APIRouter(prefix="/investigations", tags=["investigations"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ID_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _sanitize_id(raw: str) -> str:
    return _ID_RE.sub("", raw)


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class StartInvestigationBody(BaseModel):
    session_id: str = Field(alias="sessionId")
    prompt: str
    alert_id: str | None = Field(default=None, alias="alertId")
    session_name: str | None = Field(default=None, alias="sessionName")

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Routes (stubs — background agent not ported to Python yet)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[BackgroundInvestigation])
async def list_investigations():
    return []


@router.post("/start", response_model=BackgroundInvestigation)
async def start_investigation(body: StartInvestigationBody):
    if not body.session_id or not body.prompt:
        raise HTTPException(status_code=400, detail="sessionId and prompt required")
    return BackgroundInvestigation(
        id=f"inv-{_sanitize_id(body.session_id)}",
        session_id=body.session_id,
        alert_id=body.alert_id,
        status="running",
        started_at="",
    )


@router.get("/{session_id}", response_model=BackgroundInvestigation)
async def get_investigation(session_id: str):
    raise HTTPException(status_code=404, detail="Not found")


@router.delete("/{session_id}", response_model=SuccessResponse)
async def stop_investigation(session_id: str):
    return SuccessResponse()


@router.post("/{session_id}/resume", response_model=ResumeResult)
async def resume_investigation(session_id: str):
    return ResumeResult(
        ok=False,
        session_id=_sanitize_id(session_id),
        status="not_implemented",
        message="Background agent not available in Python server yet",
    )
