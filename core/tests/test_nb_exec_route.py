from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.routes import nb_exec as nb_exec_route
from lab import paths


def _fake_result(stdout: str) -> dict:
    return json.loads(stdout)


@pytest.fixture()
def patch_kernel(monkeypatch: pytest.MonkeyPatch):
    """Exercise the route's persistence and events with a local kernel double."""
    from core import notebook_kernel
    calls: list[dict[str, Any]] = []

    async def fake_run(root, path, handle, code, timeout, *, on_event=None):
        calls.append({"session": notebook_kernel.session_name(root, path), "code": code})
        return fake_run.response

    fake_run.response = {
        "kernel_id": "kid-1234",
        "execution_count": 1,
        "cell_outputs": [{"output_type": "stream", "name": "stdout", "text": "42\n"}],
    }
    monkeypatch.setattr(notebook_kernel, "execute", fake_run)
    monkeypatch.setattr(nb_exec_route, "_required_local_handle", lambda *args: object())
    return fake_run, calls


def test_session_endpoint_returns_deterministic_id(client, monorepo: Path) -> None:
    rel = "workspaces/demo/notebooks/x.ipynb"
    (monorepo / "workspaces" / "demo" / "notebooks").mkdir(parents=True, exist_ok=True)

    r = client.get(f"/api/nb/session?path={rel}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == rel
    assert body["session"].startswith("local-")
    assert len(body["session"]) == len("local-") + 12

    # Same path must always map to the same session id.
    r2 = client.get(f"/api/nb/session?path={rel}")
    assert r2.json()["session"] == body["session"]

    # A different .ipynb owns a different kernel session.
    other = client.get("/api/nb/session?path=workspaces/demo/notebooks/y.ipynb")
    assert other.status_code == 200, other.text
    assert other.json()["session"] != body["session"]


def test_exec_appends_cell_to_new_notebook(client, monorepo: Path, patch_kernel) -> None:
    _, calls = patch_kernel
    rel = "workspaces/demo/notebooks/new.ipynb"

    r = client.post("/api/nb/exec", json={"path": rel, "code": "print(42)"})
    assert r.status_code == 200, r.text
    body = r.json()

    # File got created on disk with one code cell containing the stdout.
    nb_path = monorepo / rel
    assert nb_path.is_file()
    on_disk = json.loads(nb_path.read_text())
    assert on_disk["nbformat"] == 4
    assert len(on_disk["cells"]) == 1
    cell = on_disk["cells"][0]
    assert cell["cell_type"] == "code"
    assert cell["execution_count"] == 1
    assert "".join(cell["source"]) == "print(42)"
    assert cell["outputs"][0]["output_type"] == "stream"
    assert "42" in cell["outputs"][0]["text"]

    # Response shape matches what the UI's renderer consumes.
    assert body["session"].startswith("local-")
    assert body["kernel_id"] == "kid-1234"
    assert body["execution_count"] == 1
    assert body["cell"]["cell_type"] == "code"
    assert any("42" in o["content"] for o in body["cell"]["outputs"])

    assert len(calls) == 1
    assert calls[0]["session"] == body["session"]
    assert calls[0]["code"] == "print(42)"


def test_exec_and_live_replay_follow_explicit_owning_vault(
    client, monorepo: Path, tmp_path: Path, patch_kernel
) -> None:
    """A workspace tab may belong to a vault other than the active shell."""
    paths.register_vault(
        monorepo, name="Main", vault_id="main", active=True
    )
    other = tmp_path / "other-vault"
    (other / "workspaces").mkdir(parents=True)
    registration = paths.register_vault(
        other, name="Local", vault_id="local", active=False
    )
    rel = "workspaces/test/agent-demo.ipynb"

    executed = client.post(
        "/api/nb/exec",
        json={
            "vault": registration["id"],
            "path": rel,
            "code": "print(42)",
        },
    )

    assert executed.status_code == 200, executed.text
    assert executed.json()["vault"] == registration["id"]
    assert (other / rel).is_file()
    assert not (monorepo / rel).exists()
    opened = client.get(
        f"/api/nb?path={rel}&vault={registration['id']}"
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["cells"][0]["source"] == "print(42)"
    live = client.get(
        f"/api/nb/live?path={rel}&vault={registration['id']}"
    )
    assert live.status_code == 200, live.text
    assert live.json() == {
        "path": rel,
        "vault": registration["id"],
        "executions": [],
    }

def test_exec_appends_to_existing_notebook_and_pins_session(
    client, monorepo: Path, patch_kernel
) -> None:
    _, calls = patch_kernel
    rel = "workspaces/demo/notebooks/grow.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 7, "metadata": {},
             "source": ["x=1"], "outputs": []},
        ],
    }))

    r1 = client.post("/api/nb/exec", json={"path": rel, "code": "y=2"})
    r2 = client.post("/api/nb/exec", json={"path": rel, "code": "z=3"})
    assert r1.status_code == 200 and r2.status_code == 200

    on_disk = json.loads(target.read_text())
    assert len(on_disk["cells"]) == 3
    assert "".join(on_disk["cells"][1]["source"]) == "y=2"
    assert "".join(on_disk["cells"][2]["source"]) == "z=3"

    # Both runs used the SAME session — the per-file pin.
    sessions = []
    for entry in calls:
        sessions.append(entry["session"])
    assert sessions[0] == sessions[1]


