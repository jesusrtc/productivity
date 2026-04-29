import time
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from ..config import settings, start_time

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    uptime: float
    bridge: str
    sessions: int
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health():
    session_count = len(list(settings.sessions_dir.glob("*.json")))
    return HealthResponse(
        status="ok",
        uptime=time.time() - start_time,
        bridge="not available",
        sessions=session_count,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
