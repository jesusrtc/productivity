"""Tests for /api/term/* session CRUD.

These endpoint tests run against a per-test fake ``tmux`` binary on PATH. That
keeps the API/storage flow real while avoiding the user's production tmux
server and socket. The WebSocket PTY bridge is covered separately.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import textwrap
import uuid
from pathlib import Path

import pytest


def _write_fake_tmux(bin_dir: Path, state_file: Path) -> Path:
    """Write a fake ``tmux`` binary that persists sessions to a JSON file.

    Shared by every fixture that needs a real tmux binary on PATH without
    touching the user's production tmux server/socket. Session-name
    filtering by naming scheme happens on the Python side (``_tmux_list``
    etc.) — this fake just stores/serves whatever name it's asked for.
    """
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
def isolated_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Unique prefix plus a fake tmux state file per test."""
    prefix = f"lab-test-{uuid.uuid4().hex[:6]}-"
    monkeypatch.setenv("LAB_TMUX_PREFIX", prefix)
    state_file = tmp_path / "fake-tmux-state.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_tmux(bin_dir, state_file)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    yield prefix

    # Tear down any sessions this test left behind.
    proc = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    for name in proc.stdout.splitlines():
        if name.strip().startswith(prefix):
            subprocess.run(["tmux", "kill-session", "-t", name.strip()],
                           capture_output=True, text=True)


@pytest.fixture()
def nomenclature_tmux(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, monorepo: Path):
    """Fake tmux + a registered workspace, for exercising the CURRENT
    (non-``LAB_TMUX_PREFIX``) ``neurona-<workspace>-<project>-<tab>-<hash6>``
    naming scheme end-to-end, instead of the plain legacy shape the other
    tests opt into via ``isolated_prefix``.
    """
    monkeypatch.delenv("LAB_TMUX_PREFIX", raising=False)

    # `monorepo` already points `LAB_HOME` at a per-test tmp dir, so this
    # registry write is fully isolated from the user's real
    # ``~/.lab/workspaces.toml``.
    from lab import paths
    paths.write_workspace_registry({
        "active": "ssd",
        "workspaces": [{"id": "ssd", "name": "productivity", "path": str(monorepo)}],
    })

    import core.routes.term as term_mod
    term_mod._WORKSPACE_LABEL_CACHE.clear()

    state_file = tmp_path / "fake-tmux-state-nomenclature.json"
    bin_dir = tmp_path / "bin-nomenclature"
    bin_dir.mkdir()
    _write_fake_tmux(bin_dir, state_file)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    yield "ssd"

    term_mod._WORKSPACE_LABEL_CACHE.clear()
    proc = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    for name in proc.stdout.splitlines():
        if name.strip().startswith("neurona-") or name.strip().startswith("lab-"):
            subprocess.run(["tmux", "kill-session", "-t", name.strip()],
                           capture_output=True, text=True)


def test_list_sessions_empty(client, isolated_prefix) -> None:
    r = client.get("/api/term/sessions")
    assert r.status_code == 200
    assert r.json() == []


def test_create_claude_session_for_project(client, seed_project, isolated_prefix,
                                            monorepo: Path) -> None:
    seed_project("demo")
    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # Deterministic tmux name: <prefix>demo-claude.
    assert body["name"] == isolated_prefix + "demo-claude"
    assert body["kind"] == "claude"
    assert body["logical_name"] == "claude"
    assert body["auto"] is True
    assert body["claude_session_id"], "first-launch should mint a UUID"
    # tmux actually has it.
    assert subprocess.run(["tmux", "has-session", "-t", body["name"]],
                          capture_output=True).returncode == 0

    # project.json now has a durable sessions[] entry with the id.
    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert pjson["sessions"] == [{
        "name": "claude", "kind": "claude", "agent": "claude",
        "claude_session_id": body["claude_session_id"],
    }]


def test_create_terminal_session(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    r = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == isolated_prefix + "demo-bash"
    assert body["kind"] == "terminal"
    assert body["claude_session_id"] is None


def test_unknown_kind_rejected(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    r = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "banana"})
    assert r.status_code == 400


def test_wheel_binding_passes_mouse_apps_through(monkeypatch) -> None:
    """Wheel-up must reach programs that enabled mouse reporting (claude
    scrolls its own transcript), and fall back to copy-mode LINE scrolling
    (-e, never the -eu page jump) for everything else. The condition must
    not include alternate_on — tmux turns wheel into arrow keys for
    alt-screen panes, which recalls prompt history in agent TUIs."""
    import core.routes.term as term_mod

    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(term_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(term_mod, "_tmux_available", lambda: True)

    term_mod._configure_tmux_wheel_scrolling("sess-x")

    wheel_up = [c for c in calls if "WheelUpPane" in c]
    assert wheel_up == [[
        "tmux", "bind-key", "-T", "root", "WheelUpPane",
        "if-shell", "-F", "#{||:#{pane_in_mode},#{mouse_any_flag}}",
        "send-keys -M", "copy-mode -e",
    ]]
    # Wheel-down stays unbound: tmux forwards it to mouse-enabled panes
    # itself and drops it for plain shells (nothing injected into stdin).
    assert ["tmux", "unbind-key", "-T", "root", "WheelDownPane"] in calls
    assert not any("bind-key" in c and "WheelDownPane" in c for c in calls)
    # Per-session options still applied.
    assert ["tmux", "set-option", "-t", "sess-x", "mouse", "on"] in calls
    assert ["tmux", "set-option", "-t", "sess-x", "alternate-screen", "off"] in calls


def test_agent_argv_copilot_prefers_standalone(monkeypatch) -> None:
    import core.routes.term as term_mod

    def fake_which(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd == "copilot" else None

    monkeypatch.setattr(term_mod.shutil, "which", fake_which)
    assert term_mod._agent_argv("copilot") == ["copilot"]


def test_agent_argv_copilot_rejects_gh_without_standalone_copilot(monkeypatch) -> None:
    import core.routes.term as term_mod

    def fake_which(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd == "gh" else None

    monkeypatch.setattr(term_mod.shutil, "which", fake_which)

    with pytest.raises(term_mod.HTTPException) as exc:
        term_mod._agent_argv("copilot")
    assert exc.value.status_code == 400
    assert "`copilot`" in exc.value.detail


def test_agent_argv_copilot_unavailable(monkeypatch) -> None:
    import core.routes.term as term_mod

    monkeypatch.setattr(term_mod.shutil, "which", lambda cmd: None)
    with pytest.raises(term_mod.HTTPException) as exc:
        term_mod._agent_argv("copilot")
    assert exc.value.status_code == 400


def test_second_claude_gets_suffix(client, seed_project, isolated_prefix) -> None:
    """`+ New` while a default-named session is already live spawns claude-2."""
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    second = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "start_fresh": True,
    }).json()
    assert first["name"].endswith("-claude")
    assert second["name"].endswith("-claude-2")
    # They're independent Claude sessions with different UUIDs.
    assert first["claude_session_id"] != second["claude_session_id"]


def test_reopen_same_name_resumes_saved_uuid(client, seed_project, isolated_prefix,
                                              monorepo: Path) -> None:
    """Kill the tmux session (tab close) then respawn by name → --resume with saved uuid."""
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    original_uuid = first["claude_session_id"]

    # Simulate the X-on-tab flow: kill the tmux session but keep project.json entry.
    r = client.delete(f"/api/term/sessions/{first['name']}")
    assert r.status_code == 200

    # Re-create — should pick up the same UUID via --resume.
    resumed = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    assert resumed["claude_session_id"] == original_uuid
    assert resumed["resumed_from"] == original_uuid
    assert "--resume" in resumed["cmd"]
    assert "--session-id" not in resumed["cmd"]


def test_start_fresh_overrides_saved_uuid(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    client.delete(f"/api/term/sessions/{first['name']}")
    fresh = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "start_fresh": True,
    }).json()
    assert fresh["claude_session_id"] != first["claude_session_id"]
    assert fresh["resumed_from"] is None
    assert "--session-id" in fresh["cmd"]