def test_exec_error_cell_is_persisted_as_200(
    client, monorepo: Path, patch_kernel
) -> None:
    fake_run, _ = patch_kernel
    fake_run.response = _fake_result(json.dumps({
        "output": "",
        "kernel_id": "kid-1234",
        "execution_count": 2,
        "cell_outputs": [
            {"output_type": "error", "ename": "NameError",
             "evalue": "name 'foo' is not defined",
             "traceback": ["Traceback…", "NameError: name 'foo' is not defined"]},
        ],
    }))
    rel = "workspaces/demo/notebooks/err.ipynb"
    r = client.post("/api/nb/exec", json={"path": rel, "code": "foo"})
    assert r.status_code == 200, r.text

    cell = r.json()["cell"]
    assert any(o["type"] == "error" for o in cell["outputs"])


def test_exec_rejects_path_traversal(client, patch_kernel) -> None:
    r = client.post(
        "/api/nb/exec",
        json={"path": "../etc/passwd.ipynb", "code": "1"},
    )
    assert r.status_code == 400


def test_exec_rejects_non_ipynb(client, patch_kernel) -> None:
    r = client.post(
        "/api/nb/exec",
        json={"path": "workspaces/demo/notes.txt", "code": "1"},
    )
    assert r.status_code == 400


def test_exec_with_cell_index_replaces_in_place(
    client, monorepo: Path, patch_kernel
) -> None:
    fake_run, _ = patch_kernel
    rel = "workspaces/demo/notebooks/inplace.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["x=1\n", "print(x)"], "outputs": [
                {"output_type": "stream", "name": "stdout", "text": "1\n"},
             ]},
            {"cell_type": "code", "execution_count": 2, "metadata": {},
             "source": ["y=2"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_result(json.dumps({
        "output": "99\n",
        "kernel_id": "kid-1234",
        "execution_count": 7,
        "cell_outputs": [
            {"output_type": "stream", "name": "stdout", "text": "99\n"},
        ],
    }))

    r = client.post("/api/nb/exec", json={
        "path": rel, "code": "x=99\nprint(x)", "cell_index": 0,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cell_index"] == 0

    on_disk = json.loads(target.read_text())
    assert len(on_disk["cells"]) == 2  # no append
    assert "".join(on_disk["cells"][0]["source"]) == "x=99\nprint(x)"
    assert on_disk["cells"][0]["outputs"][0]["text"] == "99\n"
    assert on_disk["cells"][0]["execution_count"] == 7
    # Untouched cell stays the same.
    assert "".join(on_disk["cells"][1]["source"]) == "y=2"


def test_exec_with_out_of_range_cell_index_returns_404(
    client, monorepo: Path, patch_kernel
) -> None:
    rel = "workspaces/demo/notebooks/short.ipynb"
    (monorepo / rel).parent.mkdir(parents=True, exist_ok=True)
    (monorepo / rel).write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [],
    }))
    r = client.post(
        "/api/nb/exec",
        json={"path": rel, "code": "1", "cell_index": 7},
    )
    assert r.status_code == 404
    assert "out of range" in r.json()["detail"]


def test_delete_cell_removes_at_index(client, monorepo: Path) -> None:
    rel = "workspaces/demo/notebooks/del.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["a"], "outputs": []},
            {"cell_type": "code", "execution_count": 2, "metadata": {},
             "source": ["b"], "outputs": []},
            {"cell_type": "code", "execution_count": 3, "metadata": {},
             "source": ["c"], "outputs": []},
        ],
    }))

    r = client.post(
        "/api/nb/cell/delete",
        json={"path": rel, "cell_index": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["remaining_cells"] == 2

    on_disk = json.loads(target.read_text())
    sources = [''.join(c["source"]) for c in on_disk["cells"]]
    assert sources == ["a", "c"]


def test_delete_cell_404_on_missing_notebook(client) -> None:
    r = client.post(
        "/api/nb/cell/delete",
        json={"path": "workspaces/demo/notebooks/nope.ipynb", "cell_index": 0},
    )
    assert r.status_code == 404


def test_delete_cell_out_of_range(client, monorepo: Path) -> None:
    rel = "workspaces/demo/notebooks/oob.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["a"], "outputs": []},
        ],
    }))
    r = client.post(
        "/api/nb/cell/delete",
        json={"path": rel, "cell_index": 5},
    )
    assert r.status_code == 404
    assert "out of range" in r.json()["detail"]


