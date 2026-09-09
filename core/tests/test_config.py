from __future__ import annotations

from pathlib import Path

from core import config


def test_port_uses_vault_lab_toml(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "lab.toml").write_text(
        '[vault]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LAB_VAULT", str(tmp_path))
    monkeypatch.delenv("LAB_PORT", raising=False)
    monkeypatch.setenv("LAB_ENV_FILE", str(tmp_path / "missing.env"))

    assert config.port() == 4545


def test_port_uses_client_env_before_vault_lab_toml(
    tmp_path: Path, monkeypatch,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "lab.toml").write_text(
        '[vault]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    client_env = tmp_path / "client.env"
    client_env.write_text("LAB_PORT=5656\n", encoding="utf-8")
    monkeypatch.setenv("LAB_VAULT", str(vault))
    monkeypatch.setenv("LAB_ENV_FILE", str(client_env))
    monkeypatch.delenv("LAB_PORT", raising=False)

    assert config.port() == 5656


def test_port_environment_override_wins(
    tmp_path: Path, monkeypatch,
) -> None:
    (tmp_path / "lab.toml").write_text(
        '[vault]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("LAB_VAULT", str(tmp_path))
    monkeypatch.setenv("LAB_PORT", "5656")

    assert config.port() == 5656