def test_idempotent_when_already_live(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    again = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    # No new session spawned — same live name returned.
    assert again["name"] == first["name"]
    assert again.get("already_running") is True


def test_list_filters_by_project(client, seed_project, isolated_prefix) -> None:
    seed_project("alpha")
    seed_project("beta")
    client.post("/api/term/sessions", json={"project_id": "alpha", "kind": "terminal"})
    client.post("/api/term/sessions", json={"project_id": "beta", "kind": "terminal"})

    r_all = client.get("/api/term/sessions")
    assert len(r_all.json()) == 2
    r_alpha = client.get("/api/term/sessions?project_id=alpha").json()
    assert len(r_alpha) == 1
    assert r_alpha[0]["project_id"] == "alpha"


def test_projects_with_sessions(client, seed_project, isolated_prefix) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/term/projects-with-sessions")
    assert r.json() == []

    client.post("/api/term/sessions", json={"project_id": "alpha", "kind": "terminal"})
    client.post("/api/term/sessions", json={"project_id": "beta", "kind": "terminal"})
    client.post("/api/term/sessions", json={"project_id": "beta", "kind": "terminal"})

    ids = client.get("/api/term/projects-with-sessions").json()
    assert sorted(ids) == ["alpha", "beta"]


def test_kill_project_sessions_removes_all(client, seed_project, isolated_prefix,
                                             monorepo: Path) -> None:
    seed_project("demo")
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"})

    r = client.delete("/api/term/sessions/project/demo")
    assert r.status_code == 200
    assert len(r.json()["killed"]) == 2

    # No live sessions remain.
    assert client.get("/api/term/sessions?project_id=demo").json() == []
    # But project.json still has the saved entries (not purged).
    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert len(pjson["sessions"]) == 2


def test_kill_project_sessions_purge_clears_saved(client, seed_project, isolated_prefix,
                                                    monorepo: Path) -> None:
    seed_project("demo")
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})

    r = client.delete("/api/term/sessions/project/demo?purge=true")
    assert r.status_code == 200
    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert pjson["sessions"] == []


def test_classify_pane_subagent_is_working(monkeypatch) -> None:
    """Regression: Claude spawned a subagent (Task tool research loop) and the
    `esc to interrupt` hint wrapped off the capture, but other signals —
    `…(1m 36s`, `thought for 27s`, `↓ 343 tokens` — are still present.
    The classifier must see the session as WORKING."""
    import core.routes.term as term_mod
    # Stub tmux + clear the TTL cache.
    import subprocess as sp

    pane_text = (
        "⏺ Bash(rm /tmp/foo)\n"
        "  └ Done\n"
        "\n"
        "* Researching inResponse cases vs incidents… (1m 36s · ↓ 343 tokens · thought for 27\n"
        "   └ ✓ Draft initial problem statement doc\n"
        "   ■ Research inResponse cases vs incidents\n"
        "   □ Draft unification proposal section\n"
        "\n"
        "> \n"
    )

    class FakeRun:
        returncode = 0
        stderr = ""
        stdout = pane_text

    monkeypatch.setattr(sp, "run", lambda *a, **kw: FakeRun())
    monkeypatch.setattr(term_mod, "_tmux_available", lambda: True)
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})
    assert term_mod._classify_pane("lab-xxx-claude") == "working"


def test_classify_pane_idle_prompt(monkeypatch) -> None:
    """Opposite: a freshly-idle Claude showing just its prompt — no timer,
    no token count, no interrupt hint — should classify IDLE."""
    import core.routes.term as term_mod
    import subprocess as sp

    pane_text = (
        "⏺ Done editing README.md\n"
        "\n"
        "> \n"
    )

    class FakeRun:
        returncode = 0
        stderr = ""
        stdout = pane_text

    monkeypatch.setattr(sp, "run", lambda *a, **kw: FakeRun())
    monkeypatch.setattr(term_mod, "_tmux_available", lambda: True)
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})
    assert term_mod._classify_pane("lab-xxx-claude") == "idle"


