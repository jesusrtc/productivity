"""Tiny JSON state store for embedded lab apps (e.g. the pytype drill app).

GET /api/appstate/{key}   -> the stored JSON ({} when nothing saved yet)
PUT /api/appstate/{key}   -> store the request body (must be JSON)

Embedded apps served through the per-project proxy AND directly from their
own port are different browser origins, so localStorage fragments between
them. This endpoint gives them one shared, server-side home for small
state blobs. Files live under ``content/.appstate/<key>.json`` (content/
already holds lab state and is gitignored). Writes are atomic
(tmp + rename) so a crash mid-write can't corrupt the previous state.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter()

_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Generous cap — pytype's whole SRS state is ~20KB.
_MAX_BYTES = 1_000_000


def _state_file(root: Path, key: str) -> Path:
    return root / "content" / ".appstate" / (key + ".json")


@router.get("/api/appstate/{key}")
async def appstate_get(key: str, request: Request) -> Response:
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="bad key")
    root: Path = request.app.state.index_cache.root
    f = _state_file(root, key)
    if not f.exists():
        return Response(content="{}", media_type="application/json")
    return Response(content=f.read_bytes(), media_type="application/json")


@router.put("/api/appstate/{key}")
async def appstate_put(key: str, request: Request) -> dict:
    if not _KEY_RE.match(key):
        raise HTTPException(status_code=400, detail="bad key")
    body = await request.body()
    if len(body) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="state too large")
    try:
        json.loads(body or b"null")
    except Exception:
        raise HTTPException(status_code=400, detail="body must be valid JSON")
    root: Path = request.app.state.index_cache.root
    f = _state_file(root, key)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_bytes(body)
    tmp.replace(f)
    return {"ok": True}
