from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_project_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "--help"])
    assert result.exit_code == 0, result.output
    assert "project" in result.output.lower()


import json
from pathlib import Path

from lab.cli import main


def test_project_new_creates_directory_and_files(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "new", "davi-vision", "--desc", "Reshape DAVI"])
    assert result.exit_code == 0, result.output
    pdir = monorepo / "projects" / "davi-vision"
    assert pdir.is_dir()
    assert (pdir / "docs").is_dir()
    assert (pdir / "notes").is_dir()
    assert (pdir / "assets").is_dir()

    proj = json.loads((pdir / "project.json").read_text())
    assert proj["id"] == "davi-vision"
    assert proj["description"] == "Reshape DAVI"
    assert proj["status"] == "active"

    tasks = json.loads((pdir / "tasks.json").read_text())
    assert tasks == {"next_id": 1, "tasks": []}


def test_project_new_with_priority_due_tags_labels(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, [
        "project", "new", "drools-rate",
        "--desc", "Rate limiter",
        "--priority", "P1",
        "--due", "2026-05-01",
        "--tags", "limits,abuse",
        "--labels", "abuse-scoring-rules",
    ])
    assert result.exit_code == 0, result.output
    proj = json.loads((monorepo / "projects" / "drools-rate" / "project.json").read_text())
    assert proj["priority"] == "P1"
    assert proj["due"] == "2026-05-01"
    assert proj["tags"] == ["limits", "abuse"]
    assert proj["labels"] == ["abuse-scoring-rules"]


def test_project_new_rejects_duplicate(monorepo: Path, seed_project) -> None:
    seed_project("existing")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "new", "existing"])
    assert result.exit_code != 0
    assert "already exists" in result.output.lower()


def test_project_new_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "new", "Bad ID!"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()
    # The invalid id should never create a directory.
    assert not (monorepo / "projects" / "Bad ID!").exists()


# ─── `lab agents sync` — AGENTS.md canonical + CLAUDE.md/Copilot/memory links ──
# These supersede the never-implemented `lab project relink` design. They
# monkeypatch HOME so the sync's ~/.claude + ~/.codex writes land in a temp dir.


def test_agents_sync_links_project_claude_md(monorepo: Path, seed_project,
                                             monkeypatch, tmp_path) -> None:
    """A hand-written project CLAUDE.md becomes a symlink to a canonical AGENTS.md."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    pdir = seed_project("legacy")
    (pdir / "CLAUDE.md").write_text("# legacy project instructions\n")
    runner = CliRunner()
    result = runner.invoke(main, ["agents", "sync"])
    assert result.exit_code == 0, result.output
    agents = pdir / "AGENTS.md"
    claude = pdir / "CLAUDE.md"
    assert agents.is_file() and not agents.is_symlink()
    assert "legacy project instructions" in agents.read_text()
    assert claude.is_symlink()
    assert claude.resolve() == agents.resolve()


def test_agents_sync_root_instructions_and_memory(monorepo: Path,
                                                  monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    runner = CliRunner()
    result = runner.invoke(main, ["agents", "sync"])
    assert result.exit_code == 0, result.output
    # Root CLAUDE.md (a real file in the fixture) → moved to AGENTS.md + symlinked.
    assert (monorepo / "AGENTS.md").is_file()
    assert (monorepo / "CLAUDE.md").is_symlink()
    cop = monorepo / ".github" / "copilot-instructions.md"
    assert cop.is_symlink()
    assert cop.resolve() == (monorepo / "AGENTS.md").resolve()
    # Repo-local memory dir + index created, and AGENTS.md carries the rule.
    assert (monorepo / ".agents" / "memory" / "MEMORY.md").is_file()
    assert "Memory (repo-local" in (monorepo / "AGENTS.md").read_text()


def test_agents_sync_is_idempotent(monorepo: Path, seed_project,
                                   monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    seed_project("one")
    runner = CliRunner()
    first = runner.invoke(main, ["agents", "sync"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(main, ["agents", "sync"])
    assert second.exit_code == 0, second.output
    assert "nothing to do" in second.output


def test_agents_sync_links_shared_skills(monorepo: Path, seed_project,
                                         monkeypatch, tmp_path) -> None:
    """Canonical .claude/skills is exposed via .agents/skills at root + per project."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (monorepo / ".claude" / "skills" / "demo").mkdir(parents=True)
    (monorepo / ".claude" / "skills" / "demo" / "SKILL.md").write_text("# demo\n")
    pdir = seed_project("p")
    runner = CliRunner()
    r = runner.invoke(main, ["agents", "sync"])
    assert r.exit_code == 0, r.output
    # Root tool-neutral alias.
    root_alias = monorepo / ".agents" / "skills"
    assert root_alias.is_symlink()
    assert (root_alias / "demo" / "SKILL.md").is_file()
    # Each project sees the shared skills via both the Claude and tool-neutral paths.
    for sub in (".claude/skills", ".agents/skills"):
        link = pdir / sub
        assert link.is_symlink(), sub
        assert (link / "demo" / "SKILL.md").is_file(), sub


