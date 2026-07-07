"""Tests for /api/servers/* — per-project dev-server management.

These tests run against a per-test fake ``tmux`` binary on PATH (mirroring
``test_term_routes.py``'s ``_write_fake_tmux``) so the tmux side of the flow
is real without touching the user's production tmux server/socket. The
``make server-stop`` target IS actually invoked via the real ``make``
binary (fast/no-op recipes only) so the "best effort cleanup ran" behavior
is exercised for real rather than mocked away.
"""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest


# ─── fake tmux (copied from test_term_routes.py's _write_fake_tmux; kept in
# sync manually rather than cross-importing between test modules) ───────────

def _write_fake_tmux(bin_dir: Path, state_file: Path) -> Path:
    tmux = bin_dir / "tmux"
    tmux.write_text(textwrap.dedent(r'''#!/usr/bin/env python3
        import json
        import sys
        import time
        from pathlib import Path

        STATE = Path(__STATE_FILE__)

        def load():
            if not STATE.is_file():
                return {}
            try:
                return json.loads(STATE.read_text())
            except Exception:
                return {}

        def save(data):
            STATE.write_text(json.dumps(data))

        def opt(args, flag, default=None):
            try:
                return args[args.index(flag) + 1]
            except (ValueError, IndexError):
                return default

        args = sys.argv[1:]
        if not args:
            sys.exit(0)

        cmd = args[0]
        data = load()

        if cmd == "list-sessions":
            sessions = data.get("sessions", {})
            if not sessions:
                sys.stderr.write("no server running\n")
                sys.exit(1)
            fmt = opt(args, "-F", "#{session_name}")
            rows = []
            for name, info in sessions.items():
                if fmt == "#{session_name}":
                    rows.append(name)
                else:
                    rows.append("|".join([
                        name,
                        str(info.get("created", 0)),
                        str(info.get("attached", 0)),
                        str(info.get("windows", 1)),
                    ]))
            sys.stdout.write("\n".join(rows) + ("\n" if rows else ""))
            sys.exit(0)

        if cmd == "new-session":
            name = opt(args, "-s")
            if not name:
                sys.stderr.write("missing session name\n")
                sys.exit(1)
            sessions = data.setdefault("sessions", {})
            if name in sessions:
                sys.stderr.write("duplicate session: " + name + "\n")
                sys.exit(1)
            sessions[name] = {
                "created": int(time.time()),
                "attached": 0,
                "windows": 1,
                "cwd": opt(args, "-c", ""),
                "cmd": args[-1] if args else "",
            }
            save(data)
            sys.exit(0)

        if cmd == "has-session":
            name = opt(args, "-t")
            sys.exit(0 if name in data.get("sessions", {}) else 1)

        if cmd == "kill-session":
            name = opt(args, "-t")
            data.get("sessions", {}).pop(name, None)
            save(data)
            sys.exit(0)

        if cmd == "capture-pane":
            sys.stdout.write("$ \n")
            sys.exit(0)

        if cmd in ("set-option", "bind-key", "unbind-key"):
            sys.exit(0)

        if cmd == "-V":
            sys.stdout.write("tmux fake\n")
            sys.exit(0)

        sys.stderr.write("unsupported fake tmux command: " + " ".join(args) + "\n")
        sys.exit(1)
    ''').replace("\n        ", "\n").replace("__STATE_FILE__", json.dumps(str(state_file))))
    tmux.chmod(0o755)
    return tmux


@pytest.fixture()
def isolated_tmux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Unique tmux prefix plus a fake tmux binary on PATH, per test."""
    prefix = f"lab-test-{uuid.uuid4().hex[:6]}-"
    monkeypatch.setenv("LAB_TMUX_PREFIX", prefix)
    state_file = tmp_path / "fake-tmux-state.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_tmux(bin_dir, state_file)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    yield prefix


@pytest.fixture(autouse=True)
def _reset_servers_module_state():
    """Module-level caches/status map are process-global; scrub between
    tests so no test can observe another's leftovers."""
    import core.routes.servers as servers_mod

    def _clear():
        servers_mod._discovery_cache.clear()
        with servers_mod._STATUS_LOCK:
            servers_mod._STATUS.clear()

    _clear()
    yield
    _clear()