def test_session_status_working_vs_idle(client, seed_project, isolated_prefix,
                                          monkeypatch) -> None:
    """`/api/term/sessions/status`: claude pane containing 'esc to interrupt'
    is 'working'; otherwise 'idle'. Terminal sessions are 'n/a'."""
    seed_project("demo")
    # Start one claude + one terminal. Pane capture will be stubbed.
    c = client.post("/api/term/sessions",
                    json={"project_id": "demo", "kind": "claude"}).json()
    t = client.post("/api/term/sessions",
                    json={"project_id": "demo", "kind": "terminal"}).json()

    # Stub tmux capture-pane: claude pane shows "esc to interrupt" → working.
    import subprocess as sp
    real_run = sp.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and cmd[:2] == ["tmux", "capture-pane"]:
            target_idx = cmd.index("-pt") + 1 if "-pt" in cmd else -1
            target = cmd[target_idx] if target_idx > 0 else ""
            class R:
                returncode = 0
                stderr = ""
            if target.endswith("-claude"):
                R.stdout = "⏺ Burrowing… (24s · esc to interrupt)\n"
            else:
                R.stdout = "$ \n"
            return R()
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(sp, "run", fake_run)
    # Stub cache too — it's time-based; wipe between calls.
    import core.routes.term as term_mod
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})

    rows = client.get("/api/term/sessions/status?project_id=demo").json()
    by_name = {r["name"]: r for r in rows}
    assert by_name[c["name"]]["status"] == "working"
    assert by_name[t["name"]]["status"] == "n/a"


def test_projects_attention_needs_idle_claude(client, seed_project, isolated_prefix,
                                                 monkeypatch) -> None:
    """A project is in the attention list only when at least one claude is
    live AND none of them is working."""
    seed_project("demo")
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()

    import subprocess as sp
    real_run = sp.run
    pane_text = {"value": "esc to interrupt"}  # start working

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and cmd[:2] == ["tmux", "capture-pane"]:
            class R: returncode = 0; stderr = ""; stdout = pane_text["value"] + "\n"
            return R()
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(sp, "run", fake_run)
    import core.routes.term as term_mod
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})
    monkeypatch.setattr(term_mod, "_PROJECTS_ATTENTION_CACHE", None)

    # Working → not in attention list.
    assert client.get("/api/term/projects-attention").json() == []

    # Idle → in attention list.
    pane_text["value"] = "some prompt:"
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})  # bust the 1.5s cache
    monkeypatch.setattr(term_mod, "_PROJECTS_ATTENTION_CACHE", None)
    assert client.get("/api/term/projects-attention").json() == ["demo"]

    # Held → excluded from attention even when Claude is idle. A snoozed
    # project is *expected* to be idle; pulsing it would defeat the point.
    import json as _json
    from lab import paths as _paths
    root = client.app.state.index_cache.root
    pjson = _paths.project_file(root, "demo")
    data = _json.loads(pjson.read_text())
    data["hold"] = {"until": "2099-01-01T00:00:00+00:00"}
    pjson.write_text(_json.dumps(data))
    client.app.state.index_cache.rebuild()
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})
    monkeypatch.setattr(term_mod, "_PROJECTS_ATTENTION_CACHE", None)
    assert client.get("/api/term/projects-attention").json() == []

    # Hold in the past → attention returns (ready-for-review still pings).
    data["hold"] = {"until": "2020-01-01T00:00:00+00:00"}
    pjson.write_text(_json.dumps(data))
    client.app.state.index_cache.rebuild()
    monkeypatch.setattr(term_mod, "_STATUS_CACHE", {})
    monkeypatch.setattr(term_mod, "_PROJECTS_ATTENTION_CACHE", None)
    assert client.get("/api/term/projects-attention").json() == ["demo"]


def test_session_status_n_a_for_non_claude(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    client.post("/api/term/sessions",
                json={"project_id": "demo", "kind": "terminal"}).json()
    rows = client.get("/api/term/sessions/status?project_id=demo").json()
    assert [r["status"] for r in rows] == ["n/a"]


def test_session_order_reorder_saved_and_affect_live_list(client, seed_project,
                                                             isolated_prefix,
                                                             monorepo) -> None:
    """POST /api/term/sessions/order reorders project.json.sessions[]; the
    live GET uses that order too so the UI's pill row reflects it."""
    import json as _json
    seed_project("demo")
    # Spawn three sessions.
    a = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()
    b = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "start_fresh": True,
    }).json()
    c = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"}).json()
    names = [a["logical_name"], b["logical_name"], c["logical_name"]]
    assert sorted(names) == sorted(["claude", "claude-2", "bash"])

    # Reorder: bash, claude-2, claude.
    new_order = ["bash", "claude-2", "claude"]
    r = client.post("/api/term/sessions/order",
                     json={"project_id": "demo", "order": new_order})
    assert r.status_code == 200, r.text
    assert r.json()["order"] == new_order

    # Saved order updated.
    pjson = _json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert [s["name"] for s in pjson["sessions"]] == new_order

    # Live list reflects saved order.
    live = client.get("/api/term/sessions?project_id=demo").json()
    assert [s["logical_name"] for s in live] == new_order


def test_session_order_ignores_unknown_names(client, seed_project, isolated_prefix) -> None:
    """Names not in project.json.sessions[] are silently dropped from the
    order update (they have no saved entry to move)."""
    seed_project("demo")
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})
    r = client.post("/api/term/sessions/order",
                    json={"project_id": "demo", "order": ["mystery", "claude"]})
    assert r.status_code == 200
    assert r.json()["order"] == ["claude"]


def test_session_order_404_for_missing_project(client, isolated_prefix) -> None:
    r = client.post("/api/term/sessions/order",
                    json={"project_id": "does-not-exist", "order": []})
    assert r.status_code == 404


def test_saved_sessions_endpoint(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})
    client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"})

    saved = client.get("/api/term/sessions/saved?project_id=demo").json()
    assert len(saved) == 2
    kinds = sorted(s["kind"] for s in saved)
    assert kinds == ["claude", "terminal"]
    claude_entry = next(s for s in saved if s["kind"] == "claude")
    assert "claude_session_id" in claude_entry


def test_delete_rejects_non_prefix(client, isolated_prefix) -> None:
    r = client.delete("/api/term/sessions/some-other-session")
    assert r.status_code == 400


def test_delete_single_session_does_not_purge_project_json(client, seed_project,
                                                            isolated_prefix, monorepo: Path) -> None:
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()

    client.delete(f"/api/term/sessions/{first['name']}")

    # tmux session gone, runtime meta gone…
    assert subprocess.run(["tmux", "has-session", "-t", first["name"]],
                          capture_output=True).returncode != 0
    # …but the project.json entry with the claude UUID persists so we can --resume later.
    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert pjson["sessions"][0]["claude_session_id"] == first["claude_session_id"]


