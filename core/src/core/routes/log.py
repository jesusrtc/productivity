"""Client-side log ingestion.

Accepts batches of JS info/warning/error events from the browser and writes
them to the server's file logs with source="client". The file handlers are
configured by main.py's lifespan startup hook; this module only needs a
standard logger.

Rate limiting: 200 events per 60-second window (module-level counters, safe
for single-process uvicorn). Batch size is capped server-side at 50.
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_log = logging.getLogger("core.client_errors")

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
    level: str = "info"            # "info" | "warning" | "error"
    msg: str
    path: str | None = None        # window.location.pathname at time of event
    session_id: str | None = None  # optional, forwarded as-is
    action: str | None = None
    target: str | None = None
    event_type: str | None = None
    href: str | None = None
    method: str | None = None
    status_code: int | None = None
    duration_ms: float | None = None
    source_url: str | None = None


class ClientLogBatch(BaseModel):
    events: list[ClientLogEvent]


# ─── endpoint ─────────────────────────────────────────────────────────────────

@router.post("/api/log/client")
async def log_client(body: ClientLogBatch) -> dict:
    """Ingest a batch of client-side log events.

    Each event is written at INFO/WARNING/ERROR level to the root logger so it
    lands in the frontend split logs. The JSON formatter in main.py uses the
    ``source`` and ``path_info`` extras to distinguish client entries from core
    entries.
    """
    # Cap batch to 50 entries regardless of what was sent.
    events = body.events[:50]
    if not events:
        return {"ok": True, "logged": 0}

    if not _check_rate(len(events)):
        return {"ok": False, "reason": "rate_limited", "logged": 0}

    for ev in events:
        # Map "error"/"warning"/"warn"/"info" → Python log levels.
        raw = (ev.level or "error").lower()
        if raw == "error":
            level = logging.ERROR
        elif raw in ("warning", "warn"):
            level = logging.WARNING
        else:
            level = logging.INFO

        extra: dict = {
            "source": "client",
            "path_info": ev.path or "",
        }
        if ev.session_id:
            extra["session_id"] = ev.session_id

        for field in (
            "action",
            "target",
            "event_type",
            "href",
            "method",
            "status_code",
            "duration_ms",
            "source_url",
        ):
            value = getattr(ev, field)
            if value is not None:
                extra[field] = value

        # Truncate runaway messages before they hit the log.
        msg = (ev.msg or "")[:4000]
        _log.log(level, msg, extra=extra)

    return {"ok": True, "logged": len(events)}
