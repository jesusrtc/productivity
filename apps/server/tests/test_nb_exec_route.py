from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from server.routes import nb_exec as nb_exec_route


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
    rel = "content/projects/demo/notebooks/x.ipynb"
    (monorepo / "content" / "projects" / "demo" / "notebooks").mkdir(parents=True, exist_ok=True)

    r = client.get(f"/api/nb/session?path={rel}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == rel
    assert body["session"].startswith("lab-")
    assert len(body["session"]) == len("lab-") + 12

    # Same path must always map to the same session id.
    r2 = client.get(f"/api/nb/session?path={rel}")
    assert r2.json()["session"] == body["session"]


def test_exec_appends_cell_to_new_notebook(client, monorepo: Path, patch_darwin) -> None:
    _, calls = patch_darwin
    rel = "content/projects/demo/notebooks/new.ipynb"

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


def test_exec_appends_to_existing_notebook_and_pins_session(
    client, monorepo: Path, patch_darwin
) -> None:
    _, calls = patch_darwin
    rel = "content/projects/demo/notebooks/grow.ipynb"
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
    rel = "content/projects/demo/notebooks/err.ipynb"
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
    rel = "content/projects/demo/notebooks/kerr.ipynb"
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
        json={"path": "content/projects/demo/notebooks/q.ipynb", "code": "1"},
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
        json={"path": "content/projects/demo/notes.txt", "code": "1"},
    )
    assert r.status_code == 400


def test_exec_handles_missing_darwin_binary(client, monorepo: Path, monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("darwin: not found")

    monkeypatch.setattr(nb_exec_route.subprocess, "run", fake_run)
    r = client.post(
        "/api/nb/exec",
        json={"path": "content/projects/demo/notebooks/x.ipynb", "code": "1"},
    )
    assert r.status_code == 503
    assert "darwin" in r.json()["detail"].lower()


def test_exec_with_cell_index_replaces_in_place(
    client, monorepo: Path, patch_darwin
) -> None:
    fake_run, _ = patch_darwin
    rel = "content/projects/demo/notebooks/inplace.ipynb"
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
    rel = "content/projects/demo/notebooks/short.ipynb"
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
    rel = "content/projects/demo/notebooks/del.ipynb"
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
        json={"path": "content/projects/demo/notebooks/nope.ipynb", "cell_index": 0},
    )
    assert r.status_code == 404


def test_delete_cell_out_of_range(client, monorepo: Path) -> None:
    rel = "content/projects/demo/notebooks/oob.ipynb"
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
    rel = "content/projects/demo/notebooks/insert.ipynb"
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
    rel = "content/projects/demo/notebooks/prepend.ipynb"
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
    rel = "content/projects/demo/notebooks/insert_end.ipynb"
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
    rel = "content/projects/demo/notebooks/oob_insert.ipynb"
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
    rel = "content/projects/demo/notebooks/conflict.ipynb"
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
