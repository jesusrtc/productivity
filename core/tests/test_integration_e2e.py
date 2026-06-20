from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_cli_write_propagates_through_watcher_to_ws(monorepo: Path, seed_project) -> None:
    """Full loop: create project -> fs event -> watcher rebuild -> WS broadcast."""
    from core.main import create_app

    app = create_app()
    with TestClient(app) as client:
        # Index starts empty
        r = client.get("/api/index")
        assert r.json()["projects"] == []

        with client.websocket_connect("/ws") as ws:
            # Simulate "lab project new" by creating the project.json directly.
            seed_project("alpha")
            # Wait for debounce + rebuild
            time.sleep(0.5)
            msg = ws.receive_json()
            assert msg["type"] == "index-updated"

        # Index reflects the change
        r = client.get("/api/index")
        ids = [p["id"] for p in r.json()["projects"]]
        assert ids == ["alpha"]