def test_exec_insert_at_inserts_between_cells(
    client, monorepo: Path, patch_kernel
) -> None:
    """``insert_at`` shifts existing cells down and lands the new cell at the
    given index — the wire used by the UI's hover-revealed `+` button between
    cells."""
    fake_run, calls = patch_kernel
    rel = "workspaces/demo/notebooks/insert.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["a = 1"], "outputs": []},
            {"cell_type": "code", "execution_count": 2, "metadata": {},
             "source": ["b = 2"], "outputs": []},
            {"cell_type": "code", "execution_count": 3, "metadata": {},
             "source": ["c = 3"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_result(json.dumps({
        "output": "", "kernel_id": "kid-1", "execution_count": 11,
        "cell_outputs": [{"output_type": "stream", "name": "stdout", "text": "ok\n"}],
    }))

    # Insert between cells [1] and [2] — new cell lands at index 2.
    r = client.post("/api/nb/exec", json={
        "path": rel, "code": "mid = 99", "insert_at": 2,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cell_index"] == 2

    on_disk = json.loads(target.read_text())
    assert len(on_disk["cells"]) == 4
    sources = ["".join(c["source"]) for c in on_disk["cells"]]
    assert sources == ["a = 1", "b = 2", "mid = 99", "c = 3"]


def test_exec_insert_at_zero_prepends(
    client, monorepo: Path, patch_kernel
) -> None:
    """``insert_at=0`` puts the new cell at the very top."""
    fake_run, _ = patch_kernel
    rel = "workspaces/demo/notebooks/prepend.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["existing"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_result(json.dumps({
        "output": "", "kernel_id": "k", "execution_count": 5, "cell_outputs": [],
    }))
    r = client.post("/api/nb/exec", json={
        "path": rel, "code": "first", "insert_at": 0,
    })
    assert r.status_code == 200, r.text
    sources = ["".join(c["source"]) for c in json.loads(target.read_text())["cells"]]
    assert sources == ["first", "existing"]


def test_exec_insert_at_end_equals_append(
    client, monorepo: Path, patch_kernel
) -> None:
    """``insert_at == len(cells)`` is identical to a plain append."""
    fake_run, _ = patch_kernel
    rel = "workspaces/demo/notebooks/insert_end.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["first"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_result(json.dumps({
        "output": "", "kernel_id": "k", "execution_count": 2, "cell_outputs": [],
    }))
    r = client.post("/api/nb/exec", json={"path": rel, "code": "last", "insert_at": 1})
    assert r.status_code == 200
    sources = ["".join(c["source"]) for c in json.loads(target.read_text())["cells"]]
    assert sources == ["first", "last"]


