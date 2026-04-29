from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BackgroundInvestigation(BaseModel):
    id: str
    session_id: str
    alert_id: str | None = None
    status: Literal["running", "completed", "failed", "cancelled"] = "running"
    started_at: str = ""
    finished_at: str | None = None
    error: str | None = None
    doc_url: str | None = None
    node_count: int = 0


class ResumeResult(BaseModel):
    ok: bool = True
    session_id: str = ""
    status: str = ""
    message: str = ""
