from __future__ import annotations

from fastapi import APIRouter, Request

from core import auth


router = APIRouter()


@router.get("/api/index")
def get_index(request: Request) -> dict:
    return auth.request_index(request)
