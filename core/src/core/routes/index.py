from __future__ import annotations

from fastapi import APIRouter, Request


router = APIRouter()


@router.get("/api/index")
async def get_index(request: Request) -> dict:
    cache = request.app.state.index_cache
    return cache.get()
