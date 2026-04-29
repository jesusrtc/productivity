"""Client-side error log ingestion.

Accepts batches of JS error/warning events from the browser and writes them
to the server's rotating log file (logs/server.log) with source="client".
The file handler is configured by main.py's lifespan startup hook; this
module only needs a standard logger.

Rate limiting: 200 events per 60-second window (module-level counters, safe
for single-process uvicorn). Batch size is capped server-side at 50.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_log = logging.getLogger("server.client_errors")

# ─── rate limiting ────────────────────────────────────────────────────────────
_RATE_WINDOW_S = 60
_RATE_LIMIT = 200       # max events per window
_rate_count = 0
_rate_window_start: float = 0.0


def _check_rate(n: int) -> bool:
    """Return True if the batch is within rate limits; update counters."""
    global _rate_count, _rate_window_start
    now = time.monotonic()
    if now - _rate_window_start > _RATE_WINDOW_S:
        _rate_window_start = now
        _rate_count = 0
    if _rate_count >= _RATE_LIMIT:
        return False
    _rate_count += n
    return True


# ─── models ───────────────────────────────────────────────────────────────────

class ClientLogEvent(BaseModel):
    level: str = "error"           # "error" | "warning"
    msg: str
    path: str | None = None        # window.location.pathname at time of event
    session_id: str | None = None  # optional, forwarded as-is


class ClientLogBatch(BaseModel):
    events: list[ClientLogEvent]


# ─── endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/log/client")
async def log_client(body: ClientLogBatch) -> dict:
    """Ingest a batch of client-side log events.

    Each event is written at WARNING or ERROR level to the root logger so it
    lands in logs/server.log alongside server-side entries. The JSON formatter
    in main.py uses the ``source`` and ``path_info`` extras to distinguish
    client entries from server entries.
    """
    # Cap batch to 50 entries regardless of what was sent.
    events = body.events[:50]
    if not events:
        return {"ok": True, "logged": 0}

    if not _check_rate(len(events)):
        return {"ok": False, "reason": "rate_limited", "logged": 0}

    for ev in events:
        # Map "error"/"warning"/"warn" → Python log levels.
        raw = (ev.level or "error").lower()
        level = logging.ERROR if raw == "error" else logging.WARNING

        extra: dict = {
            "source": "client",
            "path_info": ev.path or "",
        }
        if ev.session_id:
            extra["session_id"] = ev.session_id

        # Truncate runaway messages before they hit the log.
        msg = (ev.msg or "")[:4000]
        _log.log(level, msg, extra=extra)

    return {"ok": True, "logged": len(events)}