def _write_server_makefile(pdir: Path, *, port: int | None = None,
                           health_url: str | None = None,
                           with_stop: bool = True,
                           stop_recipe: str = "@true") -> None:
    lines: list[str] = []
    if port is not None:
        lines.append(f"SERVER_PORT = {port}")
    if health_url is not None:
        lines.append(f"SERVER_HEALTH_URL = {health_url}")
    if lines:
        lines.append("")
    lines.append("server-start:")
    lines.append("\t@echo starting")
    if with_stop:
        lines.append("")
        lines.append("server-stop:")
        lines.append(f"\t{stop_recipe}")
    (pdir / "Makefile").write_text("\n".join(lines) + "\n")


@pytest.fixture()
def server_project(seed_project):
    def _create(project_id: str = "webapp", **kwargs) -> Path:
        pdir = seed_project(project_id)
        _write_server_makefile(pdir, **kwargs)
        return pdir
    return _create


def _desired_state(root: Path) -> dict:
    p = root / ".lab" / "state" / "servers.json"
    if not p.is_file():
        return {}
    return json.loads(p.read_text())


@pytest.fixture()
def ws(monorepo: Path) -> str:
    """Register the fixture workspace under a stable id ("main"), the way
    a real ``lab init``/``lab workspace`` flow would — so
    ``/api/servers/<id>/...`` URLs read cleanly. Every single-workspace
    test in this file keys off this id instead of the incidental fallback
    (unregistered-workspace dirname) id."""
    from lab import paths
    paths.register_workspace(monorepo, name="Main", active=True)
    return "main"


def _write_project_makefile(root: Path, project_id: str, **kwargs) -> Path:
    pdir = root / "projects" / project_id
    pdir.mkdir(parents=True, exist_ok=True)
    _write_server_makefile(pdir, **kwargs)
    return pdir


@pytest.fixture()
def second_workspace(ws: str, tmp_path: Path):
    """A second registered workspace ("second"), independent of the
    ``monorepo``/``ws`` one, for cross-workspace tests. Returns
    ``(workspace_id, root)``."""
    from lab import paths
    root = tmp_path / "second"
    (root / "projects").mkdir(parents=True)
    (root / "content").mkdir(parents=True, exist_ok=True)
    paths.register_workspace(root, name="Second", active=False)
    return "second", root


# ─── Makefile parsing (unit-level) ──────────────────────────────────────────

def test_parse_makefile_port_and_stop_target() -> None:
    import core.routes.servers as servers_mod

    text = "SERVER_PORT = 8006\n\nserver-start:\n\t@echo hi\n\nserver-stop:\n\t@true\n"
    info = servers_mod._parse_makefile(text)
    assert info == {
        "has_start": True, "has_stop": True,
        "port": 8006, "health_url": "http://127.0.0.1:8006/",
    }


def test_parse_makefile_explicit_health_url_wins_over_port() -> None:
    import core.routes.servers as servers_mod

    text = "SERVER_PORT = 8006\nSERVER_HEALTH_URL = http://127.0.0.1:8006/healthz\n\nserver-start:\n\t@echo hi\n"
    info = servers_mod._parse_makefile(text)
    assert info["health_url"] == "http://127.0.0.1:8006/healthz"


def test_parse_makefile_no_vars_no_health_check() -> None:
    import core.routes.servers as servers_mod

    info = servers_mod._parse_makefile("server-start:\n\t@echo hi\n")
    assert info["has_start"] is True
    assert info["has_stop"] is False
    assert info["port"] is None
    assert info["health_url"] is None


