from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..models.skill import Skill, SkillDetail, SkillInventory

router = APIRouter(prefix="/skills", tags=["skills"])


# ---------------------------------------------------------------------------
# Skill discovery (ported from server/domains/skills/store.ts)
# ---------------------------------------------------------------------------

def _parse_frontmatter(file_path: Path, category: str, dir_name: str) -> Skill | None:
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return None

    fm_match = re.match(r"^---\n([\s\S]*?)\n---", content)
    if not fm_match:
        return Skill(
            name=dir_name,
            description="",
            allowed_tools=[],
            file_path=str(file_path),
            category=category,  # type: ignore[arg-type]
            area=dir_name,
        )

    fm = fm_match.group(1)
    name_match = re.search(r"name:\s*(.+)", fm)
    name = name_match.group(1).strip() if name_match else dir_name

    # Multi-line description (>- or >) then single-line fallback
    desc_match = re.search(r"description:\s*>-?\s*\n([\s\S]*?)(?=\n\w|\n---)", fm)
    if desc_match:
        description = re.sub(r"\n\s+", " ", desc_match.group(1).strip())
    else:
        desc_single = re.search(r"description:\s*(.+)", fm)
        description = desc_single.group(1).strip() if desc_single else ""

    tools_match = re.search(r"allowed-tools:\s*(.+)", fm)
    tools_str = tools_match.group(1).strip() if tools_match else ""
    allowed_tools = [t.strip() for t in tools_str.split(",") if t.strip()]

    return Skill(
        name=name,
        description=description,
        allowed_tools=allowed_tools,
        file_path=str(file_path),
        category=category,  # type: ignore[arg-type]
        area=dir_name,
    )


def discover_skills(skills_dir: Path) -> SkillInventory:
    inv = SkillInventory()
    if not skills_dir.exists():
        return inv

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue

        if entry.name == "actions":
            for action_entry in sorted(entry.iterdir()):
                if not action_entry.is_dir():
                    continue
                skill_file = action_entry / "SKILL.md"
                if skill_file.exists():
                    meta = _parse_frontmatter(skill_file, "action", action_entry.name)
                    if meta:
                        inv.action.append(meta)
        else:
            skill_file = entry / "SKILL.md"
            if skill_file.exists():
                meta = _parse_frontmatter(skill_file, "investigation", entry.name)
                if meta:
                    inv.investigation.append(meta)

    return inv


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=SkillInventory)
async def list_skills():
    return discover_skills(settings.skills_dir)


@router.get("/{name}", response_model=SkillDetail)
async def get_skill(name: str):
    inv = discover_skills(settings.skills_dir)
    for skill in inv.investigation + inv.action:
        if skill.name == name:
            try:
                content = Path(skill.file_path).read_text(encoding="utf-8")
            except OSError:
                raise HTTPException(status_code=500, detail="Could not read skill file")
            return SkillDetail(**skill.model_dump(), content=content)

    raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