def test_tab_close_then_reopen_restores_all_sessions(client, seed_project,
                                                       isolated_prefix, monorepo: Path) -> None:
    """Tab close (kill-all) → re-post each saved session by name → --resume.

    This is the loop the frontend runs when you reopen a project tab:
    GET /sessions/saved, then for every entry POST again with the same name
    so Claude resumes with its saved UUID.
    """
    seed_project("demo")
    main = client.post("/api/term/sessions",
                       json={"project_id": "demo", "kind": "claude"}).json()
    extra = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "start_fresh": True,
    }).json()
    main_id, extra_id = main["claude_session_id"], extra["claude_session_id"]
    assert main["logical_name"] == "claude"
    assert extra["logical_name"] == "claude-2"

    # User closes the tab → every live session dies. Saved metadata stays.
    client.delete("/api/term/sessions/project/demo")
    saved = client.get("/api/term/sessions/saved?project_id=demo").json()
    assert len(saved) == 2
    names = {s["name"] for s in saved}
    assert names == {"claude", "claude-2"}

    # User reopens the tab. Frontend POSTs each saved entry by name.
    for s in saved:
        r = client.post("/api/term/sessions", json={
            "project_id": "demo", "kind": s["kind"], "name": s["name"], "auto": True,
        })
        assert r.status_code == 200, r.text

    # Both sessions are live again and retained their UUIDs via --resume.
    live = client.get("/api/term/sessions?project_id=demo").json()
    assert len(live) == 2
    by_logical = {s["logical_name"]: s for s in live}
    assert by_logical["claude"]["claude_session_id"] == main_id
    assert by_logical["claude-2"]["claude_session_id"] == extra_id
    assert "--resume" in by_logical["claude"]["cmd"]
    assert "--resume" in by_logical["claude-2"]["cmd"]


def test_cerebro_pseudo_project_lifecycle(client, isolated_prefix,
                                             monorepo: Path) -> None:
    """__cerebro__ is a pseudo-project: cwd = content/, storage = hidden
    file. Behaves like a real project for session create + resume."""
    r = client.post("/api/term/sessions", json={
        "project_id": "__cerebro__", "kind": "claude",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == isolated_prefix + "__cerebro__-claude"
    assert body["cwd"].endswith("/content")
    assert body["claude_session_id"], "cerebro sessions still mint a UUID"

    # The saved sessions go into content/.cerebro-project.json.
    meta_path = monorepo / "content" / ".cerebro-project.json"
    assert meta_path.is_file()
    data = json.loads(meta_path.read_text())
    assert data["sessions"][0]["name"] == "claude"
    assert data["sessions"][0]["claude_session_id"] == body["claude_session_id"]

    # Close + reopen: --resume is used.
    client.delete(f"/api/term/sessions/{body['name']}")
    resumed = client.post("/api/term/sessions", json={
        "project_id": "__cerebro__", "kind": "claude",
    }).json()
    assert resumed["resumed_from"] == body["claude_session_id"]
    assert "--resume" in resumed["cmd"]


def test_logs_pseudo_project_uses_own_saved_state(monorepo: Path) -> None:
    """The Logs tab owns terminal metadata separate from other tabs."""
    from core.routes import term as term_mod
    from lab import paths

    paths.logs_dir(monorepo).mkdir(parents=True, exist_ok=True)

    assert term_mod.LOGS_PROJECT_ID == "__logs__"
    assert term_mod._project_json(monorepo, term_mod.LOGS_PROJECT_ID) == (
        monorepo / "content" / ".logs-project.json"
    )
    assert term_mod._project_cwd(monorepo, term_mod.LOGS_PROJECT_ID) == (
        paths.logs_dir(monorepo)
    ).resolve()
    assert term_mod._load_project(monorepo, term_mod.LOGS_PROJECT_ID) == {}
    assert term_mod.LOGS_PROJECT_ID in term_mod._known_project_ids(monorepo)

    term_mod._upsert_project_session(
        monorepo,
        term_mod.LOGS_PROJECT_ID,
        {"name": "bash", "kind": "terminal"},
    )

    meta_path = monorepo / "content" / ".logs-project.json"
    assert meta_path.is_file()
    data = json.loads(meta_path.read_text())
    assert data["sessions"] == [{"name": "bash", "kind": "terminal"}]
    assert term_mod._get_project_sessions(monorepo, term_mod.LOGS_PROJECT_ID) == [
        {"name": "bash", "kind": "terminal"}
    ]


def test_workspace_pseudo_project_runs_at_root_and_persists_own_sessions(
    client, isolated_prefix, monorepo: Path,
) -> None:
    from core.routes import term as term_mod

    r = client.post("/api/term/sessions", json={
        "project_id": "__workspace__",
        "kind": "terminal",
    })

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == isolated_prefix + "__workspace__-bash"
    assert body["cwd"] == str(monorepo.resolve())
    assert term_mod._project_json(monorepo, term_mod.WORKSPACE_PROJECT_ID) == (
        monorepo / "content" / ".workspace-project.json"
    )
    assert term_mod.WORKSPACE_PROJECT_ID in term_mod._known_project_ids(monorepo)
    saved = json.loads(
        (monorepo / "content" / ".workspace-project.json").read_text()
    )
    assert saved["sessions"] == [{"name": "bash", "kind": "terminal"}]


def test_create_session_enforces_workspace_supported_agents(
    client,
    seed_project,
    isolated_prefix,
    monorepo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.routes import term as term_mod

    seed_project("demo")
    (monorepo / "workspace.json").write_text(json.dumps({
        "version": 1,
        "agents": {"supported": ["codex"], "default": "codex"},
    }))
    monkeypatch.setattr(term_mod, "_agent_argv", lambda agent: [agent])

    disabled = client.post("/api/term/sessions", json={
        "project_id": "demo",
        "kind": "claude",
        "agent": "claude",
    })
    assert disabled.status_code == 400
    assert "not enabled" in disabled.json()["detail"]

    defaulted = client.post("/api/term/sessions", json={
        "project_id": "demo",
        "kind": "claude",
    })
    assert defaulted.status_code == 200, defaulted.text
    assert defaulted.json()["agent"] == "codex"
    assert defaulted.json()["logical_name"] == "codex"


def test_self_pseudo_project_uses_framework_root_for_terminal(monorepo: Path, tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    from core.routes import term as term_mod
    from lab import paths

    framework = tmp_path / "framework"
    (framework / "content").mkdir(parents=True)
    monkeypatch.setattr(paths, "find_framework_root", lambda: framework)

    assert term_mod._project_json(monorepo, term_mod.SELF_PROJECT_ID) == (
        framework / "content" / ".self-project.json"
    )
    assert term_mod._project_cwd(monorepo, term_mod.SELF_PROJECT_ID) == framework.resolve()


def test_delete_with_purge_clears_project_json_entry(client, seed_project,
                                                      isolated_prefix, monorepo: Path) -> None:
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"}).json()

    client.delete(f"/api/term/sessions/{first['name']}?purge=true")
    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert pjson["sessions"] == []


def test_delete_with_purge_prevents_later_resume(client, seed_project,
                                                  isolated_prefix) -> None:
    seed_project("demo")
    r = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})
    assert r.status_code == 200, r.text
    first = r.json()

    client.delete(f"/api/term/sessions/{first['name']}?purge=true")
    r = client.post("/api/term/sessions", json={
        "project_id": "demo",
        "kind": "claude",
    })
    assert r.status_code == 200, r.text
    recreated = r.json()

    assert recreated["claude_session_id"] != first["claude_session_id"]
    assert recreated["resumed_from"] is None
    assert "--session-id" in recreated["cmd"]
    assert "--resume" not in recreated["cmd"]


def test_wiped_sessions_json_is_rebuilt_from_live_tmux(client, seed_project,
                                                        isolated_prefix,
                                                        monorepo: Path) -> None:
    """Regression (2026-06-10): .sessions.json got wiped while sessions were
    live, orphaning every tab (project_id=None → grey tabs, empty
    projects-with-sessions). The registry must self-heal from the tmux
    session names + the durable project.json entries."""
    seed_project("demo")
    created = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude",
    }).json()

    from lab import paths
    sessions_path = paths.sessions_file(monorepo)
    # Simulate the wipe.
    sessions_path.write_text("{}\n")

    rows = client.get("/api/term/sessions?project_id=demo").json()
    assert [r["name"] for r in rows] == [created["name"]]
    assert rows[0]["project_id"] == "demo"
    assert rows[0]["logical_name"] == "claude"
    assert rows[0]["kind"] == "claude"
    assert rows[0]["agent"] == "claude"
    # claude_session_id recovered from project.json so --resume keeps working.
    assert rows[0]["claude_session_id"] == created["claude_session_id"]

    assert client.get("/api/term/projects-with-sessions").json() == ["demo"]
    # And the rebuilt entry is persisted.
    meta = json.loads(sessions_path.read_text())
    assert meta[created["name"]]["project_id"] == "demo"


