from pathlib import Path


def test_monorepo_fixture_creates_structure(monorepo: Path) -> None:
    assert (monorepo / "workspaces").is_dir()
    assert (monorepo / ".git").is_dir()


def test_seed_workspace_factory(seed_workspace) -> None:
    pdir = seed_workspace("hello")
    assert (pdir / "workspace.json").is_file()
    assert (pdir / "tasks.json").is_file()
