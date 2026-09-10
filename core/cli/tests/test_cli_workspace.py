from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_workspace_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "--help"])
    assert result.exit_code == 0, result.output
    assert "workspace" in result.output.lower()


import json
from pathlib import Path

from lab.cli import main


def test_workspace_new_creates_directory_and_files(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "new", "charts-vision", "--desc", "Reshape Charts"])
    assert result.exit_code == 0, result.output
    pdir = monorepo / "workspaces" / "charts-vision"
    assert pdir.is_dir()
    assert (pdir / "docs").is_dir()
    assert (pdir / "notes").is_dir()
    assert (pdir / "assets").is_dir()

    workspace = json.loads((pdir / "workspace.json").read_text())
    assert workspace["id"] == "charts-vision"
    assert workspace["description"] == "Reshape Charts"
    assert workspace["status"] == "active"

    tasks = json.loads((pdir / "tasks.json").read_text())
    assert tasks == {"next_id": 1, "tasks": []}
    assert not (pdir / "AGENTS.md").exists()
    assert not (pdir / "CLAUDE.md").is_symlink()
    assert not (pdir / ".agents").exists()
    assert not (pdir / ".claude").exists()


def test_workspace_new_with_priority_due_tags_labels(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [
        "workspace", "new", "rules-rate",
        "--desc", "Rate limiter",
        "--priority", "P1",
        "--due", "2026-05-01",
        "--tags", "limits,abuse",
        "--labels", "sample-rules",
    ])
    assert result.exit_code == 0, result.output
    workspace = json.loads((monorepo / "workspaces" / "rules-rate" / "workspace.json").read_text())
    assert workspace["priority"] == "P1"
    assert workspace["due"] == "2026-05-01"
    assert workspace["tags"] == ["limits", "abuse"]
    assert workspace["labels"] == ["sample-rules"]


def test_workspace_new_rejects_duplicate(monorepo: Path, seed_workspace) -> None:
    seed_workspace("existing")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "new", "existing"])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_workspace_new_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "new", "Bad ID!"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()
    # The invalid id should never create a directory.
    assert not (monorepo / "workspaces" / "Bad ID!").exists()


def test_workspace_ls_empty(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "ls"])
    assert result.exit_code == 0
    assert "no workspaces" in result.output.lower()


