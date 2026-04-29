from __future__ import annotations

from pydantic import BaseModel


class SuccessResponse(BaseModel):
    ok: bool = True
