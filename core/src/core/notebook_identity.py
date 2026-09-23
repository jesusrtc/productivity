"""Stable notebook session names without loading the Jupyter execution stack."""
from __future__ import annotations

import hashlib
from pathlib import Path


def notebook_identity(root: Path, rel_path: str) -> str:
    from lab import naming
    from lab.workspace_identity import id_at
    parts = Path(rel_path).parts
    if len(parts) >= 3 and parts[0] == naming.workspaces_dir(root).name:
        return str(Path(parts[0], id_at(root / parts[0] / parts[1]), *parts[2:]))
    return rel_path


def session_name(root: Path, rel_path: str) -> str:
    key = f"{root.resolve()}\0{notebook_identity(root, rel_path)}".encode("utf-8")
    return "local-" + hashlib.sha1(key).hexdigest()[:12]
