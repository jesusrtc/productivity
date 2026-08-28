from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from core.routes import nb_exec as nb_exec_route
from lab import paths


def _fake_completed(stdout: str, *, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["darwin"], returncode=returncode, stdout=stdout, stderr=stderr,
    )


@pytest.fixture()
def patch_darwin(monkeypatch: pytest.MonkeyPatch):
    """Patch ``subprocess.run`` inside the route module to return a canned
    Darwin JSON envelope. Returns a holder so tests can read what was passed
    to the CLI (verify --session, --kernel, --file etc.)."""
    calls: list[dict[str, Any]] = []

    def fake_run(cmd, **kwargs):
        # Capture the temp file's contents so tests can assert what code
        # was actually shipped to darwin.
        try:
            tmp_path = cmd[cmd.index("--file") + 1]
            code = Path(tmp_path).read_text(encoding="utf-8")
        except (ValueError, IndexError, OSError):
            code = ""
        calls.append({"cmd": list(cmd), "code": code})
        return fake_run.response

    fake_run.response = _fake_completed(json.dumps({  # type: ignore[attr-defined]
        "output": "42\n",
        "kernel_id": "kid-1234",
        "execution_count": 1,
        "cell_outputs": [
            {"output_type": "stream", "name": "stdout", "text": "42\n"},
        ],
    }))
    monkeypatch.setattr(nb_exec_route.subprocess, "run", fake_run)
    return fake_run, calls


