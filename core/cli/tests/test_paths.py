from __future__ import annotations

import os
from pathlib import Path

import pytest

from lab.paths import (
    MonorepoNotFound,
    client_env_server_port,
    configured_server_port,
    find_monorepo_root,
    workspace_dir,
    workspace_file,
    tasks_file,
)


def test_client_env_server_port_reads_lab_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LAB_ENV_FILE", raising=False)
    (tmp_path / ".env").write_text(
        "# client setting\nexport LAB_PORT='5656'\n", encoding="utf-8",
    )

    assert client_env_server_port(tmp_path) == 5656


@pytest.mark.parametrize("value", ["true", "0", "70000", "not-a-port"])
def test_client_env_server_port_rejects_invalid_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: str,
) -> None:
    monkeypatch.delenv("LAB_ENV_FILE", raising=False)
    (tmp_path / ".env").write_text(f"LAB_PORT={value}\n", encoding="utf-8")

    assert client_env_server_port(tmp_path) is None


def test_configured_server_port_reads_vault_lab_toml(tmp_path: Path) -> None:
    (tmp_path / "lab.toml").write_text(
        '[vault]\nname = "test"\n\n[server]\nport = 4545\n',
        encoding="utf-8",
    )
    assert configured_server_port(tmp_path) == 4545


@pytest.mark.parametrize("value", ["true", '"4545"', "0", "70000"])
def test_configured_server_port_rejects_invalid_values(
    tmp_path: Path, value: str,
) -> None:
    (tmp_path / "lab.toml").write_text(
        f"[server]\nport = {value}\n", encoding="utf-8",
    )
    assert configured_server_port(tmp_path) == 3333


def test_find_monorepo_root_uses_env_var(monorepo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_ROOT", str(monorepo))
    assert find_monorepo_root() == monorepo


def test_find_monorepo_root_walks_up_from_subdir(monorepo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_ROOT", raising=False)
    sub = monorepo / "workspaces"
    monkeypatch.chdir(sub)
    # macOS tmp_path is under /var → /private/var symlink; compare resolved paths.
    assert find_monorepo_root().resolve() == monorepo.resolve()


def test_find_monorepo_root_raises_when_not_in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_ROOT", raising=False)
    monkeypatch.delenv("LAB_VAULT", raising=False)
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-empty"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MonorepoNotFound):
        find_monorepo_root()


def test_workspace_dir_composes_path(monorepo: Path) -> None:
    assert workspace_dir(monorepo, "charts-vision") == monorepo / "workspaces" / "charts-vision"


def test_workspace_file_and_tasks_file(monorepo: Path) -> None:
    pdir = monorepo / "workspaces" / "charts-vision"
    assert workspace_file(monorepo, "charts-vision") == pdir / "workspace.json"
    assert tasks_file(monorepo, "charts-vision") == pdir / "tasks.json"


from lab.paths import WorkspaceNotFound, find_workspace_id_from_pwd


def test_find_workspace_id_from_pwd_inside_workspace(monorepo: Path, seed_workspace, monkeypatch) -> None:
    pdir = seed_workspace("alpha")
    monkeypatch.chdir(pdir)
    assert find_workspace_id_from_pwd(monorepo) == "alpha"


def test_find_workspace_id_from_pwd_inside_subdir(monorepo: Path, seed_workspace, monkeypatch) -> None:
    pdir = seed_workspace("alpha")
    (pdir / "docs" / "nested").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(pdir / "docs" / "nested")
    assert find_workspace_id_from_pwd(monorepo) == "alpha"


def test_find_workspace_id_from_pwd_outside_raises(monorepo: Path, monkeypatch) -> None:
    monkeypatch.chdir(monorepo)
    with pytest.raises(WorkspaceNotFound):
        find_workspace_id_from_pwd(monorepo)
