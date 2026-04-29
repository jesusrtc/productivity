from __future__ import annotations

import re
from pathlib import Path

import markdown as _md
import yaml
from fastapi import APIRouter, HTTPException, Request


router = APIRouter()

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.+?)\n---\s*\n", re.DOTALL)

_RENDERER = _md.Markdown(
    extensions=["fenced_code", "codehilite", "tables", "toc", "nl2br", "sane_lists"],
    extension_configs={"codehilite": {"css_class": "highlight", "guess_lang": False}},
)


def _safe_resolve(root: Path, rel: str) -> Path:
    if rel.startswith("/"):
        raise HTTPException(status_code=400, detail="absolute paths not allowed")
    if ".." in Path(rel).parts:
        raise HTTPException(status_code=400, detail="path traversal not allowed")
    if not rel.lower().endswith(".md"):
        raise HTTPException(status_code=400, detail="only .md files supported")
    target = (root / rel).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise HTTPException(status_code=400, detail="path escapes monorepo")
    return target


@router.get("/api/markdown")
async def render_markdown(path: str, request: Request) -> dict:
    root: Path = request.app.state.index_cache.root
    target = _safe_resolve(root, path)
    if not target.is_file():
        raise HTTPException(status_code=404, detail="not found")

    text = target.read_text(encoding="utf-8")
    frontmatter: dict = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        try:
            frontmatter = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            frontmatter = {}
        body = text[m.end():]

    _RENDERER.reset()
    html = _RENDERER.convert(body)
    return {"frontmatter": frontmatter, "html": html}