def test_parse_makefile_without_start_target() -> None:
    import core.routes.servers as servers_mod

    info = servers_mod._parse_makefile("server-stop:\n\t@true\n")
    assert info["has_start"] is False


# ─── 1. Discovery ────────────────────────────────────────────────────────────

def test_discovery_lists_project_with_server_makefile(client, server_project, isolated_tmux, ws) -> None:
    # Obscure port: the health check now runs even for stopped servers (to
    # detect hand-started "external" ones), so a commonly-used dev port
    # would make this flaky whenever a real local server occupies it.
    server_project("webapp", port=59173, with_stop=True)
    r = client.get("/api/servers")
    assert r.status_code == 200, r.text
    servers = r.json()["servers"]
    assert len(servers) == 1
    row = servers[0]
    assert row["project_id"] == "webapp"
    assert row["has_stop"] is True
    assert row["port"] == 59173
    assert row["health_url"] == "http://127.0.0.1:59173/"
    assert row["url"] is None
    assert row["desired"] == "stopped"
    assert row["status"] == "stopped"
    assert row["healthy"] is None
    assert row["restarts"] == 0
    assert row["session_name"].endswith("webapp-server")
    assert row["workspace"] == ws
    assert row["session_created"] is None
    assert row["path"].endswith(os.path.join("projects", "webapp"))


def test_discovery_excludes_project_without_makefile(client, seed_project, isolated_tmux) -> None:
    seed_project("no-makefile")
    r = client.get("/api/servers")
    assert r.json()["servers"] == []


def test_discovery_excludes_makefile_without_start_target(client, seed_project, isolated_tmux) -> None:
    pdir = seed_project("stop-only")
    (pdir / "Makefile").write_text("server-stop:\n\t@true\n")
    r = client.get("/api/servers")
    assert r.json()["servers"] == []


# ─── 2. start ────────────────────────────────────────────────────────────────

def test_start_creates_tmux_session_and_persists_desired(client, server_project, isolated_tmux, monorepo: Path, ws) -> None:
    server_project("webapp")
    r = client.post(f"/api/servers/{ws}/webapp/start")
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["desired"] == "running"
    assert row["status"] == "running"
    assert row["workspace"] == ws
    assert isinstance(row["session_created"], int)
    session_name = row["session_name"]
    assert session_name == isolated_tmux + "webapp-server"

    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode == 0

    assert _desired_state(monorepo)["webapp"]["desired"] == "running"


