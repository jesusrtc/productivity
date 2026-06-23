from __future__ import annotations

import json
from types import SimpleNamespace

from starlette.datastructures import URL

from core.routes.proxy import _is_self_proxy, _self_proxy_response
from lab import paths


def _conn(url: str, server=("127.0.0.1", 8080)):
    return SimpleNamespace(url=URL(url), scope={"server": server, "scheme": "http"})


def test_self_proxy_detects_lab_port_on_localhost() -> None:
    conn = _conn("http://127.0.0.1:8080/api/proxy/demo/8080/")

    assert _is_self_proxy({"host": "localhost", "port": 8080}, conn)
    assert _is_self_proxy({"host": "127.0.0.1", "port": 8080}, conn)
    assert _is_self_proxy({"host": "::1", "port": 8080}, conn)
    assert not _is_self_proxy({"host": "localhost", "port": 5173}, conn)
    assert not _is_self_proxy({"host": "example.com", "port": 8080}, conn)


def test_self_proxy_response_fails_fast_with_explanation() -> None:
    response = _self_proxy_response("demo", "frontend", {"host": "localhost", "port": 8080})

    assert response.status_code == 409
    assert b"Proxy points at Lab itself" in response.body
    assert b"localhost:8080" in response.body


def _jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_lab_appstate_not_rewritten_from_proxy_referer(client) -> None:
    response = client.put(
        "/api/appstate/pytype",
        headers={"referer": "http://testserver/api/proxy/programming/Programming/"},
        content=json.dumps({"savedAt": 1, "cards": {}, "unlocked": {}}),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_unreachable_proxy_placeholder_does_not_enter_error_log(
    client, monorepo, seed_project
) -> None:
    project = seed_project("demo")
    project_json = project / "project.json"
    data = json.loads(project_json.read_text())
    data["proxies"] = [{"name": "missing", "port": 9}]
    project_json.write_text(json.dumps(data, indent=2))

    response = client.get("/api/proxy/demo/missing/")

    assert response.status_code == 502
    assert b"Dev server not reachable" in response.content
    errors = _jsonl(paths.logs_dir(monorepo) / "errors.log")
    assert not any(r.get("path") == "/api/proxy/demo/missing/" for r in errors)
