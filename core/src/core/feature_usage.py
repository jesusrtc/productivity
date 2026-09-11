"""Daily UI feature counters, independent of rotating diagnostic logs."""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3

FILENAME = "feature-usage.sqlite3"


def increment(log_dir: Path, day: str, feature: str) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(log_dir / FILENAME, timeout=5)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS usage (
            day TEXT NOT NULL, feature TEXT NOT NULL, usage_count INTEGER NOT NULL,
            PRIMARY KEY (day, feature))""")
        db.execute("""INSERT INTO usage VALUES (?, ?, 1)
            ON CONFLICT(day, feature) DO UPDATE SET usage_count = usage_count + 1""",
            (day, feature))


def read(log_dir: Path, day: str | None = None) -> list[dict]:
    path = log_dir / FILENAME
    if not path.exists():
        return []
    with closing(sqlite3.connect(path, timeout=5)) as db:
        rows = db.execute(
            "SELECT day, feature, usage_count FROM usage" + (" WHERE day = ?" if day else ""),
            (day,) if day else (),
        ).fetchall()
    return [{"date": row[0], "feature": row[1], "usage_count": row[2]} for row in rows]


def clear(log_dir: Path) -> bool:
    path = log_dir / FILENAME
    if not path.exists():
        return False
    with closing(sqlite3.connect(path, timeout=5)) as db, db:
        db.execute("DELETE FROM usage")
    return True
