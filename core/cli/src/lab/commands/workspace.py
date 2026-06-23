from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import click

from lab import paths, storage


def _write_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def _append_gitignore_block(path: Path, block: str) -> None:
    marker = "# Lab workspace"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if marker in current:
            return
        sep = "" if current.endswith("\n") else "\n"
        path.write_text(current + sep + "\n" + block, encoding="utf-8")
    else:
        _write_if_missing(path, block)


def _project_doc(project_id: str, name: str) -> dict:
    today = date.today().isoformat()
    return {
        "id": project_id,
        "name": name,
        "description": "Example project created by lab init.",
        "status": "active",
        "tags": [],
        "labels": [],
        "priority": "P2",
        "loe": None,
        "due": None,
        "created": today,
        "updated": today,
        "worktrees": [],
        "prs": [],
        "artifacts": [],
        "references": [],
        "pinned": ["docs/README.md"],
        "hold": None,
    }


def _init_example_project(root: Path) -> None:
    pdir = root / "projects" / "example"
    (pdir / "docs").mkdir(parents=True, exist_ok=True)
    (pdir / "notes").mkdir(parents=True, exist_ok=True)
    (pdir / "assets").mkdir(parents=True, exist_ok=True)
    (pdir / "scripts").mkdir(parents=True, exist_ok=True)
    if not (pdir / "project.json").exists():
        storage.write_json(pdir / "project.json", _project_doc("example", "Example"))
    if not (pdir / "tasks.json").exists():
        storage.write_json(pdir / "tasks.json", {"next_id": 1, "tasks": []})
    _write_if_missing(
        pdir / "docs" / "README.md",
        "# Example project\n\nThis project shows the default Lab project shape.\n",
    )
    _write_if_missing(pdir / "notes" / ".gitkeep", "")
    _write_if_missing(pdir / "assets" / ".gitkeep", "")
    _write_if_missing(
        pdir / "scripts" / "README.md",
        "# Project scripts\n\nPut project-specific helper scripts here.\n",
    )


def _init_example_app(root: Path) -> None:
    app_dir = root / "apps" / "example-cli"
    (app_dir / "bin").mkdir(parents=True, exist_ok=True)
    _write_if_missing(
        app_dir / "README.md",
        "# example-cli\n\nWorkspace-owned CLI example. Run with `lab app run example-cli` once app support lands.\n",
    )
    _write_if_missing(
        app_dir / "lab-app.toml",
        'name = "example-cli"\n'
        'description = "Example workspace CLI."\n'
        'command = "bin/example"\n',
    )
    script = app_dir / "bin" / "example"
    _write_if_missing(script, "#!/usr/bin/env sh\necho \"hello from a workspace app\"\n")
    try:
        script.chmod(script.stat().st_mode | 0o111)
    except OSError:
        pass