def test_exec_insert_at_out_of_range_returns_404(
    client, monorepo: Path, patch_kernel
) -> None:
    rel = "workspaces/demo/notebooks/oob_insert.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [],
    }))
    r = client.post("/api/nb/exec", json={"path": rel, "code": "x", "insert_at": 7})
    assert r.status_code == 404
    assert "out of range" in r.json()["detail"]


def test_exec_rejects_cell_index_and_insert_at_together(
    client, monorepo: Path, patch_kernel
) -> None:
    """The two are mutually exclusive — server must reject the ambiguity."""
    rel = "workspaces/demo/notebooks/conflict.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["x"], "outputs": []},
        ],
    }))
    r = client.post("/api/nb/exec", json={
        "path": rel, "code": "x", "cell_index": 0, "insert_at": 0,
    })
    assert r.status_code == 400
    assert "mutually exclusive" in r.json()["detail"]


def test_live_snapshot_replays_rich_output_and_display_updates(tmp_path: Path) -> None:
    target = tmp_path / "live.ipynb"
    run_id = "run-live"
    started = nb_exec_route._live_start(
        target,
        path="workspaces/demo/notebooks/live.ipynb",
        vault="local",
        run_id=run_id,
        cell_id="cell-live",
        cell_index=3,
        actor="agent",
        source="display(chart)",
        provider="local",
        provider_label="workspace kernel",
        execution_count=8,
        started_at=100.0,
    )
    try:
        assert started["sequence"] == 0
        assert "Running on workspace kernel" in started["outputs"][0]["content"]

        first, first_checkpoint, _ = nb_exec_route._live_apply_kernel_event(
            target,
            run_id,
            {
                "kind": "output",
                "operation": "append",
                "output": {
                    "output_type": "display_data",
                    "data": {"text/html": "<div id='chart'>first</div>"},
                    "metadata": {},
                    "transient": {"display_id": "chart-1"},
                },
            },
        )
        assert first is not None
        assert first["reset"] is True
        assert first["output"]["type"] == "html"
        assert first["output"]["display_id"] == "chart-1"
        assert first_checkpoint is not None

        update, update_checkpoint, _ = nb_exec_route._live_apply_kernel_event(
            target,
            run_id,
            {
                "kind": "output",
                "operation": "replace",
                "output": {
                    "output_type": "display_data",
                    "data": {"text/html": "<div id='chart'>final</div>"},
                    "metadata": {},
                    "transient": {"display_id": "chart-1"},
                },
            },
        )
        assert update is not None
        assert update["operation"] == "replace"
        assert update_checkpoint is not None
        snapshot = nb_exec_route._live_snapshot(target)
        assert len(snapshot) == 1
        assert snapshot[0]["sequence"] == 2
        assert snapshot[0]["outputs"] == [{
            "type": "html",
            "content": "<div id='chart'>final</div>",
            "display_id": "chart-1",
        }]
    finally:
        nb_exec_route._live_remove(target, run_id)
    assert nb_exec_route._live_snapshot(target) == []


def test_live_endpoint_does_not_replay_a_run_after_its_cell_finished(
    client, monorepo: Path
) -> None:
    rel = "workspaces/demo/notebooks/live-finish-race.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    run_id = "run-finish-race"
    cell = {
        "id": "cell-finish-race",
        "cell_type": "code",
        "execution_count": 1,
        "metadata": {
            "lab_pending": True,
            "lab_run_id": run_id,
            "lab_actor": "agent",
            "lab_started_at": 100.0,
        },
        "source": ["print(1)"],
        "outputs": [],
    }
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [cell],
    }), encoding="utf-8")
    nb_exec_route._live_start(
        target,
        path=rel,
        vault="local",
        run_id=run_id,
        cell_id=cell["id"],
        cell_index=0,
        actor="agent",
        source="print(1)",
        provider="local",
        provider_label="workspace kernel",
        execution_count=1,
        started_at=100.0,
    )
    try:
        running = client.get(f"/api/nb/live?path={rel}")
        assert running.status_code == 200
        assert [run["run_id"] for run in running.json()["executions"]] == [run_id]

        cell["metadata"]["lab_pending"] = False
        cell["metadata"].pop("lab_run_id")
        target.write_text(json.dumps({
            "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [cell],
        }), encoding="utf-8")
        finished = client.get(f"/api/nb/live?path={rel}")
        assert finished.status_code == 200
        assert finished.json()["executions"] == []
    finally:
        nb_exec_route._live_remove(target, run_id)