def test_session_endpoint_returns_deterministic_id(client, monorepo: Path) -> None:
    rel = "projects/demo/notebooks/x.ipynb"
    (monorepo / "projects" / "demo" / "notebooks").mkdir(parents=True, exist_ok=True)

    r = client.get(f"/api/nb/session?path={rel}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == rel
    assert body["session"].startswith("lab-")
    assert len(body["session"]) == len("lab-") + 12

    # Same path must always map to the same session id.
    r2 = client.get(f"/api/nb/session?path={rel}")
    assert r2.json()["session"] == body["session"]

    # A different .ipynb owns a different kernel session.
    other = client.get("/api/nb/session?path=projects/demo/notebooks/y.ipynb")
    assert other.status_code == 200, other.text
    assert other.json()["session"] != body["session"]


def test_exec_appends_cell_to_new_notebook(client, monorepo: Path, patch_darwin) -> None:
    _, calls = patch_darwin
    rel = "projects/demo/notebooks/new.ipynb"

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
    assert body["session"].startswith("lab-")
    assert body["kernel_id"] == "kid-1234"
    assert body["execution_count"] == 1
    assert body["cell"]["cell_type"] == "code"
    assert any("42" in o["content"] for o in body["cell"]["outputs"])

    # Darwin was invoked with the pinned session and the code via --file.
    assert len(calls) == 1
    cmd = calls[0]["cmd"]
    assert cmd[0:3] == ["darwin", "code", "execute"]
    assert "--session" in cmd
    assert calls[0]["code"] == "print(42)"


def test_exec_and_live_replay_follow_explicit_owning_workspace(
    client, monorepo: Path, tmp_path: Path, patch_darwin
) -> None:
    """A project tab may belong to a workspace other than the active shell."""
    paths.register_workspace(
        monorepo, name="Main", workspace_id="main", active=True
    )
    other = tmp_path / "other-workspace"
    (other / "projects").mkdir(parents=True)
    registration = paths.register_workspace(
        other, name="Local", workspace_id="local", active=False
    )
    rel = "projects/test/agent-demo.ipynb"

    executed = client.post(
        "/api/nb/exec",
        json={
            "workspace": registration["id"],
            "path": rel,
            "code": "print(42)",
        },
    )

    assert executed.status_code == 200, executed.text
    assert executed.json()["workspace"] == registration["id"]
    assert (other / rel).is_file()
    assert not (monorepo / rel).exists()
    opened = client.get(
        f"/api/nb?path={rel}&workspace={registration['id']}"
    )
    assert opened.status_code == 200, opened.text
    assert opened.json()["cells"][0]["source"] == "print(42)"
    live = client.get(
        f"/api/nb/live?path={rel}&workspace={registration['id']}"
    )
    assert live.status_code == 200, live.text
    assert live.json() == {
        "path": rel,
        "workspace": registration["id"],
        "executions": [],
    }

def test_exec_appends_to_existing_notebook_and_pins_session(
    client, monorepo: Path, patch_darwin
) -> None:
    _, calls = patch_darwin
    rel = "projects/demo/notebooks/grow.ipynb"
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
        i = entry["cmd"].index("--session")
        sessions.append(entry["cmd"][i + 1])
    assert sessions[0] == sessions[1]


def test_exec_error_cell_is_persisted_as_200(
    client, monorepo: Path, patch_darwin
) -> None:
    fake_run, _ = patch_darwin
    fake_run.response = _fake_completed(json.dumps({
        "output": "",
        "kernel_id": "kid-1234",
        "execution_count": 2,
        "cell_outputs": [
            {"output_type": "error", "ename": "NameError",
             "evalue": "name 'foo' is not defined",
             "traceback": ["Traceback…", "NameError: name 'foo' is not defined"]},
        ],
    }))
    rel = "projects/demo/notebooks/err.ipynb"
    r = client.post("/api/nb/exec", json={"path": rel, "code": "foo"})
    assert r.status_code == 200, r.text

    cell = r.json()["cell"]
    assert any(o["type"] == "error" for o in cell["outputs"])


def test_exec_kernel_error_returns_200_with_error_cell(
    client, monorepo: Path, patch_darwin
) -> None:
    """Exit 6 (KernelExecutionError) — e.g. ``%sql`` magic not imported —
    must surface as an in-cell error output, not an HTTP 500. Otherwise the
    user sees nothing in the UI and has to dig the failure out of devtools."""
    fake_run, _ = patch_darwin
    fake_run.response = _fake_completed(
        json.dumps({
            "error": "KernelExecutionError",
            "message": "UsageError: Line magic function `%sql` not found.",
            "recovery": "Check your code for errors.",
            "exit_code": 6,
        }),
        returncode=6,
    )
    rel = "projects/demo/notebooks/kerr.ipynb"
    r = client.post("/api/nb/exec", json={"path": rel, "code": "%sql SELECT 1"})

    assert r.status_code == 200, r.text
    cell = r.json()["cell"]
    # Error output is the same shape parse_notebook produces for any other
    # raised exception, so the FE renders it the same way.
    assert any(o["type"] == "error" for o in cell["outputs"])
    err_text = " ".join(o["content"] for o in cell["outputs"] if o["type"] == "error")
    assert "%sql" in err_text
    # And it's persisted on disk like any other run.
    on_disk = json.loads((monorepo / rel).read_text())
    assert on_disk["cells"][-1]["outputs"][0]["output_type"] == "error"


def test_exec_maps_auth_failure_to_401(client, monorepo: Path, patch_darwin) -> None:
    fake_run, _ = patch_darwin
    fake_run.response = _fake_completed(
        "", returncode=2, stderr="DVToken expired",
    )
    r = client.post(
        "/api/nb/exec",
        json={"path": "projects/demo/notebooks/q.ipynb", "code": "1"},
    )
    assert r.status_code == 401
    assert "auth" in r.json()["detail"].lower()


def test_exec_rejects_path_traversal(client, patch_darwin) -> None:
    r = client.post(
        "/api/nb/exec",
        json={"path": "../etc/passwd.ipynb", "code": "1"},
    )
    assert r.status_code == 400


def test_exec_rejects_non_ipynb(client, patch_darwin) -> None:
    r = client.post(
        "/api/nb/exec",
        json={"path": "projects/demo/notes.txt", "code": "1"},
    )
    assert r.status_code == 400


def test_exec_handles_missing_darwin_binary(client, monorepo: Path, monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("darwin: not found")

    monkeypatch.setattr(nb_exec_route.subprocess, "run", fake_run)
    r = client.post(
        "/api/nb/exec",
        json={"path": "projects/demo/notebooks/x.ipynb", "code": "1"},
    )
    assert r.status_code == 503
    assert "darwin" in r.json()["detail"].lower()


def test_exec_with_cell_index_replaces_in_place(
    client, monorepo: Path, patch_darwin
) -> None:
    fake_run, _ = patch_darwin
    rel = "projects/demo/notebooks/inplace.ipynb"
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
    fake_run.response = _fake_completed(json.dumps({
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
    client, monorepo: Path, patch_darwin
) -> None:
    rel = "projects/demo/notebooks/short.ipynb"
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
    rel = "projects/demo/notebooks/del.ipynb"
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
        json={"path": "projects/demo/notebooks/nope.ipynb", "cell_index": 0},
    )
    assert r.status_code == 404


def test_delete_cell_out_of_range(client, monorepo: Path) -> None:
    rel = "projects/demo/notebooks/oob.ipynb"
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
    client, monorepo: Path, patch_darwin
) -> None:
    """``insert_at`` shifts existing cells down and lands the new cell at the
    given index — the wire used by the UI's hover-revealed `+` button between
    cells."""
    fake_run, calls = patch_darwin
    rel = "projects/demo/notebooks/insert.ipynb"
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
    fake_run.response = _fake_completed(json.dumps({
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
    client, monorepo: Path, patch_darwin
) -> None:
    """``insert_at=0`` puts the new cell at the very top."""
    fake_run, _ = patch_darwin
    rel = "projects/demo/notebooks/prepend.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["existing"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_completed(json.dumps({
        "output": "", "kernel_id": "k", "execution_count": 5, "cell_outputs": [],
    }))
    r = client.post("/api/nb/exec", json={
        "path": rel, "code": "first", "insert_at": 0,
    })
    assert r.status_code == 200, r.text
    sources = ["".join(c["source"]) for c in json.loads(target.read_text())["cells"]]
    assert sources == ["first", "existing"]


def test_exec_insert_at_end_equals_append(
    client, monorepo: Path, patch_darwin
) -> None:
    """``insert_at == len(cells)`` is identical to a plain append."""
    fake_run, _ = patch_darwin
    rel = "projects/demo/notebooks/insert_end.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [
            {"cell_type": "code", "execution_count": 1, "metadata": {},
             "source": ["first"], "outputs": []},
        ],
    }))
    fake_run.response = _fake_completed(json.dumps({
        "output": "", "kernel_id": "k", "execution_count": 2, "cell_outputs": [],
    }))
    r = client.post("/api/nb/exec", json={"path": rel, "code": "last", "insert_at": 1})
    assert r.status_code == 200
    sources = ["".join(c["source"]) for c in json.loads(target.read_text())["cells"]]
    assert sources == ["first", "last"]


