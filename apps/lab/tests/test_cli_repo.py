from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_repo_ls_no_repositories_dir(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["repo", "ls"])
    assert result.exit_code == 0
    assert "no repositories" in result.output.lower()


def test_repo_ls_empty(monorepo: Path) -> None:
    (monorepo / "repositories").mkdir()
    runner = CliRunner()
    result = runner.invoke(main, ["repo", "ls"])
    assert result.exit_code == 0
    assert "no repos cloned" in result.output.lower()


def test_repo_ls_with_fake_repo(monorepo: Path) -> None:
    (monorepo / "repositories" / "lipy-davi" / ".git").mkdir(parents=True)
    runner = CliRunner()
    result = runner.invoke(main, ["repo", "ls"])
    assert result.exit_code == 0
    assert "lipy-davi" in result.output
    assert "davi" in result.output  # the prefix


def test_repo_pull_errors_without_list_or_only(monorepo: Path) -> None:
    # No clones on disk and no repositories.list → friendly error.
    runner = CliRunner()
    result = runner.invoke(main, ["repo", "pull"])
    assert result.exit_code != 0
    assert "no clones" in result.output.lower()
    assert "repositories.list" in result.output


def test_repo_pull_reads_list(monorepo: Path, monkeypatch) -> None:
    """With a list file + a pre-cloned repo, pull just runs `git checkout/pull`."""
    (monorepo / "repositories" / "fake-repo").mkdir(parents=True)
    # Make it look like a git repo so `git checkout` / `git pull` don't
    # complain about missing .git. The `git` calls will still fail on HEAD —
    # we just want to verify the code path runs, not that git succeeds.
    (monorepo / "repositories" / "fake-repo" / ".git").mkdir()
    (monorepo / "repositories.list").write_text("fake-repo\n")

    # Stub subprocess.run so git is a no-op (returncode 0).
    import subprocess as sp

    class Fake:
        def __init__(self, *a, **kw): pass
        returncode = 0
        stderr = ""
        stdout = ""
    monkeypatch.setattr(sp, "run", lambda *a, **kw: Fake())

    runner = CliRunner()
    result = runner.invoke(main, ["repo", "pull"])
    assert result.exit_code == 0, result.output
    assert "fake-repo" in result.output


def test_repo_pull_picks_up_disk_repo_missing_from_list(
    monorepo: Path, monkeypatch
) -> None:
    """A clone present on disk but missing from repositories.list still gets
    pulled, and the list is rewritten to mirror disk."""
    (monorepo / "repositories" / "in-list" / ".git").mkdir(parents=True)
    (monorepo / "repositories" / "extra-on-disk" / ".git").mkdir(parents=True)
    (monorepo / "repositories.list").write_text("in-list\n")

    import subprocess as sp

    class Fake:
        def __init__(self, *a, **kw): pass
        returncode = 0
        stderr = ""
        stdout = "HEAD branch: main\n"
    monkeypatch.setattr(sp, "run", lambda *a, **kw: Fake())

    runner = CliRunner()
    result = runner.invoke(main, ["repo", "pull"])
    assert result.exit_code == 0, result.output
    assert "in-list" in result.output
    assert "extra-on-disk" in result.output

    rewritten = (monorepo / "repositories.list").read_text().splitlines()
    assert rewritten == ["extra-on-disk", "in-list"]


def test_repo_pull_drops_removed_repos_from_list(
    monorepo: Path, monkeypatch
) -> None:
    """A repo in the list but not on disk is treated as removed: not
    re-cloned, and dropped from the list."""
    (monorepo / "repositories" / "still-here" / ".git").mkdir(parents=True)
    (monorepo / "repositories.list").write_text("still-here\nrm-by-user\n")

    import subprocess as sp

    class Fake:
        def __init__(self, *a, **kw): pass
        returncode = 0
        stderr = ""
        stdout = "HEAD branch: main\n"
    monkeypatch.setattr(sp, "run", lambda *a, **kw: Fake())

    runner = CliRunner()
    result = runner.invoke(main, ["repo", "pull"])
    assert result.exit_code == 0, result.output
    assert "rm-by-user" not in result.output

    rewritten = (monorepo / "repositories.list").read_text().splitlines()
    assert rewritten == ["still-here"]


def test_repo_prefix_sets_new(monorepo: Path, tmp_path, monkeypatch) -> None:
    # Point the config file at a temp location to avoid clobbering the seed
    import lab.mp as mp_mod
    fake = tmp_path / "mp.json"
    monkeypatch.setattr(mp_mod, "_CONFIG_FILE", fake)
    mp_mod.save_prefixes({})  # start clean
    runner = CliRunner()
    result = runner.invoke(main, ["repo", "prefix", "myrepo", "my"])
    assert result.exit_code == 0
    assert mp_mod.load_prefixes() == {"myrepo": "my"}
