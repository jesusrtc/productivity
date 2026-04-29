from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """Read a JSON file. Raises FileNotFoundError if missing."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to a temp file in the same directory, then rename.

    Creates parent directories if needed. Output is pretty-printed with 2-space
    indentation and a trailing newline for clean diffs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same-directory tempfile guarantees the rename is atomic on POSIX.
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        # Clean up temp on failure
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