def test_failed_tmux_listing_does_not_prune_registry(client, seed_project,
                                                      isolated_prefix,
                                                      monorepo: Path,
                                                      monkeypatch) -> None:
    """Regression (2026-06-10): a transient `tmux list-sessions` failure
    must read as *unknown*, not as "no sessions" — pruning on it destroyed
    the whole registry."""
    from core.routes import term as term_route

    seed_project("demo")
    created = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude",
    }).json()

    monkeypatch.setattr(term_route, "_tmux_list", lambda prefix: None)
    assert client.get("/api/term/sessions").json() == []
    assert client.get("/api/term/projects-with-sessions").json() == []
    assert client.get("/api/term/sessions/status").json() == []
    assert client.get("/api/term/projects-attention").json() == []

    from lab import paths
    meta = json.loads(paths.sessions_file(monorepo).read_text())
    assert created["name"] in meta, "failed listing must not prune the registry"


def test_session_metadata_label_is_persisted_and_returned(client, seed_project,
                                                          isolated_prefix,
                                                          monorepo: Path) -> None:
    seed_project("demo")
    created = client.post("/api/term/sessions", json={
        "project_id": "demo",
        "kind": "claude",
        "agent": "codex",
    }).json()

    r = client.patch("/api/term/sessions/metadata", json={
        "project_id": "demo",
        "name": created["logical_name"],
        "label": "review auth PR",
        "summary": "Checking failing auth tests",
    })
    assert r.status_code == 200, r.text

    rows = client.get("/api/term/sessions?project_id=demo").json()
    assert rows[0]["label"] == "review auth PR"
    assert rows[0]["summary"] == "Checking failing auth tests"

    pjson = json.loads((monorepo / "projects" / "demo" / "project.json").read_text())
    assert pjson["sessions"][0]["label"] == "review auth PR"
    assert pjson["sessions"][0]["summary"] == "Checking failing auth tests"


def test_paste_image_saves_under_project_and_returns_relative_path(client, seed_project,
                                                                   monorepo: Path) -> None:
    seed_project("demo")
    png = b"\x89PNG\r\n\x1a\n"
    data = "data:image/png;base64," + base64.b64encode(png).decode("ascii")

    r = client.post("/api/term/paste-image", json={
        "project_id": "demo",
        "mime": "image/png",
        "name": "clipboard.png",
        "data": data,
    })
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["path"].startswith(".lab/terminal-pastes/")
    assert body["path"].endswith(".png")
    saved = monorepo / "projects" / "demo" / body["path"]
    assert saved.read_bytes() == png
    assert body["mime"] == "image/png"
    assert body["bytes"] == len(png)


def test_paste_image_rejects_unsupported_mime(client, seed_project) -> None:
    seed_project("demo")
    r = client.post("/api/term/paste-image", json={
        "project_id": "demo",
        "mime": "text/plain",
        "data": base64.b64encode(b"not-image").decode("ascii"),
    })
    assert r.status_code == 400


# ─── Naming scheme: neurona-<workspace>-<project>-<tab>-<hash6> ────────────
#
# These tests exercise the CURRENT naming scheme (not the legacy
# LAB_TMUX_PREFIX-based one every test above opts into), covering: workspace
# id resolution from the registry, deterministic hashed-name generation,
# parsing (with hyphenated project ids/tabs), legacy-scheme adoption, and
# the attach-not-duplicate create_session path.


def _is_hex6(s: str) -> bool:
    return len(s) == 6 and all(c in "0123456789abcdef" for c in s)


