from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import core.notebook_kernel as notebook_kernel
import core.notebook_runtime as notebook_runtime
import pytest
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


def test_cancelled_http_execution_interrupts_and_drains_kernel_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.release = threading.Event()
            self.interrupted = False

        def interrupt(self) -> bool:
            self.interrupted = True
            self.release.set()
            return True

    class FakeSession:
        session_id = "local-cancel-test"

        def __init__(self) -> None:
            self.process = FakeProcess()
            self.started = asyncio.Event()
            self.finished = False
            self.requests = 0

        def begin_request(self) -> None:
            self.requests += 1

        def end_request(self) -> None:
            self.requests -= 1

        async def call(self, method, code, timeout, emit):
            assert method == "execute"
            self.started.set()
            await asyncio.to_thread(self.process.release.wait)
            self.finished = True
            return {"cell_outputs": [], "execution_count": 1, "kernel_id": "fake"}

    session = FakeSession()
    monkeypatch.setattr(notebook_kernel, "_session_for", lambda *args: session)
    handle = notebook_runtime.RuntimeHandle(
        project_id="demo",
        python=sys.executable,
        working_dir=str(tmp_path),
        environment={},
        fingerprint="fake",
        display_name="Fake",
    )

    async def exercise() -> None:
        task = asyncio.create_task(
            notebook_kernel.execute(tmp_path, "cancel.ipynb", handle, "pass", 30)
        )
        await session.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
    assert session.process.interrupted is True
    assert session.finished is True
    assert session.requests == 0


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
        "code": "import os, time\ntime.sleep(1.2)\nshared_value = 40\nprint(os.environ['LAB_RUNTIME_TEST'])",
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
    assert [cell["metadata"]["lab_action"] for cell in notebook["cells"]] == [
        "created", "created"
    ]
    for cell in notebook["cells"]:
        metadata = cell["metadata"]
        assert metadata["lab_started_at"] <= metadata["lab_finished_at"]
        assert metadata["lab_duration_ms"] >= 0
    assert notebook["cells"][0]["metadata"]["lab_duration_ms"] >= 1000
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
    rerun_metadata = rerun.json()["cell"]["metadata"]
    assert rerun_metadata["lab_actor"] == "human"
    assert rerun_metadata["lab_action"] == "modified"
    assert rerun_metadata["lab_duration_ms"] >= 0
    rerun_notebook = json.loads((monorepo / rel).read_text(encoding="utf-8"))
    assert rerun_notebook["cells"][0]["id"] == first_id

    restarted = client.post("/api/nb/session/restart", json={"path": rel})
    assert restarted.status_code == 200, restarted.text
    missing_state = client.post("/api/nb/exec", json={
        "path": rel, "actor": "agent", "code": "print(shared_value)",
    })
    assert missing_state.status_code == 200, missing_state.text
    assert any(out["type"] == "error" for out in missing_state.json()["cell"]["outputs"])