def test_start_idempotent_when_already_alive(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp")
    first = client.post(f"/api/servers/{ws}/webapp/start").json()
    again = client.post(f"/api/servers/{ws}/webapp/start").json()
    assert again["session_name"] == first["session_name"]
    assert again["status"] == "running"


def test_start_spawns_tmux_with_expected_argv_and_stripped_env(
    client, server_project, isolated_tmux, monorepo: Path, monkeypatch: pytest.MonkeyPatch, ws,
) -> None:
    server_project("webapp")
    monkeypatch.setenv("TMUX", "/tmp/some-socket,1234,0")
    monkeypatch.setenv("TMUX_PANE", "%3")

    with patch("core.routes.servers.subprocess.run", wraps=subprocess.run) as run_mock:
        r = client.post(f"/api/servers/{ws}/webapp/start")
    assert r.status_code == 200, r.text

    new_session_calls = [c for c in run_mock.call_args_list if c.args[0][:2] == ["tmux", "new-session"]]
    assert len(new_session_calls) == 1
    cmd = new_session_calls[0].args[0]
    kwargs = new_session_calls[0].kwargs
    assert cmd[-1] == "make server-start"
    assert cmd[cmd.index("-c") + 1] == str(monorepo / "projects" / "webapp")
    assert "TMUX" not in kwargs["env"]
    assert "TMUX_PANE" not in kwargs["env"]


def test_start_unknown_project_404(client, isolated_tmux, ws) -> None:
    r = client.post(f"/api/servers/{ws}/does-not-exist/start")
    assert r.status_code == 404


def test_start_project_without_server_target_404(client, seed_project, isolated_tmux, ws) -> None:
    seed_project("plain")
    r = client.post(f"/api/servers/{ws}/plain/start")
    assert r.status_code == 404


def test_start_invalid_project_id_400(client, isolated_tmux, ws) -> None:
    r = client.post(f"/api/servers/{ws}/Not Valid!/start")
    assert r.status_code == 400


def test_start_hard_tmux_failure_returns_409(client, server_project, isolated_tmux, monkeypatch: pytest.MonkeyPatch, ws) -> None:
    server_project("webapp")

    class _Failed:
        returncode = 1
        stdout = ""
        stderr = "tmux: some hard failure"

    monkeypatch.setattr("core.routes.servers.subprocess.run", lambda *a, **kw: _Failed())
    r = client.post(f"/api/servers/{ws}/webapp/start")
    assert r.status_code == 409
    assert "hard failure" in r.json()["detail"]


# ─── 3. stop ─────────────────────────────────────────────────────────────────

def test_stop_runs_server_stop_target_and_kills_session(client, server_project, isolated_tmux, monorepo: Path, ws) -> None:
    pdir = server_project("webapp", with_stop=True, stop_recipe="touch stopped.marker")
    client.post(f"/api/servers/{ws}/webapp/start")

    r = client.post(f"/api/servers/{ws}/webapp/stop")
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["desired"] == "stopped"
    assert row["status"] == "stopped"

    assert (pdir / "stopped.marker").is_file()
    assert subprocess.run(["tmux", "has-session", "-t", row["session_name"]],
                          capture_output=True).returncode != 0
    assert _desired_state(monorepo)["webapp"]["desired"] == "stopped"


def test_stop_without_stop_target_just_kills_session(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp", with_stop=False)
    row = client.post(f"/api/servers/{ws}/webapp/start").json()
    assert row["has_stop"] is False

    stopped = client.post(f"/api/servers/{ws}/webapp/stop").json()
    assert stopped["status"] == "stopped"
    assert subprocess.run(["tmux", "has-session", "-t", stopped["session_name"]],
                          capture_output=True).returncode != 0


def test_stop_timeout_returns_504(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp", with_stop=True)
    client.post(f"/api/servers/{ws}/webapp/start")

    real_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if cmd[:1] == ["make"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=20)
        return real_run(cmd, **kwargs)

    with patch("core.routes.servers.subprocess.run", side_effect=fake_run):
        r = client.post(f"/api/servers/{ws}/webapp/stop")
    assert r.status_code == 504


# ─── 4. restart ──────────────────────────────────────────────────────────────

def test_restart_returns_running_state_and_desired(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp", with_stop=True)
    client.post(f"/api/servers/{ws}/webapp/start")

    r = client.post(f"/api/servers/{ws}/webapp/restart")
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["desired"] == "running"
    assert row["status"] == "running"


def test_restart_when_never_started(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp", with_stop=True)
    r = client.post(f"/api/servers/{ws}/webapp/restart")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "running"


# ─── 5. health ───────────────────────────────────────────────────────────────

def test_health_reflected_in_get_servers(client, server_project, isolated_tmux, monkeypatch: pytest.MonkeyPatch, ws) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp", port=8006)

    monkeypatch.setattr(servers_mod, "_check_health", lambda *a, **kw: False)
    client.post(f"/api/servers/{ws}/webapp/start")
    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["healthy"] is False
    assert row["status"] in ("starting", "unhealthy")

    monkeypatch.setattr(servers_mod, "_check_health", lambda *a, **kw: True)
    servers_mod.supervisor_tick(Path(client.app.state.index_cache.root))
    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["healthy"] is True
    assert row["status"] == "running"


def test_check_health_any_http_response_is_healthy() -> None:
    import core.routes.servers as servers_mod

    with patch("core.routes.servers.urllib.request.urlopen") as urlopen:
        urlopen.return_value.__enter__.return_value = object()
        assert servers_mod._check_health("http://127.0.0.1:1/") is True


def test_check_health_http_error_still_counts_as_healthy() -> None:
    import core.routes.servers as servers_mod
    import urllib.error

    def _raise(*_a, **_kw):
        raise urllib.error.HTTPError("http://x/", 500, "boom", {}, None)

    with patch("core.routes.servers.urllib.request.urlopen", side_effect=_raise):
        assert servers_mod._check_health("http://127.0.0.1:1/") is True


def test_check_health_connection_refused_is_unhealthy() -> None:
    import core.routes.servers as servers_mod

    def _raise(*_a, **_kw):
        raise ConnectionRefusedError()

    with patch("core.routes.servers.urllib.request.urlopen", side_effect=_raise):
        assert servers_mod._check_health("http://127.0.0.1:1/") is False


# ─── 5b. external (hand-started) servers ────────────────────────────────────

def test_port_answering_without_session_reports_external_with_url(
    client, server_project, isolated_tmux, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp", port=59173)
    monkeypatch.setattr(servers_mod, "_check_health", lambda *a, **kw: True)

    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["status"] == "external"
    assert row["healthy"] is True
    assert row["url"] == "http://localhost:59173/"


def test_running_managed_server_reports_url(
    client, server_project, isolated_tmux, monkeypatch: pytest.MonkeyPatch, ws,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp", port=59173)
    monkeypatch.setattr(servers_mod, "_check_health", lambda *a, **kw: True)

    row = client.post(f"/api/servers/{ws}/webapp/start").json()
    assert row["status"] == "running"
    assert row["url"] == "http://localhost:59173/"


def test_supervisor_never_restarts_external_server(
    client, server_project, isolated_tmux, monorepo: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp", port=59173)
    # Desired running but no lab session — and the port answers (someone
    # started it by hand). Spawning on the busy port would crash-loop.
    servers_mod.set_desired(monorepo, "webapp", "running")
    monkeypatch.setattr(servers_mod, "_check_health", lambda *a, **kw: True)

    servers_mod.supervisor_tick(monorepo)

    session_name = servers_mod._session_name_for(monorepo, "webapp")
    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode != 0
    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["status"] == "external"
    assert row["restarts"] == 0


# ─── 6. supervisor_tick ──────────────────────────────────────────────────────

def test_supervisor_tick_restarts_dead_session_when_desired_running(
    client, server_project, isolated_tmux, monorepo: Path, ws,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp")
    client.post(f"/api/servers/{ws}/webapp/start")
    session_name = servers_mod._session_name_for(monorepo, "webapp")

    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)
    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode != 0

    servers_mod.supervisor_tick(monorepo)

    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode == 0
    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["restarts"] == 1


def test_supervisor_tick_leaves_desired_stopped_project_alone(
    client, server_project, isolated_tmux, monorepo: Path, ws,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp")
    client.post(f"/api/servers/{ws}/webapp/start")
    client.post(f"/api/servers/{ws}/webapp/stop")
    session_name = servers_mod._session_name_for(monorepo, "webapp")
    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode != 0

    servers_mod.supervisor_tick(monorepo)

    assert subprocess.run(["tmux", "has-session", "-t", session_name],
                          capture_output=True).returncode != 0
    row = next(s for s in client.get("/api/servers").json()["servers"] if s["project_id"] == "webapp")
    assert row["desired"] == "stopped"
    assert row["status"] == "stopped"
    assert row["restarts"] == 0


def test_supervisor_backs_off_after_repeated_restart_failures(
    client, server_project, isolated_tmux, monorepo: Path, monkeypatch: pytest.MonkeyPatch, ws,
) -> None:
    import core.routes.servers as servers_mod

    server_project("webapp")
    client.post(f"/api/servers/{ws}/webapp/start")
    session_name = servers_mod._session_name_for(monorepo, "webapp")
    subprocess.run(["tmux", "kill-session", "-t", session_name], capture_output=True)

    def _boom(*_a, **_kw):
        raise RuntimeError("spawn boom")

    monkeypatch.setattr(servers_mod, "_spawn_server_session", _boom)

    for _ in range(5):
        servers_mod.supervisor_tick(monorepo)

    key = (servers_mod._root_key(monorepo), "webapp")
    with servers_mod._STATUS_LOCK:
        entry = dict(servers_mod._STATUS[key])
    # Backs off after 3 consecutive failed attempts — a 4th/5th tick within
    # the same 60s window must not attempt (and therefore not increment)
    # further.
    assert entry["consecutive_restart_failures"] == 3
    assert entry["restarts"] == 3
    assert entry["alive"] is False


# ─── 7. kill-integration ─────────────────────────────────────────────────────

def test_kill_session_marks_server_desired_stopped(client, server_project, isolated_tmux, monorepo: Path, ws) -> None:
    server_project("webapp")
    row = client.post(f"/api/servers/{ws}/webapp/start").json()
    session_name = row["session_name"]

    # The terminal UI polls /api/term/sessions, which reconciles the runtime
    # registry — a real "server" tab is discovered this way before a user
    # could ever see (and click kill on) it.
    sessions = client.get("/api/term/sessions").json()
    assert any(s["name"] == session_name and s.get("logical_name") == "server" for s in sessions)

    r = client.delete(f"/api/term/sessions/{session_name}")
    assert r.status_code == 200

    assert _desired_state(monorepo)["webapp"]["desired"] == "stopped"


def test_kill_project_sessions_marks_server_desired_stopped(client, server_project, isolated_tmux, monorepo: Path, ws) -> None:
    server_project("webapp")
    client.post(f"/api/servers/{ws}/webapp/start")
    client.get("/api/term/sessions")  # populate the runtime registry

    r = client.delete("/api/term/sessions/project/webapp")
    assert r.status_code == 200

    assert _desired_state(monorepo)["webapp"]["desired"] == "stopped"


# ─── 8. multi-workspace ──────────────────────────────────────────────────────

def test_cross_workspace_discovery_tags_each_row_with_its_workspace(
    client, server_project, second_workspace, isolated_tmux, ws,
) -> None:
    server_project("webapp", port=59174)
    ws2_id, ws2_root = second_workspace
    _write_project_makefile(ws2_root, "otherapp", port=59175)

    r = client.get("/api/servers")
    assert r.status_code == 200, r.text
    servers = r.json()["servers"]
    by_pid = {s["project_id"]: s for s in servers}
    assert set(by_pid) == {"webapp", "otherapp"}
    assert by_pid["webapp"]["workspace"] == ws
    assert by_pid["otherapp"]["workspace"] == ws2_id
    # Sorted by (workspace, project_id).
    assert [s["project_id"] for s in servers] == sorted(
        by_pid, key=lambda p: (by_pid[p]["workspace"], p)
    )


def test_action_routes_to_the_correct_workspace_root(
    client, server_project, second_workspace, isolated_tmux, monorepo: Path, ws,
) -> None:
    """Starting a project in the SECOND workspace must spawn its session
    and persist desired-state under that workspace's own root — never the
    active workspace's, even though the active workspace also has a
    same-named .lab/state directory."""
    server_project("webapp")
    ws2_id, ws2_root = second_workspace
    _write_project_makefile(ws2_root, "otherapp")

    r = client.post(f"/api/servers/{ws2_id}/otherapp/start")
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["workspace"] == ws2_id
    assert row["status"] == "running"

    assert _desired_state(ws2_root)["otherapp"]["desired"] == "running"
    # The active ("main") workspace's own state file is untouched.
    assert _desired_state(monorepo) == {}

    # And the two workspaces' /api/servers rows don't cross-contaminate.
    servers = client.get("/api/servers").json()["servers"]
    other_row = next(s for s in servers if s["project_id"] == "otherapp")
    main_row = next(s for s in servers if s["project_id"] == "webapp")
    assert other_row["workspace"] == ws2_id
    assert other_row["status"] == "running"
    assert main_row["workspace"] == ws
    assert main_row["status"] == "stopped"


def test_start_unknown_workspace_404(client, server_project, isolated_tmux, ws) -> None:
    server_project("webapp")
    r = client.post(f"/api/servers/does-not-exist-workspace/webapp/start")
    assert r.status_code == 404


def test_start_workspace_path_missing_404(
    client, ws, isolated_tmux, tmp_path: Path,
) -> None:
    from lab import paths

    ghost = tmp_path / "ghost-workspace"
    paths.register_workspace(ghost, name="Ghost", active=False)

    r = client.post("/api/servers/ghost/webapp/start")
    assert r.status_code == 404


def test_supervisor_reconciles_every_registered_workspace(
    client, server_project, second_workspace, isolated_tmux, monorepo: Path, ws,
) -> None:
    """The supervisor loop ticks every registered workspace, not just the
    active one — reproduced here by driving supervisor_tick() over
    _known_workspaces() the same way core.routes.servers._supervisor_loop
    does, without spinning up the actual background thread."""
    import core.routes.servers as servers_mod

    server_project("webapp")
    ws2_id, ws2_root = second_workspace
    _write_project_makefile(ws2_root, "otherapp")

    client.post(f"/api/servers/{ws}/webapp/start")
    client.post(f"/api/servers/{ws2_id}/otherapp/start")

    name1 = servers_mod._session_name_for(monorepo, "webapp")
    name2 = servers_mod._session_name_for(ws2_root, "otherapp")
    subprocess.run(["tmux", "kill-session", "-t", name1], capture_output=True)
    subprocess.run(["tmux", "kill-session", "-t", name2], capture_output=True)
    assert subprocess.run(["tmux", "has-session", "-t", name1], capture_output=True).returncode != 0
    assert subprocess.run(["tmux", "has-session", "-t", name2], capture_output=True).returncode != 0

    for w in servers_mod._known_workspaces(monorepo):
        servers_mod.supervisor_tick(w["path"])

    assert subprocess.run(["tmux", "has-session", "-t", name1], capture_output=True).returncode == 0
    assert subprocess.run(["tmux", "has-session", "-t", name2], capture_output=True).returncode == 0


def test_discovery_skips_workspace_fsguard_reports_unavailable(
    client, server_project, second_workspace, isolated_tmux, monkeypatch: pytest.MonkeyPatch, ws,
) -> None:
    """A registered workspace whose volume is stalled (fsguard 503) must not
    blank the whole /api/servers response — mirrors
    core.routes.workspace's list_workspace_projects per-workspace
    degradation test."""
    import core.routes.servers as servers_mod

    server_project("webapp")
    ws2_id, ws2_root = second_workspace
    _write_project_makefile(ws2_root, "otherapp")
    ws2_resolved = ws2_root.resolve()

    real_guarded = servers_mod.fsguard.guarded

    def _fake_guarded(root, fn, *args, **kwargs):
        if Path(root).resolve() == ws2_resolved:
            raise servers_mod.HTTPException(status_code=503, detail="stalled")
        return real_guarded(root, fn, *args, **kwargs)

    monkeypatch.setattr(servers_mod.fsguard, "guarded", _fake_guarded)

    r = client.get("/api/servers")
    assert r.status_code == 200, r.text
    servers = r.json()["servers"]
    assert [s["project_id"] for s in servers] == ["webapp"]
