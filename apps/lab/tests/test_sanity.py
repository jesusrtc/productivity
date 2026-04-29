from pathlib import Path


def test_monorepo_fixture_creates_structure(monorepo: Path) -> None:
    assert (monorepo / "content" / "projects").is_dir()
    assert (monorepo / ".git").is_dir()


def test_seed_project_factory(seed_project) -> None:
    pdir = seed_project("hello")
    assert (pdir / "project.json").is_file()
    assert (pdir / "tasks.json").is_file()
