from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Query, Request

from lab.search import search as search_impl

from core import auth


router = APIRouter()


@router.get("/api/search")
def api_search(request: Request, q: str = Query("", min_length=0)) -> dict:
    root = auth.request_root(request)
    return search_impl(root, q)
