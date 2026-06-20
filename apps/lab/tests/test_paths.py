from __future__ import annotations

import os
from pathlib import Path

import pytest

from lab.paths import (
    MonorepoNotFound,
    find_monorepo_root,
    project_dir,
    project_file,
    tasks_file,
)


def test_find_monorepo_root_uses_env_var(monorepo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAB_ROOT", str(monorepo))
    assert find_monorepo_root() == monorepo


def test_find_monorepo_root_walks_up_from_subdir(monorepo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_ROOT", raising=False)
    sub = monorepo / "projects"
    monkeypatch.chdir(sub)
    # macOS tmp_path is under /var → /private/var symlink; compare resolved paths.
    assert find_monorepo_root().resolve() == monorepo.resolve()


def test_find_monorepo_root_raises_when_not_in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MonorepoNotFound):
        find_monorepo_root()


def test_project_dir_composes_path(monorepo: Path) -> None:
    assert project_dir(monorepo, "davi-vision") == monorepo / "projects" / "davi-vision"


def test_project_file_and_tasks_file(monorepo: Path) -> None:
    pdir = monorepo / "projects" / "davi-vision"
    assert project_file(monorepo, "davi-vision") == pdir / "project.json"
    assert tasks_file(monorepo, "davi-vision") == pdir / "tasks.json"


from lab.paths import ProjectNotFound, find_project_id_from_pwd


def test_find_project_id_from_pwd_inside_project(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("alpha")
    monkeypatch.chdir(pdir)
    assert find_project_id_from_pwd(monorepo) == "alpha"


def test_find_project_id_from_pwd_inside_subdir(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "nested").mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(pdir / "docs" / "nested")
    assert find_project_id_from_pwd(monorepo) == "alpha"


def test_find_project_id_from_pwd_outside_raises(monorepo: Path, monkeypatch) -> None:
    monkeypatch.chdir(monorepo)
    with pytest.raises(ProjectNotFound):
        find_project_id_from_pwd(monorepo)