def test_resolve_workspace_label_prefers_registry_id(monorepo: Path) -> None:
    import core.routes.term as term_mod
    from lab import paths

    term_mod._WORKSPACE_LABEL_CACHE.clear()
    paths.write_workspace_registry({
        "active": "ssd",
        "workspaces": [{"id": "ssd", "name": "productivity", "path": str(monorepo)}],
    })
    assert term_mod._resolve_workspace_label(monorepo) == "ssd"


def test_resolve_workspace_label_falls_back_to_lab_toml_name(monorepo: Path) -> None:
    import core.routes.term as term_mod

    term_mod._WORKSPACE_LABEL_CACHE.clear()
    (monorepo / "lab.toml").write_text('[workspace]\nname = "my-workspace"\n')
    assert term_mod._resolve_workspace_label(monorepo) == "my-workspace"


def test_resolve_workspace_label_falls_back_to_dirname(monorepo: Path) -> None:
    import core.routes.term as term_mod

    term_mod._WORKSPACE_LABEL_CACHE.clear()
    assert term_mod._resolve_workspace_label(monorepo) == term_mod._sanitize(monorepo.name)


def test_resolve_workspace_label_rereads_registry_after_rename(monorepo: Path) -> None:
    """A concurrently-running rename (e.g. `lab workspace` re-id, or moving
    the workspace to a new registry entry) must be picked up without a
    server restart — the id must never be hardcoded or memoized forever."""
    import core.routes.term as term_mod
    from lab import paths

    term_mod._WORKSPACE_LABEL_CACHE.clear()
    paths.write_workspace_registry({
        "active": "productivity",
        "workspaces": [{"id": "productivity", "name": "productivity", "path": str(monorepo)}],
    })
    assert term_mod._resolve_workspace_label(monorepo) == "productivity"

    paths.write_workspace_registry({
        "active": "ssd",
        "workspaces": [{"id": "ssd", "name": "productivity", "path": str(monorepo)}],
    })
    term_mod._WORKSPACE_LABEL_CACHE.clear()  # simulate TTL expiry
    assert term_mod._resolve_workspace_label(monorepo) == "ssd"


def test_tmux_name_for_new_scheme_is_deterministic_and_hashed(nomenclature_tmux, monorepo: Path) -> None:
    import core.routes.term as term_mod

    name = term_mod._tmux_name_for("my-project", "codex-tab", monorepo)
    assert name.startswith("neurona-ssd-my-project-codex-tab-")
    suffix = name.rsplit("-", 1)[-1]
    assert _is_hex6(suffix)
    # Deterministic: same workspace+project+tab → same name, every time.
    assert term_mod._tmux_name_for("my-project", "codex-tab", monorepo) == name
    # A different tab hashes differently.
    other = term_mod._tmux_name_for("my-project", "other-tab", monorepo)
    assert other != name


def test_parse_tmux_name_new_scheme_with_hyphenated_project_and_tab(
    nomenclature_tmux, seed_project, monorepo: Path,
) -> None:
    seed_project("my-project")
    import core.routes.term as term_mod

    name = term_mod._tmux_name_for("my-project", "review-pr-42", monorepo)
    assert term_mod._parse_tmux_name(monorepo, name) == ("my-project", "review-pr-42")


def test_parse_tmux_name_tolerates_missing_hash_suffix(
    nomenclature_tmux, seed_project, monorepo: Path,
) -> None:
    """A session hand-created outside the server (CLI/agent following the
    ``<workspace>-<project>-<tab>`` convention but not bothering to compute
    the hash marker) must still be discovered."""
    seed_project("demo")
    import core.routes.term as term_mod

    name = "neurona-ssd-demo-mytab"
    assert term_mod._parse_tmux_name(monorepo, name) == ("demo", "mytab")


def test_parse_tmux_name_does_not_strip_unverified_hash_looking_suffix(
    nomenclature_tmux, seed_project, monorepo: Path,
) -> None:
    """A tab name that just happens to end in 6 hex characters must not be
    mistaken for a hash and chopped off — only a VERIFIED hash is stripped."""
    seed_project("demo")
    import core.routes.term as term_mod

    name = "neurona-ssd-demo-my-tab-abcdef"  # "abcdef" looks hex but is not the real hash
    assert term_mod._parse_tmux_name(monorepo, name) == ("demo", "my-tab-abcdef")


def test_parse_tmux_name_adopts_namespaced_legacy_scheme(
    nomenclature_tmux, seed_project, monorepo: Path,
) -> None:
    seed_project("demo")
    import core.routes.term as term_mod

    legacy_prefix = term_mod._legacy_namespaced_prefix(monorepo)
    name = f"{legacy_prefix}demo-claude"
    assert term_mod._parse_tmux_name(monorepo, name) == ("demo", "claude")


def test_parse_tmux_name_adopts_bare_legacy_scheme(
    nomenclature_tmux, seed_project, monorepo: Path,
) -> None:
    seed_project("demo")
    import core.routes.term as term_mod

    assert term_mod._parse_tmux_name(monorepo, "lab-demo-bash") == ("demo", "bash")


def test_pick_unique_logical_name_only_uniquifies_against_different_tabs() -> None:
    import core.routes.term as term_mod

    # Not taken at all → returned unchanged.
    assert term_mod._pick_unique_logical_name("claude", set()) == "claude"
    # Taken (by what the caller already established is a DIFFERENT tab) →
    # bump to the next free suffix.
    assert term_mod._pick_unique_logical_name("claude", {"claude"}) == "claude-2"
    assert term_mod._pick_unique_logical_name("claude", {"claude", "claude-2"}) == "claude-3"


def test_create_and_list_use_new_naming_scheme_and_expose_attach_command(
    nomenclature_tmux, seed_project, client, monorepo: Path,
) -> None:
    seed_project("demo")
    created = client.post("/api/term/sessions",
                          json={"project_id": "demo", "kind": "terminal"}).json()
    assert created["name"].startswith("neurona-ssd-demo-bash-")
    assert created["attach_command"] == "tmux attach -t '{}'".format(created["name"])

    rows = client.get("/api/term/sessions?project_id=demo").json()
    assert len(rows) == 1
    assert rows[0]["name"] == created["name"]
    assert rows[0]["attach_command"] == created["attach_command"]


def test_new_scheme_idempotent_when_already_live(nomenclature_tmux, seed_project, client) -> None:
    seed_project("demo")
    first = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"}).json()
    again = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "terminal"}).json()
    assert again["name"] == first["name"]
    assert again["already_running"] is True