def test_workspace_ls_lists_all_by_default(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    seed_workspace("beta")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "ls"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_workspace_ls_filter_by_status(monorepo: Path, seed_workspace) -> None:
    alpha = seed_workspace("alpha")
    beta = seed_workspace("beta")
    # flip beta to archived directly on disk
    data = json.loads((beta / "workspace.json").read_text())
    data["status"] = "archived"
    (beta / "workspace.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "ls", "--status", "active"])
    assert "alpha" in result.output
    assert "beta" not in result.output

    result = runner.invoke(main, ["workspace", "ls", "--status", "archived"])
    assert "beta" in result.output
    assert "alpha" not in result.output


def test_workspace_status_prints_summary(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha", description="Alpha is great")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "status", "alpha"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "Alpha is great" in result.output


def test_workspace_status_auto_detects_from_pwd(monorepo: Path, seed_workspace, monkeypatch) -> None:
    pdir = seed_workspace("beta")
    monkeypatch.chdir(pdir)
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "status"])
    assert result.exit_code == 0, result.output
    assert "beta" in result.output


def test_workspace_status_missing_workspace(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "status", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_workspace_set_updates_field(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "set", "alpha", "description", "New desc"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["description"] == "New desc"


def test_workspace_set_status(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "set", "alpha", "status", "paused"])
    assert result.exit_code == 0
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["status"] == "paused"


def test_workspace_set_rejects_bad_status(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "set", "alpha", "status", "weird"])
    assert result.exit_code != 0
    assert "not one of" in result.output.lower()


def test_workspace_set_priority_and_due(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["workspace", "set", "alpha", "priority", "P0"])
    runner.invoke(main, ["workspace", "set", "alpha", "due", "2026-05-15"])
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["priority"] == "P0"
    assert data["due"] == "2026-05-15"


def test_workspace_set_tags_and_labels_csv(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["workspace", "set", "alpha", "tags", "a,b,c"])
    runner.invoke(main, ["workspace", "set", "alpha", "labels", "sample-charts"])
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["tags"] == ["a", "b", "c"]
    assert data["labels"] == ["sample-charts"]


def test_workspace_archive(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "archive", "alpha"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["status"] == "archived"


def test_workspace_rm_requires_confirmation(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    # No confirmation → aborts
    result = runner.invoke(main, ["workspace", "rm", "alpha"], input="\n")
    assert result.exit_code != 0
    assert (monorepo / "workspaces" / "alpha").exists()


def test_workspace_rm_with_force(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "rm", "alpha", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (monorepo / "workspaces" / "alpha").exists()


def test_workspace_rm_missing(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "rm", "nope", "--yes"])
    assert result.exit_code != 0


def test_workspace_archive_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "archive", "../bad"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()


def test_workspace_rm_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "rm", "../bad", "--yes"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()


def test_workspace_archive_missing(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "archive", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_workspace_ls_filter_by_tag(monorepo: Path, seed_workspace) -> None:
    alpha = seed_workspace("alpha")
    seed_workspace("beta")
    data = json.loads((alpha / "workspace.json").read_text())
    data["tags"] = ["backend"]
    (alpha / "workspace.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "ls", "--tag", "backend"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" not in result.output


def test_workspace_ls_filter_by_label(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    beta = seed_workspace("beta")
    data = json.loads((beta / "workspace.json").read_text())
    data["labels"] = ["sample-charts"]
    (beta / "workspace.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "ls", "--label", "sample-charts"])
    assert result.exit_code == 0
    assert "beta" in result.output
    assert "alpha" not in result.output


def test_workspace_set_loe_invalid(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "set", "alpha", "loe", "not-a-number"])
    assert result.exit_code != 0
    assert "not a number" in result.output.lower()


def test_workspace_new_is_atomic_on_failure(monorepo: Path, monkeypatch) -> None:
    """If storage.write_json fails mid-creation, no partial pdir is left behind."""
    import lab.storage as storage_mod
    original_write = storage_mod.write_json
    calls = {"n": 0}

    def flaky(path, data):
        calls["n"] += 1
        if calls["n"] == 2:  # fail on the second write (tasks.json)
            raise OSError("disk went away")
        return original_write(path, data)

    monkeypatch.setattr(storage_mod, "write_json", flaky)

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "new", "doomed", "--desc", "test"])
    assert result.exit_code != 0
    assert not (monorepo / "workspaces" / "doomed").exists()


def test_workspace_add_missing_mp(monorepo, seed_workspace, monkeypatch) -> None:
    """Missing repositories report the explicit Git setup step."""
    seed_workspace("charts-test")

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "add", "charts-test", "sample-charts"])
    assert result.exit_code != 0
    assert "repositories" in result.output.lower() or "not found" in result.output.lower()


def test_workspace_add_unknown_prefix(monorepo, seed_workspace, tmp_path, monkeypatch) -> None:
    seed_workspace("charts-test")
    # Create a fake MP dir that looks like a git repo
    mp_dir = monorepo / "repositories" / "some-mp"
    mp_dir.mkdir(parents=True)
    (mp_dir / ".git").mkdir()
    # Point the prefix config at a clean temp location (no preset prefix)
    import lab.mp as mp_mod
    fake = tmp_path / "mp.json"
    monkeypatch.setattr(mp_mod, "_CONFIG_FILE", fake)
    mp_mod.save_prefixes({})
    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "add", "charts-test", "some-mp"])
    assert result.exit_code != 0
    assert "prefix" in result.output.lower()