def test_agent_api_shows_running_state_and_streams_output_before_completion(
    client, monorepo: Path
) -> None:
    rel, _ = _project_with_cli(monorepo)
    assert client.put(
        "/api/nb/runtime", json={"path": rel, "spec": _existing_spec()}
    ).status_code == 200
    built = client.post("/api/nb/runtime/build", json={"path": rel})
    assert built.status_code == 200, built.text

    code = (
        "import time\n"
        "from IPython.display import HTML, display\n"
        "print('stream-chunk-1', flush=True)\n"
        "time.sleep(1.2)\n"
        "print('stream-chunk-2', flush=True)\n"
        "time.sleep(0.4)\n"
        "chart = display(HTML(\"<div id='live-chart'>first</div>\"), display_id=True)\n"
        "time.sleep(0.2)\n"
        "chart.update(HTML(\"<div id='live-chart'>final</div>\"))\n"
    )
    events: list[dict] = []
    saw_started_while_running = False
    streamed_chunks: list[str] = []
    with client.websocket_connect("/ws") as ws:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(
                client.post,
                "/api/nb/exec",
                json={"path": rel, "actor": "agent", "code": code},
            )
            while True:
                event = ws.receive_json()
                if event.get("type") != "notebook-execution" or event.get("path") != rel:
                    continue
                events.append(event)
                if event.get("phase") == "started":
                    saw_started_while_running = not running.done()
                    assert event["actor"] == "agent"
                    assert event["source"] == code
                    assert event["started_at"] <= time.time()

                    live = client.get(f"/api/nb/live?path={rel}")
                    assert live.status_code == 200, live.text
                    snapshots = live.json()["executions"]
                    assert len(snapshots) == 1
                    snapshot = snapshots[0]
                    assert snapshot["run_id"] == event["run_id"]
                    assert snapshot["actor"] == "agent"
                    assert snapshot["source"] == code
                    assert snapshot["started_at"] == event["started_at"]

                    notebook = json.loads(
                        (monorepo / rel).read_text(encoding="utf-8")
                    )
                    pending = notebook["cells"][0]
                    assert pending["metadata"]["lab_pending"] is True
                    assert pending["metadata"]["lab_actor"] == "agent"
                    assert pending["metadata"]["lab_run_id"] == event["run_id"]

                content = (event.get("output") or {}).get("content", "")
                if "stream-chunk-1" in content:
                    assert running.done() is False
                    streamed_chunks.append("stream-chunk-1")
                    live = client.get(f"/api/nb/live?path={rel}")
                    assert live.status_code == 200, live.text
                    snapshots = live.json()["executions"]
                    assert len(snapshots) == 1
                    assert any(
                        "stream-chunk-1" in output.get("content", "")
                        for output in snapshots[0]["outputs"]
                    )
                    assert not any(
                        "stream-chunk-2" in output.get("content", "")
                        for output in snapshots[0]["outputs"]
                    )
                if "stream-chunk-2" in content:
                    assert running.done() is False
                    streamed_chunks.append("stream-chunk-2")
                if event.get("phase") in {"finished", "failed", "interrupted"}:
                    break
            completed = running.result(timeout=10)

    assert completed.status_code == 200, completed.text
    assert saw_started_while_running is True
    assert streamed_chunks == ["stream-chunk-1", "stream-chunk-2"]
    assert events[0]["phase"] == "started"
    assert events[-1]["phase"] == "finished"
    assert all(event["actor"] == "agent" for event in events)
    sequenced = [event["sequence"] for event in events if "sequence" in event]
    assert sequenced == sorted(set(sequenced))
    assert any(
        event.get("phase") == "output"
        and (event.get("output") or {}).get("type") == "html"
        and event.get("operation") == "append"
        for event in events
    )
    assert any(
        event.get("phase") == "output"
        and "final" in (event.get("output") or {}).get("content", "")
        and event.get("operation") == "replace"
        for event in events
    )
    assert client.get(f"/api/nb/live?path={rel}").json()["executions"] == []

    cell = completed.json()["cell"]
    final_text = "\n".join(out.get("content", "") for out in cell["outputs"])
    assert "stream-chunk-1" in final_text
    assert "stream-chunk-2" in final_text
    html_outputs = [out for out in cell["outputs"] if out.get("type") == "html"]
    assert len(html_outputs) == 1
    assert "final" in html_outputs[0]["content"]
    assert "first" not in html_outputs[0]["content"]


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

    terminal_event = None
    with client.websocket_connect("/ws") as ws:
        with ThreadPoolExecutor(max_workers=1) as pool:
            running = pool.submit(
                client.post,
                "/api/nb/exec",
                json={
                    "path": rel,
                    "actor": "human",
                    "timeout": 30,
                    "code": (
                        "import time\n"
                        "print('before interrupt', flush=True)\n"
                        "time.sleep(30)\n"
                        "print('should not finish')"
                    ),
                },
            )
            while True:
                event = ws.receive_json()
                if event.get("type") != "notebook-execution" or event.get("path") != rel:
                    continue
                if "before interrupt" in (event.get("output") or {}).get("content", ""):
                    assert running.done() is False
                    break

            notebook_path = monorepo / rel
            pending = json.loads(notebook_path.read_text(encoding="utf-8"))["cells"][0]
            assert pending["metadata"]["lab_actor"] == "human"
            assert pending["metadata"]["lab_action"] == "created"
            assert pending["metadata"]["lab_started_at"] <= time.time()

            interrupted = client.post("/api/nb/session/interrupt", json={"path": rel})
            assert interrupted.status_code == 200, interrupted.text
            assert interrupted.json()["interrupted"] is True
            while terminal_event is None:
                event = ws.receive_json()
                if event.get("type") != "notebook-execution" or event.get("path") != rel:
                    continue
                if event.get("phase") in {"finished", "failed", "interrupted"}:
                    terminal_event = event
            completed = running.result(timeout=10)

    assert completed.status_code == 200, completed.text
    assert terminal_event["phase"] == "interrupted"
    outputs = completed.json()["cell"]["outputs"]
    assert any("before interrupt" in output.get("content", "") for output in outputs)
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
