"""Cleanup tests never connect to the user's tmux server or vaults."""
from copy import deepcopy
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.routes import terminal_cleanup as cleanup

NOW = 2_000_000_000
OLD = NOW - 8 * 86400


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    roots = {name: tmp_path / name for name in ("one", "two", "assistant")}
    for root in roots.values():
        root.mkdir()
    vaults = [{"id": name, "path": path} for name, path in roots.items()]
    metadata = {path: {} for path in roots.values()}
    saved, listing, calls = {}, [], []
    monkeypatch.setattr(cleanup, "_roots", lambda root: vaults)
    monkeypatch.setattr(cleanup.time, "time", lambda: NOW)
    monkeypatch.setattr(cleanup.auth, "require_admin", lambda request: None)
    monkeypatch.setattr(cleanup.fsguard, "guarded", lambda root, fn, *args: fn(*args))
    monkeypatch.setattr(cleanup.term, "_tmux_list", lambda *a, **kw: deepcopy(listing))
    monkeypatch.setattr(cleanup.term, "_load_meta", lambda root: deepcopy(metadata[root]))
    monkeypatch.setattr(cleanup.term, "_save_meta", lambda root, data: metadata.__setitem__(root, deepcopy(data)))
    monkeypatch.setattr(cleanup.term, "_reconstruct_meta_entry", lambda *a: None)
    monkeypatch.setattr(cleanup.term, "_load_workspace", lambda root, workspace: deepcopy(saved.get((root, workspace), {})))
    monkeypatch.setattr(cleanup.term, "_save_workspace", lambda root, workspace, data: saved.__setitem__((root, workspace), deepcopy(data)))
    monkeypatch.setattr(cleanup.term, "_enrich_agent_session_names", lambda rows: None)
    monkeypatch.setattr(cleanup.agent_activity, "enrich", lambda rows: None)
    monkeypatch.setattr(cleanup.term, "_invalidate_workspace_term_caches", lambda: None)
    from contextlib import nullcontext
    monkeypatch.setattr(cleanup.tmux_sockets, "state_lock", nullcontext)

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(cleanup.subprocess, "run", run)

    def add(name, vault="one", workspace="demo", **extra):
        root = roots[vault]
        info = {"workspace_id": workspace, "logical_name": name, "label": f"Label {name}"}
        live = {"name": "lab-" + name, "tmux_socket": "cleanup-test", "tmux_id": "$" + str(len(listing)),
                "created": OLD - 86400, "activity": OLD, "last_attached": OLD,
                "last_access": 0, "attached": False, "activity_known": True, "pane_pid": len(listing) + 100}
        for key, value in extra.items():
            (live if key in live else info)[key] = value
        metadata[root][live["name"]] = info
        data = saved.setdefault((root, workspace), {"name": workspace.title(), "sessions": []})
        data["sessions"].append({"name": info["logical_name"], "label": info["label"]})
        listing.append(live)
        return live

    app = FastAPI()
    app.include_router(cleanup.router)
    app.state.index_cache = SimpleNamespace(root=roots["one"])
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, roots=roots, meta=metadata, saved=saved, listing=listing,
                              calls=calls, add=add)


def snapshot(setup):
    response = setup.client.get("/api/term/cleanup")
    assert response.status_code == 200
    return response.json()


def ids(data):
    return [row["id"] for group in data["groups"] for row in group["sessions"]]


def test_candidates_use_activity_not_creation_and_strict_seven_day_cutoff(setup):
    setup.add("old")
    setup.add("boundary", activity=NOW - 7 * 86400)
    setup.add("recent", last_attached=NOW - 100)
    setup.add("viewed", last_access=NOW - 10)
    setup.add("connected", attached=True)
    setup.add("new", created=NOW - 5)
    setup.add("unknown", activity_known=False)
    setup.add("server", logical_name="server-api")
    setup.add("working", agent_activity={"state": "working"})
    result = snapshot(setup)
    assert result["count"] == 1
    assert result["groups"][0]["sessions"][0]["name"] == "lab-old"
    assert not setup.calls


