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


@pytest.fixture()
def isolated_prefix(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Unique prefix plus a fake tmux state file per test."""
    prefix = f"lab-test-{uuid.uuid4().hex[:6]}-"
    monkeypatch.setenv("LAB_TMUX_PREFIX", prefix)
    state_file = tmp_path / "fake-tmux-state.json"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
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
