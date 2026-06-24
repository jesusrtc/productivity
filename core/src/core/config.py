from __future__ import annotations

import os
from pathlib import Path

from lab import paths


def monorepo_root() -> Path:
    """Return the active workspace root used by all backend routes.

    Honors `LAB_WORKSPACE` first and keeps `LAB_ROOT` as a migration alias.
    """
    return paths.find_workspace_root()


def host() -> str:
    return os.environ.get("LAB_HOST", "127.0.0.1")


def port() -> int:
    return int(os.environ.get("LAB_PORT", "3333"))


DEBOUNCE_MS = int(os.environ.get("LAB_DEBOUNCE_MS", "250"))
