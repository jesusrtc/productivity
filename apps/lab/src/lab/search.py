from __future__ import annotations

import json
import re
from pathlib import Path

from lab import storage


MAX_RESULTS_PER_KIND = 50
SNIPPET_CHARS = 120


def _snippet(text: str, query: str) -> str:
    q_low = query.lower()
    idx = text.lower().find(q_low)
    if idx < 0:
        return text[:SNIPPET_CHARS]
    start = max(0, idx - SNIPPET_CHARS // 2)
    end = min(len(text), idx + len(query) + SNIPPET_CHARS // 2)
    snippet = text[start:end].replace("\n", " ")
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + snippet + suffix


def _matches(haystack: str | None, query_low: str) -> bool:
    return haystack is not None and query_low in haystack.lower()


def search(root: Path, query: str) -> dict:
    """Grep-based search over content/. Returns {projects, tasks, docs}."""
    q = (query or "").strip()
    if not q:
        return {"query": "", "projects": [], "tasks": [], "docs": []}
    q_low = q.lower()

    projects: list[dict] = []
    tasks: list[dict] = []
    docs: list[dict] = []

    projects_root = root / "content" / "projects"
    if projects_root.is_dir():
        for child in sorted(projects_root.iterdir()):
            if not child.is_dir():
                continue
            pjson = child / "project.json"
            tjson = child / "tasks.json"
            try:
                p = storage.read_json(pjson)
            except (OSError, json.JSONDecodeError):
                p = None
            if p is not None:
                if (_matches(p.get("id"), q_low)
                        or _matches(p.get("name"), q_low)
                        or _matches(p.get("description"), q_low)
                        or any(_matches(t, q_low) for t in (p.get("tags") or []))
                        or any(_matches(l, q_low) for l in (p.get("labels") or []))):
                    projects.append({
                        "id": p.get("id", child.name),
                        "name": p.get("name", ""),
                        "description": p.get("description", ""),
                        "status": p.get("status", ""),
                        "snippet": _snippet(p.get("description") or p.get("name") or p.get("id", ""), q),
                    })
                    if len(projects) >= MAX_RESULTS_PER_KIND:
                        break
            try:
                doc = storage.read_json(tjson)
            except (OSError, json.JSONDecodeError):
                doc = None
            if doc is not None:
                for t in doc.get("tasks", []):
                    if (_matches(t.get("title"), q_low)
                            or _matches(t.get("blocker"), q_low)
                            or any(_matches(tag, q_low) for tag in (t.get("tags") or []))):
                        tasks.append({
                            "project_id": child.name,
                            "task_id": t.get("id"),
                            "title": t.get("title", ""),
                            "status": t.get("status", ""),
                            "priority": t.get("priority", ""),
                            "snippet": _snippet(t.get("title", ""), q),
                        })
                        if len(tasks) >= MAX_RESULTS_PER_KIND:
                            break

    # Walk all .md files under content/
    content_root = root / "content"
    if content_root.is_dir():
        for md in sorted(content_root.rglob("*.md")):
            try:
                text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if q_low in text.lower():
                docs.append({
                    "path": str(md.relative_to(root)),
                    "snippet": _snippet(text, q),
                })
                if len(docs) >= MAX_RESULTS_PER_KIND:
                    break

    return {
        "query": q,
        "projects": projects,
        "tasks": tasks,
        "docs": docs,
    }
