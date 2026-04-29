from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab import index as index_mod


class IndexCache:
    """Thread-safe in-memory cache of the global index.

    On first access, builds from disk. On rebuild, regenerates from on-disk
    projects and persists to knowledge/.index.json.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()
        self._data: dict[str, Any] | None = None

    @property
    def root(self) -> Path:
        return self._root

    def rebuild(self) -> dict[str, Any]:
        with self._lock:
            data = index_mod.build_index(self._root)
            index_mod.write_index(self._root, data)
            self._data = data
            return data

    def get(self) -> dict[str, Any]:
        with self._lock:
            if self._data is not None:
                return self._data
        # Build outside the lock to avoid holding it during disk IO.
        return self.rebuild()


@dataclass
class IndexUpdatedEvent:
    ts: str

    def to_json(self) -> dict:
        return {"type": "index-updated", "ts": self.ts}


class WsBroadcaster:
    """In-memory list of connected WebSockets with an async publish fan-out."""

    def __init__(self) -> None:
        self._clients: list = []
        self._lock = asyncio.Lock()

    async def add(self, websocket) -> None:
        async with self._lock:
            self._clients.append(websocket)

    async def remove(self, websocket) -> None:
        async with self._lock:
            if websocket in self._clients:
                self._clients.remove(websocket)

    async def publish(self, event: IndexUpdatedEvent) -> None:
        async with self._lock:
            clients = list(self._clients)
        broken: list = []
        for ws in clients:
            try:
                await ws.send_json(event.to_json())
            except Exception:
                broken.append(ws)
        if broken:
            async with self._lock:
                for ws in broken:
                    if ws in self._clients:
                        self._clients.remove(ws)