def test_scopes_include_home_assistant_and_same_workspace_in_two_vaults(setup):
    setup.add("a")
    setup.add("b", vault="two")
    setup.add("home-a", workspace="__self__")
    setup.add("home-b", vault="two", workspace="__self__")
    setup.add("assistant", vault="assistant", workspace="__assistant__")
    result = snapshot(setup)
    assert result["count"] == 5
    assert len(result["groups"]) == 4
    assert len(next(g for g in result["groups"] if g["name"] == "Home")["sessions"]) == 2
    assert any(g["name"] == "Assistant" for g in result["groups"])
    chosen = next(g for g in result["groups"] if g["vault"] == "two" and g["workspace_id"] == "demo")
    response = setup.client.post("/api/term/cleanup", json={"candidates": [s["id"] for s in chosen["sessions"]]})
    assert [s["name"] for s in response.json()["killed"]] == ["lab-b"]
    assert setup.saved[(setup.roots["one"], "demo")]["sessions"]
    assert setup.saved[(setup.roots["two"], "demo")]["sessions"] == []
    assert "lab-a" in setup.meta[setup.roots["one"]]
    assert cleanup.ui._load(setup.roots["two"])["terminal_autospawn_disabled"] == ["demo"]


@pytest.mark.parametrize("change", ["last_access", "attached", "created", "tmux_id", "tmux_socket", "pane_pid"])
def test_stale_snapshot_cannot_kill_reused_or_newly_active_session(setup, change):
    live = setup.add("old")
    selected = ids(snapshot(setup))
    live[change] = True if change == "attached" else ("changed" if change in {"tmux_id", "tmux_socket"} else NOW)
    response = setup.client.post("/api/term/cleanup", json={"candidates": selected})
    assert response.status_code == 200
    assert len(response.json()["skipped"]) == 1
    assert response.json()["killed"] == []
    assert not setup.calls
    assert setup.saved[(setup.roots["one"], "demo")]["sessions"]


def test_stop_rechecks_exact_tmux_target_and_reports_failed_kills(setup, monkeypatch):
    setup.add("old")
    selected = ids(snapshot(setup))
    def failed(command, **kwargs):
        setup.calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="failure")
    monkeypatch.setattr(cleanup.subprocess, "run", failed)
    result = setup.client.post("/api/term/cleanup", json={"candidates": selected}).json()
    assert len(result["errors"]) == 1
    assert not result["killed"]
    assert setup.saved[(setup.roots["one"], "demo")]["sessions"]
    command = setup.calls[0]
    assert "if-shell" in command
    assert "=lab-old:" in command
    condition = command[command.index("=lab-old:") + 1]
    for field in ("session_id", "session_created", "session_attached", "session_activity", "session_last_attached", "@lab_last_access"):
        assert field in condition


def test_attachment_during_kill_is_skipped_without_purging(setup, monkeypatch):
    setup.add("old")
    monkeypatch.setattr(cleanup.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="lab-cleanup-skipped\n"))
    result = setup.client.post("/api/term/cleanup", json={"candidates": ids(snapshot(setup))}).json()
    assert len(result["skipped"]) == 1
    assert not result["killed"]
    assert setup.saved[(setup.roots["one"], "demo")]["sessions"]


def test_all_only_removes_reviewed_old_tabs(setup):
    setup.add("a")
    setup.add("b", vault="two")
    setup.add("recent", activity=NOW)
    selected = ids(snapshot(setup))
    setup.add("not-reviewed")
    result = setup.client.post("/api/term/cleanup", json={"candidates": selected + selected}).json()
    assert len(result["killed"]) == 2
    assert len(setup.calls) == 2
    assert {s["name"] for s in setup.saved[(setup.roots["one"], "demo")]["sessions"]} == {"recent", "not-reviewed"}