def test_exec_insert_at_out_of_range_returns_404(
    client, monorepo: Path, patch_darwin
) -> None:
    rel = "projects/demo/notebooks/oob_insert.ipynb"
    target = monorepo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [],
    }))
    r = client.post("/api/nb/exec", json={"path": rel, "code": "x", "insert_at": 7})
    assert r.status_code == 404
    assert "out of range" in r.json()["detail"]


def test_exec_rejects_cell_index_and_insert_at_together(
    client, monorepo: Path, patch_darwin
) -> None:
    """The two are mutually exclusive — server must reject the ambiguity."""
    rel = "projects/demo/notebooks/conflict.ipynb"
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
        path="projects/demo/notebooks/live.ipynb",
        workspace="local",
        run_id=run_id,
        cell_id="cell-live",
        cell_index=3,
        actor="agent",
        source="display(chart)",
        provider="local",
        provider_label="project kernel",
        execution_count=8,
        started_at=100.0,
    )
    try:
        assert started["sequence"] == 0
        assert "Running on project kernel" in started["outputs"][0]["content"]

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
    rel = "projects/demo/notebooks/live-finish-race.ipynb"
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
        workspace="local",
        run_id=run_id,
        cell_id=cell["id"],
        cell_index=0,
        actor="agent",
        source="print(1)",
        provider="local",
        provider_label="project kernel",
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
    rel = "projects/demo/notebooks/orphaned.ipynb"
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