def _init_workspace_files(root: Path, *, name: str, include_example: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for d in (
        root / ".lab" / "state" / "cache",
        root / ".lab" / "state" / "indexes",
        root / ".lab" / "state" / "sessions",
        root / "projects",
        root / "apps",
        root / "docs",
        root / "skills",
        root / "scripts",
        root / "repositories",
        root / "content" / "updates",
        root / "content" / "logs",
        root / "content" / "wikis",
        root / ".agents" / "memory",
    ):
        d.mkdir(parents=True, exist_ok=True)

    _write_if_missing(root / "README.md", f"# {name}\n\nLab workspace.\n")
    _write_if_missing(
        root / "AGENTS.md",
        "# Lab workspace instructions\n\nUse `lab` for project and task state. Do not hand-edit `project.json` or `tasks.json`.\n",
    )
    _write_if_missing(
        root / "lab.toml",
        "[workspace]\n"
        f"name = {paths.toml_str(name)}\n"
        "version = 1\n\n"
        "[paths]\n"
        'projects = "projects"\n'
        'apps = "apps"\n'
        'docs = "docs"\n'
        'skills = "skills"\n'
        'scripts = "scripts"\n'
        'repositories = "repositories"\n'
        'content = "content"\n\n'
        "[server]\n"
        'host = "127.0.0.1"\n'
        "port = 3333\n\n"
        "[agents]\n"
        'default = "codex"\n',
    )
    _append_gitignore_block(
        root / ".gitignore",
        "# Lab workspace\n"
        ".lab/state/\n"
        "__pycache__/\n"
        ".DS_Store\n"
        "projects/*/worktrees/\n"
        "repositories/*\n"
        "!repositories/.gitignore\n"
        "!repositories/README.md\n",
    )
    _write_if_missing(root / "docs" / "README.md", "# Workspace docs\n")
    _write_if_missing(root / "scripts" / "hello.py", "print('hello from Lab')\n")
    _write_if_missing(root / "repositories" / "README.md", "# Repositories\n\nClone reference repos here.\n")
    _write_if_missing(root / "repositories" / ".gitignore", "*\n!.gitignore\n!README.md\n")
    _write_if_missing(root / "content" / "README.md", "# Content\n\nWorkspace knowledge base.\n")
    _write_if_missing(root / "content" / "updates" / ".gitkeep", "")
    _write_if_missing(root / "content" / "logs" / ".gitkeep", "")
    _write_if_missing(root / "content" / "wikis" / ".gitkeep", "")
    _write_if_missing(root / ".agents" / "memory" / "MEMORY.md", "# Memory index\n")
    _write_if_missing(
        root / "skills" / "example-skill" / "SKILL.md",
        "---\nname: example-skill\ndescription: Example workspace skill.\n---\n\n# Example skill\n",
    )
    if include_example:
        _init_example_project(root)
        _init_example_app(root)


@click.command(name="init")
@click.argument("path", required=False, type=click.Path(path_type=Path))
@click.option("--name", default=None, help="Workspace display name.")
@click.option("--no-example", is_flag=True, help="Skip example project/app files.")
@click.option("--no-git", is_flag=True, help="Do not run git init for a new workspace.")
def init_cmd(path: Path | None, name: str | None, no_example: bool, no_git: bool) -> None:
    """Create a Lab workspace and register it as active."""
    root = (path or Path.cwd()).expanduser().resolve()
    display_name = name or root.name
    already_initialized = (root / "lab.toml").exists()
    _init_workspace_files(root, name=display_name, include_example=not no_example)
    if not no_git and not (root / ".git").exists():
        subprocess.run(["git", "init"], cwd=str(root), check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    row = paths.register_workspace(root, name=display_name, active=True)
    state = "registered" if already_initialized else "created"
    click.echo(f"{state} workspace {row['id']} at {row['path']}")


@click.group(name="workspace")
def workspace_group() -> None:
    """Manage Lab workspaces."""


@workspace_group.command("list")
def list_workspaces() -> None:
    data = paths.read_workspace_registry()
    active = data.get("active")
    rows = data.get("workspaces") or []
    if not rows:
        click.echo("no workspaces")
        return
    width = max(len(str(r["id"])) for r in rows)
    for row in rows:
        mark = "*" if row["id"] == active else " "
        click.echo(f"{mark} {row['id']:<{width}}  {row['name']}  {row['path']}")


@workspace_group.command("use")
@click.argument("path", type=click.Path(path_type=Path))
@click.option("--name", default=None, help="Workspace display name.")
def use_workspace(path: Path, name: str | None) -> None:
    root = path.expanduser().resolve()
    if not (root / "lab.toml").is_file() and not ((root / ".git").exists() and (root / "content").is_dir()):
        raise click.ClickException(f"{root} is not a Lab workspace; run `lab init {root}` first")
    row = paths.register_workspace(root, name=name or root.name, active=True)
    click.echo(f"active workspace {row['id']} at {row['path']}")


@workspace_group.command("current")
def current_workspace() -> None:
    root = paths.find_workspace_root()
    data = paths.read_workspace_registry()
    active = data.get("active")
    label = f" ({active})" if active else ""
    click.echo(f"{root}{label}")
