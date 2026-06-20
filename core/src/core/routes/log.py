"""Client-side log ingestion and read-only log tailing.

Accepts batches of JS info/warning/error events from the browser and writes
them to the server's file logs with source="client". The file handlers are
configured by main.py's lifespan startup hook; this module only needs a
standard logger.

Rate limiting: 200 events per 60-second window (module-level counters, safe
for single-process uvicorn). Batch size is capped server-side at 50.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter()

_log = logging.getLogger("core.client_errors")

_LOG_FILES = (
    "errors.log",
    "backend-errors.log",
    "frontend-errors.log",
    "backend.log",
    "frontend.log",
    "server.log",
)
_DEFAULT_LOG_FILE = "errors.log"
_DEFAULT_TAIL = 500
_MAX_TAIL = 5000

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


def _log_dir(request: Request) -> Path:
    cache = getattr(request.app.state, "index_cache", None)
    if cache is not None:
        return Path(cache.root) / "logs"

    from core import config

    return config.monorepo_root() / "logs"


def _is_allowed_log_name(name: str) -> bool:
    if Path(name).name != name:
        return False
    for base in _LOG_FILES:
        if name == base:
            return True
        if name.startswith(base + "."):
            suffix = name[len(base) + 1:]
            return suffix.isdigit()
    return False


def _tail_text_lines(path: Path, limit: int) -> list[str]:
    """Return the last ``limit`` lines without reading a whole rotated log."""
    if limit <= 0 or not path.exists():
        return []

    chunks: list[bytes] = []
    newlines = 0
    with path.open("rb") as fh:
        fh.seek(0, 2)
        pos = fh.tell()
        while pos > 0 and newlines <= limit:
            size = min(8192, pos)
            pos -= size
            fh.seek(pos)
            chunk = fh.read(size)
            chunks.append(chunk)
            newlines += chunk.count(b"\n")

    text = b"".join(reversed(chunks)).decode("utf-8", errors="replace")
    return text.splitlines()[-limit:]


def _parse_log_line(line: str) -> dict:
    try:
        value = json.loads(line)
    except json.JSONDecodeError:
        return {"raw": line}
    if isinstance(value, dict):
        return value
    return {"raw": line}


def _log_file_meta(log_dir: Path, name: str) -> dict:
    path = log_dir / name
    exists = path.exists()
    stat = path.stat() if exists else None
    return {
        "name": name,
        "exists": exists,
        "size": stat.st_size if stat else 0,
        "modified": stat.st_mtime if stat else None,
        "error_only": name.startswith("errors.log")
        or name.startswith("backend-errors.log")
        or name.startswith("frontend-errors.log"),
    }


def _error_log_state(log_dir: Path) -> dict:
    path = log_dir / _DEFAULT_LOG_FILE
    if not path.exists():
        return {
            "file": _DEFAULT_LOG_FILE,
            "exists": False,
            "size": 0,
            "modified": None,
            "cursor": f"{_DEFAULT_LOG_FILE}:missing",
        }

    stat = path.stat()
    return {
        "file": _DEFAULT_LOG_FILE,
        "exists": True,
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "cursor": f"{_DEFAULT_LOG_FILE}:{stat.st_mtime_ns}:{stat.st_size}",
    }


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


@router.get("/api/log/files")
async def log_files(request: Request) -> dict:
    """List known log files that the UI is allowed to tail."""
    log_dir = _log_dir(request)
    names = set(_LOG_FILES)
    if log_dir.exists():
        for base in _LOG_FILES:
            for path in log_dir.glob(base + ".*"):
                if _is_allowed_log_name(path.name):
                    names.add(path.name)

    files = [_log_file_meta(log_dir, name) for name in sorted(names)]
    return {
        "default_file": _DEFAULT_LOG_FILE,
        "default_tail": _DEFAULT_TAIL,
        "max_tail": _MAX_TAIL,
        "files": files,
    }


@router.get("/api/log/error-state")
async def log_error_state(request: Request) -> dict:
    """Current cursor for the shared errors-only log.

    The UI stores this cursor in localStorage after the user opens the log
    viewer. If the cursor changes later, the Logs button can turn red without
    the server needing per-browser state.
    """
    return _error_log_state(_log_dir(request))


@router.get("/api/log/tail")
async def log_tail(
    request: Request,
    file: str = _DEFAULT_LOG_FILE,
    tail: int = Query(default=_DEFAULT_TAIL, ge=1, le=_MAX_TAIL),
) -> dict:
    """Return a parsed tail from one whitelisted log file."""
    if not _is_allowed_log_name(file):
        raise HTTPException(status_code=400, detail="unsupported log file")

    log_dir = _log_dir(request)
    path = log_dir / file
    if not path.exists():
        raise HTTPException(status_code=404, detail="log file not found")

    lines = _tail_text_lines(path, tail)
    return {
        "file": file,
        "tail": tail,
        "line_count": len(lines),
        "state": _error_log_state(log_dir),
        "entries": [_parse_log_line(line) for line in lines],
    }


@router.get("/logs", response_class=HTMLResponse)
async def logs_page() -> HTMLResponse:
    """Standalone log viewer, useful when the server is running on port 8080."""
    return HTMLResponse(
        """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>lab logs</title>
  <link rel="stylesheet" href="/static/css/app.css">
  <script src="/static/js/lib/error-report.js"></script>
  <script src="/static/js/lib/log-alert.js" defer></script>
</head>
<body>
  <header>
    <h1><a href="/">lab</a></h1>
    <nav>
      <a href="/logs">Logs</a>
      <a href="/#/logs">SPA logs</a>
    </nav>
  </header>
  <main id="view"></main>
  <script type="module">
    import { render } from "/static/js/views/logs.js";
    render(document.getElementById("view"), { params: new URLSearchParams(location.search) });
  </script>
</body>
</html>"""
    )