def test_list_sessions_adopts_legacy_named_live_session(
    nomenclature_tmux, seed_project, client, monorepo: Path,
) -> None:
    """A session already live under the OLD naming scheme (spawned by a
    previous server build) must still show up in the project's session
    list, not just vanish because its name doesn't match the current
    scheme."""
    seed_project("demo")
    import core.routes.term as term_mod

    legacy_prefix = term_mod._legacy_namespaced_prefix(monorepo)
    legacy_name = f"{legacy_prefix}demo-claude"
    subprocess.run(["tmux", "new-session", "-d", "-s", legacy_name, "-c", str(monorepo), "bash"],
                  check=True)

    rows = client.get("/api/term/sessions?project_id=demo").json()
    assert [r["name"] for r in rows] == [legacy_name]
    assert rows[0]["project_id"] == "demo"
    assert rows[0]["logical_name"] == "claude"
    assert rows[0]["attach_command"] == f"tmux attach -t '{legacy_name}'"


def test_create_session_attaches_to_legacy_named_live_session_instead_of_duplicating(
    nomenclature_tmux, seed_project, client, monorepo: Path,
) -> None:
    """The repro for the 'creates a new session for some reason' bug: a
    session for this exact project+tab is already live, just under an
    OLDER naming scheme (e.g. left over from before this naming change, or
    from a server instance that landed on a different tmux socket).
    Reopening that project+tab must attach to the live session, not spawn a
    second, differently-named one."""
    seed_project("demo")
    import core.routes.term as term_mod

    legacy_prefix = term_mod._legacy_namespaced_prefix(monorepo)
    legacy_name = f"{legacy_prefix}demo-codex"
    subprocess.run(["tmux", "new-session", "-d", "-s", legacy_name, "-c", str(monorepo), "bash"],
                  check=True)

    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "agent": "codex", "name": "codex",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == legacy_name
    assert body["already_running"] is True
    assert body["attach_command"] == f"tmux attach -t '{legacy_name}'"

    # Only one live tmux session for this project — no duplicate spawned.
    rows = client.get("/api/term/sessions?project_id=demo").json()
    assert len(rows) == 1
    assert rows[0]["name"] == legacy_name


