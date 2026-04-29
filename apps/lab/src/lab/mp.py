from __future__ import annotations

from pathlib import Path

from lab import storage


_CONFIG_FILE = Path(__file__).parent / "config" / "mp-prefixes.json"


def load_prefixes() -> dict[str, str]:
    if not _CONFIG_FILE.is_file():
        return {}
    return storage.read_json(_CONFIG_FILE)


def save_prefixes(prefixes: dict[str, str]) -> None:
    # Sort keys for stable diffs.
    storage.write_json(_CONFIG_FILE, dict(sorted(prefixes.items())))


def prefix_for(mp: str) -> str | None:
    return load_prefixes().get(mp)


def objective_from(project_id: str) -> str:
    """Extract the objective portion of a project id by stripping any known prefix."""
    prefixes = load_prefixes()
    # Longest-match first so `drools` wins over `d`
    for mp, pfx in sorted(prefixes.items(), key=lambda kv: -len(kv[1])):
        if project_id == pfx:
            return project_id
        if project_id.startswith(pfx + "-"):
            return project_id[len(pfx) + 1:]
    return project_id
