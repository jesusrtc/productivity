from __future__ import annotations

import os
from pathlib import Path

from lab import paths


def monorepo_root() -> Path:
    """Return the monorepo root used by all backend routes.

    Honors the same `LAB_ROOT` env var as the CLI — so tests can point the
    backend at a temp directory the same way.
    """
    return paths.find_monorepo_root()


def host() -> str:
    return os.environ.get("LAB_HOST", "127.0.0.1")


def port() -> int:
    return int(os.environ.get("LAB_PORT", "3333"))


DEBOUNCE_MS = int(os.environ.get("LAB_DEBOUNCE_MS", "250"))
