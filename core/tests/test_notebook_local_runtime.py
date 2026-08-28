from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import core.notebook_kernel as notebook_kernel
import core.notebook_runtime as notebook_runtime
from core.notebook_runtime import ProjectRuntimeSpec, runtime_fingerprint


def _project_with_cli(monorepo: Path) -> tuple[str, Path]:
    rel = "projects/demo/notebooks/analysis.ipynb"
    project = monorepo / "projects" / "demo"
    (project / "notebooks").mkdir(parents=True, exist_ok=True)
    tools = project / "tools"
    tools.mkdir()
    cli = tools / "client-tool"
    cli.write_text("#!/bin/sh\nprintf 'client-cli-ok\\n'\n", encoding="utf-8")
    cli.chmod(cli.stat().st_mode | 0o111)
    (project / "clientlib.py").write_text(
        "import subprocess\n\n"
        "def cli_value():\n"
        "    return subprocess.check_output(['client-tool'], text=True).strip()\n",
        encoding="utf-8",
    )
    return rel, project


def _existing_spec() -> dict:
    return {
        "version": 1,
        "mode": "local",
        "kind": "existing",
        "python": sys.executable,
        "packages": [],
        "editable": [],
        "imports": ["clientlib"],
        "cli_paths": ["tools"],
        "cli_checks": [{"command": "client-tool", "args": [], "timeout": 10}],
        "environment": {"LAB_RUNTIME_TEST": "configured"},
        "working_dir": ".",
        "validation_code": "assert os.environ['LAB_RUNTIME_TEST'] == 'configured'",
    }


def test_runtime_fingerprint_is_stable_and_configuration_sensitive() -> None:
    first = ProjectRuntimeSpec(python="3.12", packages=["pandas==2.3.2"])
    same = ProjectRuntimeSpec.model_validate(first.model_dump())
    changed = ProjectRuntimeSpec(python="3.12", packages=["pandas==2.3.3"])
    assert runtime_fingerprint(first) == runtime_fingerprint(same)
    assert runtime_fingerprint(first) != runtime_fingerprint(changed)


def test_managed_runtime_build_installs_pins_and_editable_libraries(
    tmp_path: Path, monkeypatch
) -> None:
    root = tmp_path / "workspace"
    project = root / "projects" / "managed"
    (project / "notebooks").mkdir(parents=True)
    (project / "libs" / "client_sdk").mkdir(parents=True)
    rel = "projects/managed/notebooks/analysis.ipynb"
    spec = ProjectRuntimeSpec(
        mode="local",
        kind="managed",
        python=sys.executable,
        packages=["pandas==2.3.2", "client-wheel>=4"],
        editable=["libs/client_sdk"],
        imports=["pandas"],
    )
    notebook_runtime.save_runtime_spec(root, rel, spec)
    commands: list[list[str]] = []

    def fake_run(command, *, cwd, env, log, timeout=900):
        commands.append(list(command))
        if command[1:3] == ["-m", "venv"]:
            python = Path(command[-1]) / "bin" / "python"
            python.parent.mkdir(parents=True)
            python.write_text("fake python", encoding="utf-8")

    def fake_validation(handle, code, timeout=120):
        assert handle.python.endswith("/venv/bin/python")
        assert "__import__('pandas')" in code
        return {
            "output": "",
            "kernel_id": "validation",
            "execution_count": 1,
            "cell_outputs": [],
        }

    monkeypatch.setattr(notebook_runtime, "_run_logged", fake_run)
    monkeypatch.setattr(notebook_kernel, "execute_ephemeral", fake_validation)
    built = notebook_runtime.build_runtime(root, rel)

    assert built["status"] == "ready"
    install = next(command for command in commands if command[1:4] == ["-m", "pip", "install"])
    assert "ipykernel>=6.29,<8" in install
    assert "pandas==2.3.2" in install
    assert "client-wheel>=4" in install
    editable = next(command for command in commands if "-e" in command)
    assert editable[-1] == str((project / "libs" / "client_sdk").resolve())


def test_runtime_api_saves_project_owned_config(client, monorepo: Path) -> None:
    rel, project = _project_with_cli(monorepo)
    before = client.get(f"/api/nb/runtime?path={rel}")
    assert before.status_code == 200
    assert before.json()["status"] == "legacy"

    response = client.put("/api/nb/runtime", json={"path": rel, "spec": _existing_spec()})
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "draft"
    assert response.json()["config_path"] == "projects/demo/runtime.json"
    saved = json.loads((project / "runtime.json").read_text(encoding="utf-8"))
    assert saved["python"] == sys.executable
    assert saved["cli_paths"] == ["tools"]


