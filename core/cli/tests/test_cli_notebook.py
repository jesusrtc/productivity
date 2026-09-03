from __future__ import annotations

import io
import json
from pathlib import Path

from click.testing import CliRunner

from lab import paths
from lab.cli import main


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()


class _Opener:
    def __init__(self) -> None:
        self.requests = []

    def open(self, request):
        self.requests.append(request)
        if request.full_url.endswith("/api/auth/login"):
            body = {"authenticated": True}
        else:
            body = {
                "path": "projects/demo/agent-demo.ipynb",
                "cell": {"id": "cell-live", "metadata": {"lab_actor": "agent"}},
            }
        return _Response(json.dumps(body).encode("utf-8"))


def test_notebook_exec_posts_agent_cell_through_live_api(
    monorepo: Path, seed_project, monkeypatch
) -> None:
    project = seed_project("demo")
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        "lab.commands.notebook.paths.read_workspace_registry",
        lambda: {
            "active": "local",
            "workspaces": [{"id": "local", "path": str(monorepo)}],
        },
    )
    monkeypatch.setattr("lab.commands.notebook.server_port", lambda _root: "8080")
    token_path = paths.local_cli_token_file()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text("local-notebook-token-with-at-least-32-characters\n")
    opener = _Opener()
    monkeypatch.setattr(
        "lab.commands.notebook.urllib.request.build_opener",
        lambda *_args: opener,
    )

    result = CliRunner().invoke(main, [
        "notebook", "exec", "agent-demo.ipynb",
        "--code", "print('first', flush=True)",
        "--cell-id", "cell-live",
    ])

    assert result.exit_code == 0, result.output
    assert "watch the open Jupyter tab for live output" in result.output
    assert '"lab_actor": "agent"' in result.output
    assert [request.full_url for request in opener.requests] == [
        "http://localhost:8080/api/nb/exec",
    ]
    assert opener.requests[0].get_header("Authorization") == (
        "Bearer local-notebook-token-with-at-least-32-characters"
    )
    payload = json.loads(opener.requests[0].data)
    assert payload == {
        "path": "projects/demo/agent-demo.ipynb",
        "workspace": "local",
        "actor": "agent",
        "timeout": 600,
        "code": "print('first', flush=True)",
        "cell_id": "cell-live",
    }


def test_notebook_exec_reads_multiline_source_file(
    monorepo: Path, seed_project, monkeypatch, tmp_path: Path
) -> None:
    project = seed_project("demo")
    monkeypatch.chdir(project)
    monkeypatch.setattr(
        "lab.commands.notebook.paths.read_workspace_registry",
        lambda: {"active": None, "workspaces": []},
    )
    opener = _Opener()
    monkeypatch.setattr(
        "lab.commands.notebook.urllib.request.build_opener",
        lambda *_args: opener,
    )
    source = tmp_path / "cell.py"
    source.write_text("import time\nprint('one', flush=True)\n", encoding="utf-8")

    result = CliRunner().invoke(main, [
        "notebook", "exec", "agent-demo.ipynb",
        "--file", str(source),
        "--base-url", "http://lab.test",
    ])

    assert result.exit_code == 0, result.output
    payload = json.loads(opener.requests[1].data)
    assert payload["code"] == source.read_text(encoding="utf-8")
    assert "workspace" not in payload


def test_notebook_exec_rejects_paths_outside_workspace(
    monorepo: Path, monkeypatch, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.ipynb"
    result = CliRunner().invoke(main, [
        "notebook", "exec", str(outside), "--code", "print(1)",
    ])

    assert result.exit_code != 0
    assert "must live under workspace" in result.output