def test_tmux_child_env_strips_tmux_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.routes.term as term_mod

    monkeypatch.setenv("TMUX", "/tmp/some-socket,1234,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    monkeypatch.setenv("SOME_OTHER_VAR", "keep-me")
    env = term_mod._tmux_child_env()
    assert "TMUX" not in env
    assert "TMUX_PANE" not in env
    assert env.get("SOME_OTHER_VAR") == "keep-me"


def test_tmux_has_session_strips_tmux_env_from_child(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: if the lab server itself is launched from inside a tmux
    session, every `tmux` subprocess call must still land on the DEFAULT
    socket — not the containing session's socket that `$TMUX` points at.
    Guard the actual call site, not just the helper, so a future edit that
    forgets `env=_tmux_child_env()` fails loudly here instead of silently
    reintroducing the split-server bug."""
    import core.routes.term as term_mod
    import subprocess as sp

    monkeypatch.setenv("TMUX", "/tmp/whatever-socket,1,0")
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = kwargs.get("env")
        class R:
            returncode = 1
            stdout = ""
            stderr = "no server running"
        return R()

    monkeypatch.setattr(sp, "run", fake_run)
    monkeypatch.setattr(term_mod, "_tmux_available", lambda: True)
    term_mod._tmux_has_session("whatever")
    assert captured["env"] is not None
    assert "TMUX" not in captured["env"]


# ─── multi-workspace terminal listing / killing ─────────────────────────────
#
# core.routes.servers manages dev servers across every registered
# workspace, not just the active one, and the cross-workspace terminals
# dashboard needs the matching view here: GET /api/term/sessions (unscoped)
# spans every registered workspace tagging each row with `workspace`, and
# the kill endpoints accept/target sessions from a non-active workspace.
# These tests use the CURRENT naming scheme (LAB_TMUX_PREFIX unset) since
# the legacy flat scheme carries no workspace identity to resolve.

@pytest.fixture()
def second_workspace_tmux(nomenclature_tmux, tmp_path: Path):
    """A second registered workspace ("other"), alongside the ``monorepo``
    ("ssd") ``nomenclature_tmux`` already registers. Returns its root."""
    from lab import paths

    other_root = tmp_path / "other-workspace"
    (other_root / "projects" / "demo2").mkdir(parents=True)
    (other_root / "content").mkdir(parents=True, exist_ok=True)

    data = paths.read_workspace_registry()
    rows = list(data.get("workspaces") or [])
    rows.append({"id": "other", "name": "other", "path": str(other_root)})
    paths.write_workspace_registry({"active": data.get("active"), "workspaces": rows})

    import core.routes.term as term_mod
    term_mod._WORKSPACE_LABEL_CACHE.clear()
    yield other_root
    term_mod._WORKSPACE_LABEL_CACHE.clear()


def _spawn_and_adopt(root: Path, project_id: str, tab: str) -> str:
    """Spawn a bare tmux session named for ``(root, project_id, tab)`` and
    reconcile THAT workspace's own runtime registry against it — mirrors
    how a session created outside this server process (or in a workspace
    that isn't currently active) gets adopted."""
    import core.routes.term as term_mod

    name = term_mod._tmux_name_for(project_id, tab, root)
    subprocess.run(["tmux", "new-session", "-d", "-s", name, "-c", str(root), "bash"], check=True)
    term_mod._sync_meta(root, term_mod._tmux_list(term_mod._tmux_discovery_prefixes(root)))
    return name


def test_list_sessions_unscoped_spans_all_registered_workspaces(
    client, seed_project, second_workspace_tmux,
) -> None:
    seed_project("demo")
    other_root = second_workspace_tmux

    mine = client.post("/api/term/sessions",
                       json={"project_id": "demo", "kind": "terminal"}).json()
    other_name = _spawn_and_adopt(other_root, "demo2", "bash")

    rows = client.get("/api/term/sessions").json()
    by_name = {r["name"]: r for r in rows}
    assert by_name[mine["name"]]["workspace"] == "ssd"
    assert by_name[other_name]["workspace"] == "other"


def test_kill_session_resolves_non_active_workspace(
    client, seed_project, second_workspace_tmux,
) -> None:
    """Killing a session named for a workspace OTHER than the active one
    must still validate (not 400) and clean up THAT workspace's own
    runtime registry, not the active workspace's."""
    other_root = second_workspace_tmux
    other_name = _spawn_and_adopt(other_root, "demo2", "bash")

    r = client.delete(f"/api/term/sessions/{other_name}")
    assert r.status_code == 200, r.text
    assert subprocess.run(["tmux", "has-session", "-t", other_name],
                          capture_output=True).returncode != 0

    import core.routes.term as term_mod
    other_meta = json.loads(term_mod._sessions_file(other_root).read_text())
    assert other_name not in other_meta


def test_kill_session_marks_server_desired_stopped_in_owning_workspace(
    client, second_workspace_tmux,
) -> None:
    """The server-tab kill hook (logical_name == 'server') must write
    desired=stopped into the SESSION's OWN workspace state file — not the
    active workspace's — when the killed session belongs to another
    registered workspace."""
    other_root = second_workspace_tmux
    other_name = _spawn_and_adopt(other_root, "demo2", "server")

    r = client.delete(f"/api/term/sessions/{other_name}")
    assert r.status_code == 200, r.text

    desired = json.loads((other_root / ".lab" / "state" / "servers.json").read_text())
    assert desired["demo2"]["desired"] == "stopped"
    # The active workspace's own (nonexistent) state file was not touched.
    assert not (Path(client.app.state.index_cache.root) / ".lab" / "state" / "servers.json").is_file()


def test_kill_project_sessions_workspace_filter_scopes_to_one_workspace(
    client, seed_project, second_workspace_tmux,
) -> None:
    seed_project("demo")
    mine = client.post("/api/term/sessions",
                       json={"project_id": "demo", "kind": "terminal"}).json()
    other_root = second_workspace_tmux
    (other_root / "projects" / "demo").mkdir(parents=True)
    other_name = _spawn_and_adopt(other_root, "demo", "bash")

    r = client.delete("/api/term/sessions/project/demo?workspace=other")
    assert r.status_code == 200, r.text
    assert r.json()["killed"] == [other_name]
    # The active workspace's same-project-id session survives untouched.
    assert subprocess.run(["tmux", "has-session", "-t", mine["name"]],
                          capture_output=True).returncode == 0
    assert subprocess.run(["tmux", "has-session", "-t", other_name],
                          capture_output=True).returncode != 0


def test_kill_project_sessions_default_scopes_to_active_workspace_only(
    client, seed_project, second_workspace_tmux,
) -> None:
    """Without ?workspace=, the "X" button's kill-everything call keeps its
    pre-multi-workspace behavior: only the active workspace's sessions for
    that project id are killed, even if another registered workspace has a
    project with the same id."""
    seed_project("demo")
    mine = client.post("/api/term/sessions",
                       json={"project_id": "demo", "kind": "terminal"}).json()
    other_root = second_workspace_tmux
    (other_root / "projects" / "demo").mkdir(parents=True)
    other_name = _spawn_and_adopt(other_root, "demo", "bash")

    r = client.delete("/api/term/sessions/project/demo")
    assert r.status_code == 200, r.text
    assert r.json()["killed"] == [mine["name"]]
    assert subprocess.run(["tmux", "has-session", "-t", mine["name"]],
                          capture_output=True).returncode != 0
    assert subprocess.run(["tmux", "has-session", "-t", other_name],
                          capture_output=True).returncode == 0


def test_kill_project_sessions_unknown_workspace_404(client, seed_project, isolated_prefix) -> None:
    seed_project("demo")
    r = client.delete("/api/term/sessions/project/demo?workspace=does-not-exist")
    assert r.status_code == 404


# ─── Workspace autopilot launch flags ────────────────────────────────────────


def test_claude_launch_respects_workspace_autopilot(client, seed_project, isolated_prefix,
                                                    monorepo: Path, tmp_path: Path) -> None:
    from lab import settings as lab_settings

    seed_project("demo")
    # Default: claude autopilot is on → --permission-mode auto in the command.
    r = client.post("/api/term/sessions", json={"project_id": "demo", "kind": "claude"})
    assert r.status_code == 200, r.text
    assert r.json()["auto"] is True
    state = json.loads((tmp_path / "fake-tmux-state.json").read_text())
    cmd = state["sessions"][r.json()["name"]]["cmd"]
    assert "--permission-mode auto" in cmd

    # Workspace opt-out: a fresh session launches without the flag.
    lab_settings.update(monorepo, {"autopilot": {"claude": False}})
    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "name": "claude-2",
    })
    assert r.status_code == 200, r.text
    assert r.json()["auto"] is False
    state = json.loads((tmp_path / "fake-tmux-state.json").read_text())
    cmd = state["sessions"][r.json()["name"]]["cmd"]
    assert "--permission-mode" not in cmd

    # Explicit per-request auto still wins over the workspace setting.
    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "name": "claude-3", "auto": True,
    })
    assert r.status_code == 200, r.text
    assert r.json()["auto"] is True


def test_copilot_launch_appends_autopilot_flag(client, seed_project, isolated_prefix,
                                               monorepo: Path, tmp_path: Path,
                                               monkeypatch) -> None:
    import shutil as real_shutil

    from core.routes import term as term_route
    from lab import settings as lab_settings

    seed_project("demo")
    real_which = real_shutil.which
    monkeypatch.setattr(
        term_route.shutil, "which",
        lambda cmd: "/fake/copilot" if cmd == "copilot" else real_which(cmd),
    )

    # Off by default: bare `copilot`.
    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "agent": "copilot", "name": "copilot",
    })
    assert r.status_code == 200, r.text
    state = json.loads((tmp_path / "fake-tmux-state.json").read_text())
    assert state["sessions"][r.json()["name"]]["cmd"] == "copilot"
    assert r.json()["auto"] is False

    # Workspace checkbox on: fresh sessions get --autopilot.
    lab_settings.update(monorepo, {"autopilot": {"copilot": True}})
    r = client.post("/api/term/sessions", json={
        "project_id": "demo", "kind": "claude", "agent": "copilot", "name": "copilot-2",
    })
    assert r.status_code == 200, r.text
    assert r.json()["auto"] is True
    state = json.loads((tmp_path / "fake-tmux-state.json").read_text())
    assert state["sessions"][r.json()["name"]]["cmd"] == "copilot --autopilot"