def test_local_jupyter_shared_human_agent_workflow_and_cli(
    client, monorepo: Path
) -> None:
    """A person and an agent share state, notebook persistence, and CLI PATH.

    This intentionally launches a real ipykernel rather than mocking the
    executor. It proves that a client library can invoke its own CLI from the
    exact Jupyter process Lab supplies.
    """
    rel, project = _project_with_cli(monorepo)
    saved = client.put("/api/nb/runtime", json={"path": rel, "spec": _existing_spec()})
    assert saved.status_code == 200, saved.text

    built = client.post("/api/nb/runtime/build", json={"path": rel})
    assert built.status_code == 200, built.text
    build_body = built.json()
    assert build_body["runtime"]["status"] == "ready"
    assert build_body["built"]["python"] == sys.executable
    # The state endpoint must never echo the Lab server's entire environment.
    assert "environment" not in build_body["built"]

    session = client.get(f"/api/nb/session?path={rel}")
    assert session.status_code == 200
    assert session.json()["provider"] == "local"
    assert "interrupt" in session.json()["capabilities"]

    human = client.post("/api/nb/exec", json={
        "path": rel,
        "actor": "human",
        "code": "import os\nshared_value = 40\nprint(os.environ['LAB_RUNTIME_TEST'])",
    })
    assert human.status_code == 200, human.text
    assert human.json()["provider"] == "local"
    assert "configured" in "\n".join(
        output.get("content", "") for output in human.json()["cell"]["outputs"]
    )

    agent = client.post("/api/nb/exec", json={
        "path": rel,
        "actor": "agent",
        "code": "from clientlib import cli_value\nprint(shared_value + 2, cli_value())",
    })
    assert agent.status_code == 200, agent.text
    agent_text = "\n".join(
        output.get("content", "") for output in agent.json()["cell"]["outputs"]
    )
    assert "42 client-cli-ok" in agent_text

    notebook = json.loads((monorepo / rel).read_text(encoding="utf-8"))
    assert [cell["metadata"]["lab_actor"] for cell in notebook["cells"]] == [
        "human", "agent"
    ]
    assert all(cell.get("id") for cell in notebook["cells"])

    # Stable ids let the UI rerun a cell after an agent inserts elsewhere.
    first_id = notebook["cells"][0]["id"]
    rerun = client.post("/api/nb/exec", json={
        "path": rel,
        "actor": "human",
        "cell_id": first_id,
        "code": "shared_value = 50\nprint('rerun')",
    })
    assert rerun.status_code == 200, rerun.text
    assert rerun.json()["cell_index"] == 0

    restarted = client.post("/api/nb/session/restart", json={"path": rel})
    assert restarted.status_code == 200, restarted.text
    missing_state = client.post("/api/nb/exec", json={
        "path": rel, "actor": "agent", "code": "print(shared_value)",
    })
    assert missing_state.status_code == 200, missing_state.text
    assert any(out["type"] == "error" for out in missing_state.json()["cell"]["outputs"])


def test_local_runtime_requires_build_before_exec(client, monorepo: Path) -> None:
    rel, _ = _project_with_cli(monorepo)
    saved = client.put("/api/nb/runtime", json={"path": rel, "spec": _existing_spec()})
    assert saved.status_code == 200
    response = client.post("/api/nb/exec", json={"path": rel, "code": "1 + 1"})
    assert response.status_code == 409
    assert "built" in response.json()["detail"].lower()


def test_local_kernel_interrupt_stops_a_running_cell(client, monorepo: Path) -> None:
    rel, _ = _project_with_cli(monorepo)
    assert client.put(
        "/api/nb/runtime", json={"path": rel, "spec": _existing_spec()}
    ).status_code == 200
    built = client.post("/api/nb/runtime/build", json={"path": rel})
    assert built.status_code == 200, built.text

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(
            client.post,
            "/api/nb/exec",
            json={
                "path": rel,
                "actor": "human",
                "timeout": 30,
                "code": "import time\ntime.sleep(30)\nprint('should not finish')",
            },
        )
        deadline = time.monotonic() + 10
        notebook_path = monorepo / rel
        while time.monotonic() < deadline:
            if notebook_path.is_file() and "lab_pending" in notebook_path.read_text():
                break
            time.sleep(0.05)
        interrupted = client.post("/api/nb/session/interrupt", json={"path": rel})
        assert interrupted.status_code == 200, interrupted.text
        assert interrupted.json()["interrupted"] is True
        completed = running.result(timeout=10)

    assert completed.status_code == 200, completed.text
    outputs = completed.json()["cell"]["outputs"]
    assert any(
        output["type"] == "error" and "KeyboardInterrupt" in output["content"]
        for output in outputs
    )


def test_runtime_reports_missing_working_directory(client, monorepo: Path) -> None:
    rel, _ = _project_with_cli(monorepo)
    spec = _existing_spec()
    spec["working_dir"] = "missing-directory"
    saved = client.put("/api/nb/runtime", json={"path": rel, "spec": spec})
    assert saved.status_code == 200
    built = client.post("/api/nb/runtime/build", json={"path": rel})
    assert built.status_code == 422
    detail = built.json()["detail"]
    assert "working directory does not exist" in detail["message"]


def test_revalidation_detects_a_client_cli_removed_in_place(
    client, monorepo: Path
) -> None:
    rel, project = _project_with_cli(monorepo)
    assert client.put(
        "/api/nb/runtime", json={"path": rel, "spec": _existing_spec()}
    ).status_code == 200
    first = client.post("/api/nb/runtime/build", json={"path": rel})
    assert first.status_code == 200, first.text

    (project / "tools" / "client-tool").unlink()
    revalidated = client.post("/api/nb/runtime/build", json={"path": rel})
    assert revalidated.status_code == 422, revalidated.text
    assert "CLI not found" in revalidated.json()["detail"]["message"]
    status = client.get(f"/api/nb/runtime?path={rel}").json()
    assert status["status"] == "broken"
    blocked = client.post("/api/nb/exec", json={"path": rel, "code": "1 + 1"})
    assert blocked.status_code == 409
