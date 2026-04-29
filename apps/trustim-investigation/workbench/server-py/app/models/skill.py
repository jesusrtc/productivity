from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Skill(BaseModel):
    name: str
    description: str
    allowed_tools: list[str] = Field(default_factory=list)
    file_path: str
    category: Literal["investigation", "action"]
    area: str


class SkillDetail(Skill):
    """Skill with full markdown content included."""
    content: str


class SkillInventory(BaseModel):
    investigation: list[Skill] = Field(default_factory=list)
    action: list[Skill] = Field(default_factory=list)