def test_notebook_read_recovers_orphaned_running_cell_once(
    client, monorepo: Path
) -> None:
    rel = "workspaces/demo/notebooks/orphaned.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [{
            "id": "orphan-cell",
            "cell_type": "code",
            "execution_count": 4,
            "metadata": {
                "lab_pending": True,
                "lab_run_id": "dead-run",
                "lab_actor": "agent",
                "lab_started_at": 100.0,
            },
            "source": ["print('before crash')"],
            "outputs": [{
                "output_type": "stream",
                "name": "stdout",
                "text": ["partial output survived\n"],
            }],
        }],
    }), encoding="utf-8")

    first = client.get(f"/api/nb?path={rel}")
    assert first.status_code == 200, first.text
    recovered = json.loads(target.read_text(encoding="utf-8"))["cells"][0]
    assert recovered["metadata"]["lab_pending"] is False
    assert "lab_run_id" not in recovered["metadata"]
    assert recovered["outputs"][0]["text"] == ["partial output survived\n"]
    errors = [out for out in recovered["outputs"] if out["output_type"] == "error"]
    assert len(errors) == 1
    assert errors[0]["ename"] == "ExecutionLost"

    second = client.get(f"/api/nb?path={rel}")
    assert second.status_code == 200
    again = json.loads(target.read_text(encoding="utf-8"))["cells"][0]
    assert len([out for out in again["outputs"] if out["output_type"] == "error"]) == 1


def test_pending_tracker_counts_queued_runs(tmp_path: Path) -> None:
    target = tmp_path / "queued.ipynb"
    nb_exec_route._mark_running(target)
    nb_exec_route._mark_running(target)
    try:
        assert nb_exec_route.is_path_pending(target) is True
        nb_exec_route._mark_done(target)
        assert nb_exec_route.is_path_pending(target) is True
    finally:
        nb_exec_route._mark_done(target)
    assert nb_exec_route.is_path_pending(target) is False


@pytest.mark.parametrize("endpoint", ["exec", "session/restart", "session/interrupt"])
def test_notebook_actions_require_a_configured_runtime(client, monorepo, endpoint):
    rel = "workspaces/demo/notebooks/unconfigured.ipynb"
    (monorepo / "workspaces/demo").mkdir(parents=True, exist_ok=True)
    response = client.post(f"/api/nb/{endpoint}", json={"path": rel, "code": "print(1)"})
    assert response.status_code == 409, response.text
    assert "runtime" in response.json()["detail"]
    assert not (monorepo / rel).exists()


def test_kernel_failure_finishes_pending_cell(client, monorepo, monkeypatch, patch_kernel):
    from core import notebook_kernel

    async def fail(*args, **kwargs):
        raise notebook_kernel.KernelExecutionError("kernel unavailable", status_code=503)

    monkeypatch.setattr(notebook_kernel, "execute", fail)
    rel = "workspaces/demo/notebooks/failure.ipynb"
    response = client.post("/api/nb/exec", json={"path": rel, "code": "1"})
    assert response.status_code == 503
    cell = json.loads((monorepo / rel).read_text())["cells"][0]
    assert cell["metadata"]["lab_pending"] is False
    assert cell["outputs"][-1]["output_type"] == "error"
    assert not nb_exec_route.is_path_pending(monorepo / rel)
    assert client.get(f"/api/nb/live?path={rel}").json()["executions"] == []