def test_project_ls_empty(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls"])
    assert result.exit_code == 0
    assert "no projects" in result.output.lower()


def test_project_ls_lists_all_by_default(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" in result.output


def test_project_ls_filter_by_status(monorepo: Path, seed_project) -> None:
    alpha = seed_project("alpha")
    beta = seed_project("beta")
    # flip beta to archived directly on disk
    data = json.loads((beta / "project.json").read_text())
    data["status"] = "archived"
    (beta / "project.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls", "--status", "active"])
    assert "alpha" in result.output
    assert "beta" not in result.output

    result = runner.invoke(main, ["project", "ls", "--status", "archived"])
    assert "beta" in result.output
    assert "alpha" not in result.output


def test_project_status_prints_summary(monorepo: Path, seed_project) -> None:
    seed_project("alpha", description="Alpha is great")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "status", "alpha"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "Alpha is great" in result.output


def test_project_status_auto_detects_from_pwd(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("beta")
    monkeypatch.chdir(pdir)
    runner = CliRunner()
    result = runner.invoke(main, ["project", "status"])
    assert result.exit_code == 0, result.output
    assert "beta" in result.output


def test_project_status_missing_project(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "status", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_project_set_updates_field(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "description", "New desc"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["description"] == "New desc"


def test_project_set_status(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "status", "paused"])
    assert result.exit_code == 0
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["status"] == "paused"


def test_project_set_rejects_bad_status(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "status", "weird"])
    assert result.exit_code != 0
    assert "not one of" in result.output.lower()


def test_project_set_priority_and_due(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["project", "set", "alpha", "priority", "P0"])
    runner.invoke(main, ["project", "set", "alpha", "due", "2026-05-15"])
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["priority"] == "P0"
    assert data["due"] == "2026-05-15"


def test_project_set_tags_and_labels_csv(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["project", "set", "alpha", "tags", "a,b,c"])
    runner.invoke(main, ["project", "set", "alpha", "labels", "lipy-davi"])
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["tags"] == ["a", "b", "c"]
    assert data["labels"] == ["lipy-davi"]


def test_project_archive(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "archive", "alpha"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["status"] == "archived"


def test_project_rm_requires_confirmation(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    # No confirmation → aborts
    result = runner.invoke(main, ["project", "rm", "alpha"], input="\n")
    assert result.exit_code != 0
    assert (monorepo / "projects" / "alpha").exists()


def test_project_rm_with_force(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "rm", "alpha", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (monorepo / "projects" / "alpha").exists()


def test_project_rm_missing(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "rm", "nope", "--yes"])
    assert result.exit_code != 0


def test_project_archive_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "archive", "../bad"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()


def test_project_rm_rejects_bad_id(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "rm", "../bad", "--yes"])
    assert result.exit_code != 0
    assert "must match" in result.output.lower()


def test_project_archive_missing(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "archive", "nope"])
    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_project_ls_filter_by_tag(monorepo: Path, seed_project) -> None:
    alpha = seed_project("alpha")
    seed_project("beta")
    data = json.loads((alpha / "project.json").read_text())
    data["tags"] = ["backend"]
    (alpha / "project.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls", "--tag", "backend"])
    assert result.exit_code == 0
    assert "alpha" in result.output
    assert "beta" not in result.output


def test_project_ls_filter_by_label(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    beta = seed_project("beta")
    data = json.loads((beta / "project.json").read_text())
    data["labels"] = ["lipy-davi"]
    (beta / "project.json").write_text(json.dumps(data))

    runner = CliRunner()
    result = runner.invoke(main, ["project", "ls", "--label", "lipy-davi"])
    assert result.exit_code == 0
    assert "beta" in result.output
    assert "alpha" not in result.output


def test_project_set_loe_invalid(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "loe", "not-a-number"])
    assert result.exit_code != 0
    assert "not a number" in result.output.lower()


def test_project_new_is_atomic_on_failure(monorepo: Path, monkeypatch) -> None:
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
    result = runner.invoke(main, ["project", "new", "doomed", "--desc", "test"])
    assert result.exit_code != 0
    assert not (monorepo / "projects" / "doomed").exists()


def test_project_add_missing_mp(monorepo, seed_project, monkeypatch) -> None:
    """When the MP clone is missing, `project add` first tries `mint clone`.
    If that fails (or is unavailable), the command should still error clearly.
    We stub subprocess.run so mint looks like it ran + failed."""
    seed_project("davi-test")

    import subprocess as sp
    real_run = sp.run

    def fake_run(cmd, *a, **kw):
        # Fail the mint clone; let everything else through (there won't be
        # anything else reached because we raise right after the re-check).
        if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "mint" and cmd[1] == "clone":
            class R:
                returncode = 1
                stdout = ""
                stderr = "clone unavailable in tests"
            return R()
        return real_run(cmd, *a, **kw)
    monkeypatch.setattr(sp, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["project", "add", "davi-test", "lipy-davi"])
    assert result.exit_code != 0
    assert "repositories" in result.output.lower() or "not found" in result.output.lower()


def test_project_add_unknown_prefix(monorepo, seed_project, tmp_path, monkeypatch) -> None:
    seed_project("davi-test")
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
    result = runner.invoke(main, ["project", "add", "davi-test", "some-mp"])
    assert result.exit_code != 0
    assert "prefix" in result.output.lower()


def test_project_add_stores_worktrees_subfolder_path(monorepo, seed_project, tmp_path,
                                                        monkeypatch) -> None:
    """New layout: dir should be stored as ``worktrees/<name>`` and the
    worktree lives at ``<project>/worktrees/<name>``."""
    seed_project("alpha")
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
    result = runner.invoke(main, ["project", "add", "alpha", "some-mp"])
    assert result.exit_code == 0, result.output

    pdir = monorepo / "projects" / "alpha"
    data = json.loads((pdir / "project.json").read_text())
    assert len(data["worktrees"]) == 1
    wt = data["worktrees"][0]
    assert wt["dir"].startswith("worktrees/"), f"expected subfolder layout, got {wt['dir']!r}"
    assert (pdir / wt["dir"]).is_dir()


def test_project_remove_force_flag(monorepo, seed_project, monkeypatch) -> None:
    """--force should pass through to `git worktree remove --force`."""
    seed_project("alpha")
    pdir = monorepo / "projects" / "alpha"
    # Seed a worktree entry + the dir (pretend git already set it up).
    data = json.loads((pdir / "project.json").read_text())
    data["worktrees"] = [{"mp": "some-mp", "dir": "worktrees/sm-alpha", "branch": "x"}]
    (pdir / "worktrees" / "sm-alpha").mkdir(parents=True)
    (monorepo / "repositories" / "some-mp").mkdir(parents=True)
    (pdir / "project.json").write_text(json.dumps(data))

    captured: list[list[str]] = []
    import subprocess as sp

    def fake_run(cmd, *a, **kw):
        captured.append(list(cmd))
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    monkeypatch.setattr(sp, "run", fake_run)

    runner = CliRunner()
    result = runner.invoke(main, ["project", "remove", "alpha", "some-mp", "--force"])
    assert result.exit_code == 0, result.output

    # Find the `git worktree remove` call and assert --force was included.
    removes = [c for c in captured if "worktree" in c and "remove" in c]
    assert removes and "--force" in removes[0], f"expected --force in {removes}"


def test_pr_add_and_ls(monorepo, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    r = runner.invoke(main, [
        "pr", "add", "https://example/pr/1", "--project", "alpha",
        "--mp", "lipy-davi", "--title", "test pr",
    ])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["pr", "ls", "--project", "alpha"])
    assert "https://example/pr/1" in r.output

    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert data["prs"][0]["url"] == "https://example/pr/1"
    assert data["prs"][0]["mp"] == "lipy-davi"


def test_pr_rm(monorepo, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["pr", "add", "https://x/1", "--project", "alpha"])
    runner.invoke(main, ["pr", "add", "https://x/2", "--project", "alpha"])
    r = runner.invoke(main, ["pr", "rm", "0", "--project", "alpha"])
    assert r.exit_code == 0
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert [p["url"] for p in data["prs"]] == ["https://x/2"]


def test_artifact_add_and_ls(monorepo, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    r = runner.invoke(main, [
        "artifact", "add", "https://docs/abc", "--project", "alpha",
        "--type", "google_doc", "--title", "Design doc",
    ])
    assert r.exit_code == 0, r.output
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    a = data["artifacts"][0]
    assert a["type"] == "google_doc"
    assert a["title"] == "Design doc"
    assert a["id"] == 1


def test_artifact_rm_by_id(monorepo, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["artifact", "add", "https://a", "--project", "alpha"])
    runner.invoke(main, ["artifact", "add", "https://b", "--project", "alpha"])
    r = runner.invoke(main, ["artifact", "rm", "1", "--project", "alpha"])
    assert r.exit_code == 0
    data = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert [a["url"] for a in data["artifacts"]] == ["https://b"]