def test_workspace_add_stores_worktrees_subfolder_path(monorepo, seed_workspace, tmp_path,
                                                        monkeypatch) -> None:
    """New layout: dir should be stored as ``worktrees/<name>`` and the
    worktree lives at ``<workspace>/worktrees/<name>``."""
    seed_workspace("alpha")
    mp_dir = monorepo / "repositories" / "some-mp"
    mp_dir.mkdir(parents=True)
    (mp_dir / ".git").mkdir()
    import lab.mp as mp_mod
    fake = tmp_path / "mp.json"
    monkeypatch.setattr(mp_mod, "_CONFIG_FILE", fake)
    mp_mod.save_prefixes({"some-mp": "sm"})

    # Stub subprocess.run so we don't need a real git repo underneath.
    import subprocess as sp
    real_run = sp.run

    def fake_run(cmd, *a, **kw):
        if isinstance(cmd, list) and "worktree" in cmd and "add" in cmd:
            # The worktree "add" call takes the destination path from argv.
            try:
                i = cmd.index("add")
                # destination is either cmd[i+1] (if no -b) or cmd[i+3] (with -b branch)
                dst = cmd[i + 3] if "-b" in cmd[i + 1:i + 3] else cmd[i + 1]
                from pathlib import Path as _P
                _P(dst).mkdir(parents=True, exist_ok=True)
                (_P(dst) / ".git").write_text("gitdir: ../../../repositories/some-mp/.git/worktrees/x")
            except Exception:
                pass
            class R: returncode = 0; stdout = ""; stderr = ""
            return R()
        # `rev-parse --verify` → say the branch doesn't exist so we hit the -b path.
        if isinstance(cmd, list) and "rev-parse" in cmd:
            raise sp.CalledProcessError(1, cmd, output="", stderr="")
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(sp, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "add", "alpha", "some-mp"])
    assert result.exit_code == 0, result.output

    pdir = monorepo / "workspaces" / "alpha"
    data = json.loads((pdir / "workspace.json").read_text())
    assert len(data["worktrees"]) == 1
    wt = data["worktrees"][0]
    assert wt["dir"].startswith("worktrees/"), f"expected subfolder layout, got {wt['dir']!r}"
    assert (pdir / wt["dir"]).is_dir()


def test_workspace_remove_force_flag(monorepo, seed_workspace, monkeypatch) -> None:
    """--force should pass through to `git worktree remove --force`."""
    seed_workspace("alpha")
    pdir = monorepo / "workspaces" / "alpha"
    # Seed a worktree entry + the dir (pretend git already set it up).
    data = json.loads((pdir / "workspace.json").read_text())
    data["worktrees"] = [{"mp": "some-mp", "dir": "worktrees/sm-alpha", "branch": "x"}]
    (pdir / "worktrees" / "sm-alpha").mkdir(parents=True)
    (monorepo / "repositories" / "some-mp").mkdir(parents=True)
    (pdir / "workspace.json").write_text(json.dumps(data))

    captured: list[list[str]] = []
    import subprocess as sp

    def fake_run(cmd, *a, **kw):
        captured.append(list(cmd))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr(sp, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["workspace", "remove", "alpha", "some-mp", "--force"])
    assert result.exit_code == 0, result.output

    # Find the `git worktree remove` call and assert --force was included.
    removes = [c for c in captured if "worktree" in c and "remove" in c]
    assert removes and "--force" in removes[0], f"expected --force in {removes}"


def test_pr_add_and_ls(monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    r = runner.invoke(main, [
        "pr", "add", "https://example/pr/1", "--workspace", "alpha",
        "--mp", "sample-charts", "--title", "test pr",
    ])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["pr", "ls", "--workspace", "alpha"])
    assert "https://example/pr/1" in r.output

    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert data["prs"][0]["url"] == "https://example/pr/1"
    assert data["prs"][0]["mp"] == "sample-charts"


def test_pr_rm(monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["pr", "add", "https://x/1", "--workspace", "alpha"])
    runner.invoke(main, ["pr", "add", "https://x/2", "--workspace", "alpha"])
    r = runner.invoke(main, ["pr", "rm", "0", "--workspace", "alpha"])
    assert r.exit_code == 0
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert [p["url"] for p in data["prs"]] == ["https://x/2"]


def test_artifact_add_and_ls(monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    r = runner.invoke(main, [
        "artifact", "add", "https://docs/abc", "--workspace", "alpha",
        "--type", "google_doc", "--title", "Design doc",
    ])
    assert r.exit_code == 0, r.output
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    a = data["artifacts"][0]
    assert a["type"] == "google_doc"
    assert a["title"] == "Design doc"
    assert a["id"] == 1


def test_artifact_rm_by_id(monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["artifact", "add", "https://a", "--workspace", "alpha"])
    runner.invoke(main, ["artifact", "add", "https://b", "--workspace", "alpha"])
    r = runner.invoke(main, ["artifact", "rm", "1", "--workspace", "alpha"])
    assert r.exit_code == 0
    data = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert [a["url"] for a in data["artifacts"]] == ["https://b"]
