"""Read-only viewer endpoint for local .ipynb files under the monorepo root.

Parallels ``/api/markdown``: takes a monorepo-relative ``path`` and returns
structured cells. Markdown cells are pre-rendered to HTML server-side so the
SPA doesn't need a client-side markdown library.

The pre-existing ``/api/notebook?repo=...&path=...`` (in ``routes/diff.py``) is
scoped to registered gdiff repos; this endpoint is for notebooks that live
inside ``projects/<id>/notebooks/``.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from core.diff_parser import parse_notebook
from core.routes.markdown import _RENDERER


router = APIRouter()


def _safe_resolve(root: Path, rel: str) -> Path:
    if rel.startswith("/"):
        raise HTTPException(status_code=400, detail="absolute paths not allowed")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path traversal not allowed")
    if not rel.lower().endswith(".ipynb"):
        raise HTTPException(status_code=400, detail="only .ipynb files supported")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(status_code=400, detail="path escapes monorepo")
    return target


@router.get("/api/nb")
async def render_notebook(path: str, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    target = _safe_resolve(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")

    cells = parse_notebook(str(target))
    # Pre-render markdown cells so the client can dump HTML directly.
    for cell in cells:
        if cell.get("cell_type") == "markdown":
            _RENDERER.reset()
            cell["html"] = _RENDERER.convert(cell.get("source", ""))

    return {"path": path, "cells": cells, "mtime": target.stat().st_mtime}
