from __future__ import annotations

from pathlib import Path

from core import config


def test_port_uses_workspace_lab_toml(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "lab.toml").write_text(
        '[workspace]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LAB_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("LAB_PORT", raising=False)
    monkeypatch.setenv("LAB_ENV_FILE", str(tmp_path / "missing.env"))

    assert config.port() == 4545


def test_port_uses_client_env_before_workspace_lab_toml(
    tmp_path: Path, monkeypatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "lab.toml").write_text(
        '[workspace]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    client_env = tmp_path / "client.env"
    client_env.write_text("LAB_PORT=5656\n", encoding="utf-8")
    monkeypatch.setenv("LAB_WORKSPACE", str(workspace))
    monkeypatch.setenv("LAB_ENV_FILE", str(client_env))
    monkeypatch.delenv("LAB_PORT", raising=False)

    assert config.port() == 5656


def test_port_environment_override_wins(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "lab.toml").write_text(
        '[workspace]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LAB_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("LAB_PORT", "5656")

    assert config.port() == 5656
