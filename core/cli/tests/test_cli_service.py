from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_start_invokes_make(monkeypatch, tmp_path: Path) -> None:
    called: list[dict] = []
    workspace = tmp_path / "workspace"
    framework = tmp_path / "framework"
    workspace.mkdir()
    (workspace / "lab.toml").write_text("[workspace]\nname = \"workspace\"\n")
    framework.mkdir()
    monkeypatch.setattr("lab.commands.service.paths.find_workspace_root", lambda: workspace)
    monkeypatch.setattr("lab.commands.service.paths.find_framework_root", lambda: framework)
    monkeypatch.setattr("lab.commands.service.paths.register_workspace", lambda *a, **k: {})

    def fake_run(cmd, check, cwd=None, env=None):
        called.append({"cmd": cmd, "cwd": cwd, "env": env})
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["start"])
    assert result.exit_code == 0, result.output
    assert called and called[0]["cmd"][:2] == ["make", "start-bg"]
    assert called[0]["cwd"] == str(framework)
    assert called[0]["env"]["LAB_WORKSPACE"] == str(workspace)


def test_start_accepts_port(monkeypatch, tmp_path: Path) -> None:
    called: list[dict] = []
    workspace = tmp_path / "workspace"
    framework = tmp_path / "framework"
    workspace.mkdir()
    (workspace / "lab.toml").write_text("[workspace]\nname = \"workspace\"\n")
    framework.mkdir()
    monkeypatch.setattr("lab.commands.service.paths.find_workspace_root", lambda: workspace)
    monkeypatch.setattr("lab.commands.service.paths.find_framework_root", lambda: framework)
    monkeypatch.setattr("lab.commands.service.paths.register_workspace", lambda *a, **k: {})

    def fake_run(cmd, check, cwd=None, env=None):
        called.append({"cmd": cmd, "cwd": cwd, "env": env})
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["start", "--port", "8090"])
    assert result.exit_code == 0, result.output
    assert called[0]["cmd"] == ["make", "start-bg", "PORT=8090"]
    assert called[0]["env"]["LAB_PORT"] == "8090"


def test_start_dev_sets_dev_mode(monkeypatch, tmp_path: Path) -> None:
    called: list[dict] = []
    workspace = tmp_path / "workspace"
    framework = tmp_path / "framework"
    workspace.mkdir()
    (workspace / "lab.toml").write_text("[workspace]\nname = \"workspace\"\n")
    framework.mkdir()
    monkeypatch.setattr("lab.commands.service.paths.find_workspace_root", lambda: workspace)
    monkeypatch.setattr("lab.commands.service.paths.find_framework_root", lambda: framework)
    monkeypatch.setattr("lab.commands.service.paths.register_workspace", lambda *a, **k: {})

    def fake_run(cmd, check, cwd=None, env=None):
        called.append({"cmd": cmd, "cwd": cwd, "env": env})
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["start", "--dev"])
    assert result.exit_code == 0, result.output
    assert called[0]["env"]["LAB_DEV_MODE"] == "1"


def test_start_rejects_uninitialized_workspace(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr("lab.commands.service.paths.find_workspace_root", lambda: workspace)

    result = CliRunner().invoke(main, ["start"])

    assert result.exit_code != 0
    assert "lab init" in result.output


def test_stop_invokes_make(monkeypatch, tmp_path: Path) -> None:
    called: list[list[str]] = []
    framework = tmp_path / "framework"
    framework.mkdir()
    monkeypatch.setattr("lab.commands.service.paths.find_framework_root", lambda: framework)

    def fake_run(cmd, check, cwd=None):
        called.append(cmd)
        class R:
            returncode = 0
        return R()

    monkeypatch.setattr("lab.commands.service.subprocess.run", fake_run)
    result = CliRunner().invoke(main, ["stop"])
    assert result.exit_code == 0
    assert called and called[0][:2] == ["make", "stop"]


def test_open_calls_webbrowser(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("lab.commands.service.webbrowser.open", lambda u: opened.append(u))
    # Pin to the legacy default so we don't depend on a running .lab-server.port.
    monkeypatch.setenv("LAB_PORT", "3333")
    result = CliRunner().invoke(main, ["open"])
    assert result.exit_code == 0
    assert opened == ["http://localhost:3333/api/index"]


def test_open_respects_custom_port(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr("lab.commands.service.webbrowser.open", lambda u: opened.append(u))
    monkeypatch.setenv("LAB_PORT", "4444")
    result = CliRunner().invoke(main, ["open"])
    assert result.exit_code == 0
    assert opened == ["http://localhost:4444/api/index"]