def test_unknown_listing_fails_closed_and_admin_is_required(setup, monkeypatch):
    monkeypatch.setattr(cleanup.term, "_tmux_list", lambda *a, **k: None)
    assert setup.client.get("/api/term/cleanup").status_code == 503
    assert setup.client.post("/api/term/cleanup", json={"candidates": ["fake"]}).status_code == 503
    def deny(request):
        raise HTTPException(403, "Admin required")
    monkeypatch.setattr(cleanup.auth, "require_admin", deny)
    assert setup.client.get("/api/term/cleanup").status_code == 403
    assert setup.client.post("/api/term/cleanup", json={"candidates": ["fake"]}).status_code == 403
    assert not setup.calls


def test_unavailable_vault_is_reported_and_excluded(setup, monkeypatch):
    setup.add("old")
    original = cleanup.term._load_meta
    def load(root):
        if root == setup.roots["two"]:
            raise OSError("offline")
        return original(root)
    monkeypatch.setattr(cleanup.term, "_load_meta", load)
    result = snapshot(setup)
    assert result["count"] == 1
    assert "two" in result["warnings"][0]


def test_home_prefers_owning_registry_over_recovery_in_another_vault(setup, monkeypatch):
    setup.add("home", vault="two", workspace="__self__")
    monkeypatch.setattr(cleanup.term, "_reconstruct_meta_entry", lambda *a: {
        "workspace_id": "__self__", "logical_name": "wrong-recovery"})
    result = snapshot(setup)
    row = result["groups"][0]["sessions"][0]
    assert row["vault"] == "two"
    assert row["logical_name"] == "home"


def test_activity_listing_reads_server_fields_without_pruning(setup, monkeypatch):
    monkeypatch.setattr(cleanup.tmux_sockets, "generations", lambda: [{"name": "fixture"}])
    monkeypatch.setattr(cleanup.term, "_tmux_available", lambda: True)
    monkeypatch.setattr(cleanup.subprocess, "run", lambda *a, **k: SimpleNamespace(
        returncode=0, stdout=f"lab-old|{OLD}|0|1|/dev/test|123|{OLD}|{OLD + 2}|{OLD + 4}|$12\n", stderr=""))
    # _tmux_list is patched at the fixture boundary; use the original function
    # from the module source via the function captured before fixture setup.
    rows = TMUX_LIST("lab-", prune_draining=False, activity=True)
    assert rows[0]["activity_known"] is True
    assert cleanup._last_used(rows[0]) == OLD + 4
    assert rows[0]["tmux_id"] == "$12"


TMUX_LIST = cleanup.term._tmux_list


def test_document_cleanup_preserves_resume_identity_and_drafts(setup, monkeypatch):
    setup.add("document", vault="assistant", workspace="__assistant__", document_key="doc")
    entries = {"doc": {"key": "doc", "name": "lab-document", "last_used": OLD,
                        "state": "running", "conversation_id": "resume-me", "unsent_input": True}}
    monkeypatch.setattr(cleanup.document_terminals, "_load", lambda root: deepcopy(entries))
    monkeypatch.setattr(cleanup.document_terminals, "_save", lambda root, updated: entries.update(updated))
    monkeypatch.setattr(cleanup.document_terminals, "_INPUT", {})
    assert snapshot(setup)["count"] == 0
    entries["doc"]["unsent_input"] = False
    result = setup.client.post("/api/term/cleanup", json={"candidates": ids(snapshot(setup))}).json()
    assert len(result["killed"]) == 1
    assert entries["doc"]["state"] == "sleeping"
    assert entries["doc"]["conversation_id"] == "resume-me"


def test_failed_autospawn_suppression_never_stops_session(setup, monkeypatch):
    setup.add("old")
    def fail(*args):
        raise OSError("Read-only volume")
    monkeypatch.setattr(cleanup, "_disable_autospawn", fail)
    result = setup.client.post("/api/term/cleanup", json={"candidates": ids(snapshot(setup))}).json()
    assert len(result["errors"]) == 1
    assert not result["killed"]
    assert not setup.calls
