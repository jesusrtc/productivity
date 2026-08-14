from __future__ import annotations

import json
from types import SimpleNamespace

from starlette.datastructures import URL

from core.routes import proxy as proxy_mod
from core.routes.proxy import _is_self_proxy, _proxy_mount_path, _self_proxy_response
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


def test_workspace_proxy_mount_keeps_scope_in_the_path() -> None:
    assert _proxy_mount_path("local", "demo", "web") == (
        "/api/workspace-proxy/local/demo/web/"
    )
    assert _proxy_mount_path(None, "demo", "web") == "/api/proxy/demo/web/"


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


def _configure_proxy(project, **entry) -> None:
    project_json = project / "project.json"
    data = json.loads(project_json.read_text())
    data["proxies"] = [{"name": "web", "port": 3000, **entry}]
    project_json.write_text(json.dumps(data, indent=2))


def _configure_server_file(project, *servers) -> None:
    (project / "servers.json").write_text(json.dumps({"servers": list(servers)}, indent=2))


def _stub_tmux(monkeypatch, *, running: bool = False):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(proxy_mod.term_routes, "_tmux_available", lambda: True)
    monkeypatch.setattr(proxy_mod.term_routes, "_tmux_has_session", lambda _name: running)
    monkeypatch.setattr(proxy_mod.term_routes, "_tmux_child_env", lambda: {})
    monkeypatch.setattr(proxy_mod.subprocess, "run", fake_run)
    return calls


def test_list_proxies_includes_commands_and_mode(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(
        project,
        label="Web app",
        mode="direct",
        start_command="make server-start",
        stop_command="make server-stop",
    )

    response = client.get("/api/proxies?project_id=demo")

    assert response.status_code == 200
    assert response.json() == [{
        "name": "web",
        "host": "localhost",
        "port": 3000,
        "path": "/",
        "label": "Web app",
        "mode": "direct",
        "start_command": "make server-start",
        "stop_command": "make server-stop",
    }]


def test_servers_json_overrides_legacy_project_proxies(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(project, label="Legacy")
    _configure_server_file(project, {
        "name": "api",
        "label": "API",
        "port": 8123,
        "path": "docs",
        "start_command": "make server-start",
    })

    response = client.get("/api/proxies?project_id=demo")

    assert response.status_code == 200
    assert [server["name"] for server in response.json()] == ["api"]
    assert response.json()[0]["path"] == "/docs"


def test_get_server_config_reports_legacy_source(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(project, start_command="make server-start")

    response = client.get("/api/server-config?project_id=demo")

    assert response.status_code == 200
    assert response.json()["source"] == "project.json"
    assert response.json()["is_legacy"] is True
    assert response.json()["servers"][0]["start_command"] == "make server-start"


def test_put_server_config_creates_file_without_mutating_project_json(
    client, seed_project,
) -> None:
    project = seed_project("demo")
    project_before = (project / "project.json").read_text()

    response = client.put("/api/server-config?project_id=demo", json={
        "servers": [{
            "name": "web",
            "port": 5173,
            "start_command": "make server-start",
            "stop_command": "make server-stop",
        }],
    })

    assert response.status_code == 200, response.text
    saved = json.loads((project / "servers.json").read_text())
    assert saved["servers"][0]["host"] == "localhost"
    assert saved["servers"][0]["path"] == "/"
    assert (project / "project.json").read_text() == project_before


def test_invalid_servers_json_is_reported(client, seed_project) -> None:
    project = seed_project("demo")
    (project / "servers.json").write_text('{"servers": [{"name": "web"}]}')

    response = client.get("/api/server-config?project_id=demo")

    assert response.status_code == 422
    assert "port must be between" in response.json()["detail"]


def test_detect_server_config_from_makefile(client, seed_project) -> None:
    project = seed_project("demo")
    (project / "Makefile").write_text(
        "SERVER_PORT ?= 4173\n\nserver-start:\n\tnpm run dev\n\nserver-stop:\n\ttrue\n"
    )

    response = client.get("/api/server-config/detect?project_id=demo")

    assert response.status_code == 200, response.text
    assert response.json()["servers"] == [{
        "name": "app",
        "label": "demo",
        "host": "localhost",
        "port": 4173,
        "path": "/",
        "mode": "proxy",
        "start_command": "make server-start",
        "stop_command": "make server-stop",
    }]


def test_project_info_overlays_servers_json_for_sidebar(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(project, label="Legacy")
    _configure_server_file(project, {"name": "web", "port": 3001})

    response = client.get("/api/project-info?path=demo")

    assert response.status_code == 200
    assert response.json()["server_config_source"] == "servers.json"
    assert [server["name"] for server in response.json()["proxies"]] == ["web"]


def test_proxy_start_requires_configured_command(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(project)

    response = client.post("/api/proxies/demo/web/start")

    assert response.status_code == 409
    assert response.json()["detail"] == "proxy has no start command configured"


def test_proxy_controls_reject_non_make_commands(client, seed_project) -> None:
    project = seed_project("demo")
    _configure_proxy(project, start_command="npm run dev")

    response = client.post("/api/proxies/demo/web/start")

    assert response.status_code == 400
    assert response.json()["detail"] == "start command must be a make command"


def test_proxy_start_runs_make_in_tmux(client, seed_project, monkeypatch) -> None:
    project = seed_project("demo")
    _configure_proxy(project, start_command="make server-start")
    calls = _stub_tmux(monkeypatch)

    response = client.post("/api/proxies/demo/web/start")

    assert response.status_code == 200
    assert response.json()["action"] == "started"
    argv, kwargs = calls[-1]
    assert argv[:4] == ["tmux", "new-session", "-d", "-s"]
    assert argv[-1] == "make server-start"
    assert kwargs["capture_output"] is True


def test_proxy_restart_stops_old_session_before_starting(
    client, seed_project, monkeypatch,
) -> None:
    project = seed_project("demo")
    _configure_proxy(
        project,
        start_command="make server-start",
        stop_command="make server-stop",
    )
    calls = _stub_tmux(monkeypatch, running=True)

    response = client.post("/api/proxies/demo/web/restart")

    assert response.status_code == 200
    assert response.json()["action"] == "restarted"
    assert calls[0][0] == ["make", "server-stop"]
    assert calls[1][0][:3] == ["tmux", "kill-session", "-t"]
    assert calls[2][0][:4] == ["tmux", "new-session", "-d", "-s"]


def test_proxy_stop_runs_make_and_kills_managed_session(
    client, seed_project, monkeypatch,
) -> None:
    project = seed_project("demo")
    _configure_proxy(project, stop_command="make server-stop")
    calls = _stub_tmux(monkeypatch, running=True)

    response = client.post("/api/proxies/demo/web/stop")

    assert response.status_code == 200
    assert response.json()["action"] == "stopped"
    assert calls[0][0] == ["make", "server-stop"]
    assert calls[0][1]["cwd"] == str(project)
    assert calls[1][0][:3] == ["tmux", "kill-session", "-t"]


def test_proxy_control_targets_requested_workspace(
    client, monorepo, tmp_path, monkeypatch,
) -> None:
    """A project tab from another workspace must start its own server there."""
    other_root = tmp_path / "other-workspace"
    project = other_root / "projects" / "demo"
    project.mkdir(parents=True)
    (other_root / "content").mkdir()
    (project / "project.json").write_text(json.dumps({
        "id": "demo",
        "proxies": [{
            "name": "web",
            "port": 3000,
            "start_command": "make server-start",
        }],
    }))

    registry = paths.read_workspace_registry()
    paths.write_workspace_registry({
        "active": registry.get("active"),
        "workspaces": [
            *(registry.get("workspaces") or []),
            {"id": "other", "name": "Other", "path": str(other_root)},
        ],
    })
    monkeypatch.delenv("LAB_TMUX_PREFIX", raising=False)
    proxy_mod.term_routes._WORKSPACE_LABEL_CACHE.clear()
    calls = _stub_tmux(monkeypatch)

    response = client.post("/api/proxies/demo/web/start?workspace=other")

    assert response.status_code == 200, response.text
    argv, _kwargs = calls[-1]
    assert argv[argv.index("-c") + 1] == str(project)
    assert response.json()["session_name"].startswith("neurona-demo-server-web-")
    assert not response.json()["session_name"].startswith("neurona-other-")


def test_workspace_scoped_proxy_reads_the_requested_workspace(
    client, tmp_path,
) -> None:
    """The iframe proxy must not fall back to the server's active workspace."""
    other_root = tmp_path / "other-workspace"
    project = other_root / "projects" / "demo"
    project.mkdir(parents=True)
    (other_root / "content").mkdir()
    (project / "project.json").write_text(json.dumps({"id": "demo"}))
    _configure_server_file(project, {
        "name": "web",
        "host": "localhost",
        "port": 9,
    })
    paths.write_workspace_registry({
        "active": "other",
        "workspaces": [{"id": "other", "name": "Other", "path": str(other_root)}],
    })

    response = client.get("/api/workspace-proxy/other/demo/web/")

    # Port 9 is expected to be unreachable in the test environment. A 502
    # proves the scoped route found the other workspace's declaration; the
    # active fixture workspace would return 404.
    assert response.status_code == 502, response.text
    assert b"Dev server not reachable" in response.content
