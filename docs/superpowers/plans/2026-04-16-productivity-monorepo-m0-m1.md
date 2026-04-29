# Productivity Monorepo — Plan 1 (M0 + M1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the productivity monorepo skeleton at `~/src/productivity-new/` and build the `lab` CLI with full project + task lifecycle commands, TDD-covered and installed to `~/.local/bin/lab`.

**Architecture:** Python 3.11+ package at `apps/lab/` exposing a click-based CLI. Pure JSON data model (no frontmatter). Atomic file writes. Commands are grouped under `lab project ...` and `lab task ...`. State lives in `knowledge/projects/<id>/{project.json, tasks.json}`. Tests use pytest + click's `CliRunner` against a fixture-created temp monorepo.

**Tech Stack:** Python 3.11, click 8, pytest 8, pytest-cov. No backend / frontend / watcher in this plan — those come in Plan 2 and Plan 3.

**Out of scope for Plan 1 (deferred to later plans):**
- Backend + watcher + global `.index.json` (Plan 2)
- Frontend views — dashboard, timeline, project view (Plan 3)
- Worktree commands — `lab project add`, `lab project remove` (Plan 4)
- MP prefix config + `lab mp` commands (Plan 4)
- `lab search` full-text (Plan 5)
- `lab pr add`, `lab artifact add`, `lab note` (Plan 5)
- Migration agent + `lab migrate` (Plan 6)
- Moving tool apps (darwin-runner, darwin-backups, trustim-ir-cli) (Plan 7)
- gdiff/mdview merge (Plan 8)

By the end of Plan 1, these commands work and are tested:

```
lab project new <id> [--desc "..."] [--priority P0..P3] [--due YYYY-MM-DD] [--tags ...] [--labels ...]
lab project ls [--status active|paused|done|archived] [--tag ...] [--label ...]
lab project status [<id>]                                  # PWD-aware
lab project set <id> <field> <value>                       # status, description, priority, due, ...
lab project archive <id>
lab project rm <id>                                        # confirms before delete

lab task new "title" [--project <id>] [--file] [--priority P0..P3] [--loe N] [--due YYYY-MM-DD] [--tags ...] [--labels ...]
lab task ls [--project <id>] [--status open|done|<state>] [--priority P0,P1] [--tag ...] [--label ...] [--due 7d]
lab task show <id> [--project <id>]
lab task set <id> <field> <value> [--project <id>]
lab task done <id> [--project <id>]
lab task reopen <id> [--project <id>]
lab task block <id> "reason" [--project <id>]
lab task unblock <id> [--project <id>]
```

---

## File Structure

**Monorepo root (created in Task 1):** `~/src/productivity-new/`

```
~/src/productivity-new/
├── .git/
├── .gitignore                           # ignores venv/, __pycache__, .DS_Store, multiproducts/, .index.json
├── .python-version                      # 3.11
├── README.md                            # one-paragraph overview + "make install"
├── CLAUDE.md                            # root guidance (short; points at `lab --help`)
├── Makefile                             # install target
├── apps/
│   └── lab/
│       ├── pyproject.toml               # package metadata, deps, entry_points
│       ├── README.md                    # CLI usage examples
│       ├── lab                          # shell shim → `python -m lab`
│       ├── src/
│       │   └── lab/
│       │       ├── __init__.py          # __version__
│       │       ├── __main__.py          # `python -m lab` → cli.main()
│       │       ├── cli.py               # click root group; project/task subgroups
│       │       ├── paths.py             # monorepo root detection, project path resolution
│       │       ├── storage.py           # atomic JSON read/write
│       │       ├── model.py             # Project + Task dataclasses, enums, validation
│       │       └── commands/
│       │           ├── __init__.py
│       │           ├── project.py       # project subcommands
│       │           └── task.py          # task subcommands
│       └── tests/
│           ├── __init__.py
│           ├── conftest.py              # `monorepo` fixture (tmp_path-based)
│           ├── test_paths.py
│           ├── test_storage.py
│           ├── test_model.py
│           ├── test_cli_project.py
│           └── test_cli_task.py
└── knowledge/
    ├── projects/
    │   └── .gitkeep
    ├── meetings/
    │   └── .gitkeep
    ├── wikis/
    │   └── .gitkeep
    ├── roadmaps/
    │   └── .gitkeep
    ├── logs/
    │   └── .gitkeep
    └── skills/
        └── .gitkeep
```

### Responsibilities per file

- `paths.py` — single place for filesystem conventions. `find_monorepo_root()`, `project_dir(root, id)`, `tasks_file(root, id)`, `project_file(root, id)`.
- `storage.py` — atomic read/write. `read_json(path)`, `write_json(path, data)` (writes to tempfile + rename). No domain knowledge.
- `model.py` — dataclasses `Project` and `Task`, `Status` / `Priority` enums, `from_dict` / `to_dict` round-trip, `validate()` raising `ModelError`.
- `commands/project.py` — each subcommand is a click function that loads → mutates → stores. Thin; business logic in model.
- `commands/task.py` — same pattern for tasks. Handles PWD-aware `--project` resolution.
- `cli.py` — wires root group, registers `project` and `task` subgroups.

### Test strategy

- `conftest.py` builds a temp monorepo with `knowledge/projects/`. The `monorepo` fixture returns the root path.
- Each command test uses click's `CliRunner.invoke(cli.main, [...], env={"LAB_ROOT": str(monorepo)})` and asserts on exit code, stdout, and on-disk JSON state.
- Unit tests for `model.py` / `storage.py` / `paths.py` exercise edge cases directly.
- Coverage target: ≥ 90% for `lab/` package.

---

## Task 1: Initialize monorepo root + skeleton folders

**Files:**
- Create: `~/src/productivity-new/.gitignore`
- Create: `~/src/productivity-new/README.md`
- Create: `~/src/productivity-new/.python-version`

- [ ] **Step 1: Create scratch monorepo directory and init git**

Run:
```bash
mkdir -p ~/src/productivity-new
cd ~/src/productivity-new
git init --initial-branch=main
```

Expected: `Initialized empty Git repository in /Users/jcortes/src/productivity-new/.git/`

- [ ] **Step 2: Write `.gitignore`**

Create `~/src/productivity-new/.gitignore`:

```
# Python
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.venv/
venv/

# Monorepo runtime
multiproducts/
knowledge/.index.json

# macOS
.DS_Store

# Editor
.idea/
.vscode/
*.swp

# Superpowers scratch
.superpowers/
```

- [ ] **Step 3: Write `README.md`**

Create `~/src/productivity-new/README.md`:

```markdown
# Productivity monorepo

Single-user personal productivity suite: unified CLI (`lab`), knowledge base, and project/task state.

## Install (first time)

```
make install
```

Installs `lab` into `~/.local/bin/`. Make sure `~/.local/bin` is on your PATH.

## Spec and plans

- Design spec: `docs/superpowers/specs/2026-04-16-productivity-monorepo-design.md`
- Plans: `docs/superpowers/plans/`

## Layout

- `apps/lab/` — the unified CLI (Python)
- `knowledge/projects/<id>/` — active projects
- `knowledge/{meetings,wikis,roadmaps,logs,skills}/` — content

More in the design spec.
```

- [ ] **Step 4: Write `.python-version`**

Create `~/src/productivity-new/.python-version`:

```
3.11
```

- [ ] **Step 5: Create knowledge/ skeleton with `.gitkeep` markers**

Run:
```bash
cd ~/src/productivity-new
for d in projects meetings wikis roadmaps logs skills; do
  mkdir -p "knowledge/$d" && touch "knowledge/$d/.gitkeep"
done
```

- [ ] **Step 6: Commit skeleton**

Run:
```bash
cd ~/src/productivity-new
git add .
git status
```

Expected: `.gitignore`, `.python-version`, `README.md`, `knowledge/**/.gitkeep` all staged.

Run:
```bash
git commit -m "chore: initialize monorepo skeleton"
```

---

## Task 2: Root `CLAUDE.md` and `Makefile` skeleton

**Files:**
- Create: `~/src/productivity-new/CLAUDE.md`
- Create: `~/src/productivity-new/Makefile`

- [ ] **Step 1: Write root `CLAUDE.md`**

Create `~/src/productivity-new/CLAUDE.md`:

```markdown
# Productivity monorepo

You're in a single-user productivity monorepo. Everything lives here.

## How to do anything

Use `lab`. Run `lab --help` for commands. Never hand-edit `project.json`, `tasks.json`, or `.index.json`.

## Where things live

- `knowledge/projects/<id>/` — active projects (one folder each, contains `project.json`, `tasks.json`, `docs/`, `notes/`, `assets/`, and any worktrees)
- `knowledge/{meetings,wikis,roadmaps,logs}/` — knowledge that isn't project-scoped
- `knowledge/skills/` — shared templates (investigation, one-pager, weekly-update)
- `apps/` — CLIs and the web service (Plan 1 only has `apps/lab/`)
- `multiproducts/` — gitignored MP clones (added in Plan 4)
- `.claude/agents/` — shared agents (added in later plans)

## On project work

When you're in `knowledge/projects/<id>/`, read that project's `CLAUDE.md` too. It's auto-generated and contains the project's objective and tool references.

## Archetypes (no types)

Projects are not labeled by archetype. If asked to investigate, draft from `knowledge/skills/investigation/` (once it exists). For a one-pager, use `knowledge/skills/one-pager/`. Pick based on the ask.
```

- [ ] **Step 2: Write `Makefile` with install target**

Create `~/src/productivity-new/Makefile`:

```makefile
.PHONY: install uninstall test

BIN_DIR := $(HOME)/.local/bin
VENV := apps/lab/.venv

install:
	@mkdir -p $(BIN_DIR)
	@test -d $(VENV) || python3 -m venv $(VENV)
	@$(VENV)/bin/pip install -e 'apps/lab[dev]' --quiet
	@ln -sf $(CURDIR)/apps/lab/lab $(BIN_DIR)/lab
	@echo "Installed lab → $(BIN_DIR)/lab"
	@echo "Ensure $(BIN_DIR) is on your PATH."

uninstall:
	@rm -f $(BIN_DIR)/lab
	@rm -rf $(VENV)
	@echo "Uninstalled lab and removed $(VENV)"

test:
	@$(VENV)/bin/pytest apps/lab/tests -v
```

- [ ] **Step 3: Commit**

Run:
```bash
cd ~/src/productivity-new
git add CLAUDE.md Makefile
git commit -m "chore: root CLAUDE.md and Makefile install target"
```

---

## Task 3: Scaffold `apps/lab/` Python package

**Files:**
- Create: `~/src/productivity-new/apps/lab/pyproject.toml`
- Create: `~/src/productivity-new/apps/lab/README.md`
- Create: `~/src/productivity-new/apps/lab/lab`
- Create: `~/src/productivity-new/apps/lab/src/lab/__init__.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/__main__.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/cli.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/commands/__init__.py`
- Create: `~/src/productivity-new/apps/lab/tests/__init__.py`

- [ ] **Step 1: Create directory tree**

Run:
```bash
cd ~/src/productivity-new
mkdir -p apps/lab/src/lab/commands apps/lab/tests
```

- [ ] **Step 2: Write `apps/lab/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "lab"
version = "0.1.0"
description = "Unified CLI for the productivity monorepo"
requires-python = ">=3.11"
dependencies = [
    "click>=8.1",
]

[project.scripts]
lab = "lab.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --cov=lab --cov-report=term-missing"
```

- [ ] **Step 3: Write `apps/lab/README.md`**

```markdown
# lab

Unified CLI for the productivity monorepo. See `../../docs/superpowers/specs/2026-04-16-productivity-monorepo-design.md` for the design.

## Dev

```
pip install -e .[dev]
pytest -v
```

## Subcommand overview (Plan 1)

- `lab project new|ls|status|set|archive|rm`
- `lab task new|ls|show|set|done|reopen|block|unblock`

Run `lab --help` for everything.
```

- [ ] **Step 4: Write shell shim `apps/lab/lab`**

```bash
#!/usr/bin/env bash
# Self-contained shim: always uses the venv's python so `lab` works from
# anywhere on the user's PATH without needing the venv activated.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/.venv/bin/python" -m lab "$@"
```

Then make it executable:
```bash
chmod +x ~/src/productivity-new/apps/lab/lab
```

- [ ] **Step 5: Write empty package stubs**

Create `apps/lab/src/lab/__init__.py`:
```python
__version__ = "0.1.0"
```

Create `apps/lab/src/lab/__main__.py`:
```python
from lab.cli import main

if __name__ == "__main__":
    main()
```

Create `apps/lab/src/lab/cli.py`:
```python
import click


@click.group()
@click.version_option(package_name="lab")
def main() -> None:
    """Unified CLI for the productivity monorepo."""


if __name__ == "__main__":
    main()
```

Create `apps/lab/src/lab/commands/__init__.py`:
```python
```

Create `apps/lab/tests/__init__.py`:
```python
```

- [ ] **Step 6: Install package in dev mode and smoke test**

Run:
```bash
cd ~/src/productivity-new/apps/lab
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev] --quiet
python -m lab --help
python -m lab --version
```

Expected: `--help` prints "Unified CLI for the productivity monorepo." and `--version` prints `lab, version 0.1.0`.

- [ ] **Step 7: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab
git commit -m "feat(lab): scaffold Python package with click entrypoint"
```

---

## Task 4: `conftest.py` fixture and `test_placeholder` sanity

**Files:**
- Create: `~/src/productivity-new/apps/lab/tests/conftest.py`
- Create: `~/src/productivity-new/apps/lab/tests/test_sanity.py`

- [ ] **Step 1: Write `conftest.py` with `monorepo` fixture**

```python
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture()
def monorepo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal monorepo layout under tmp_path and point `LAB_ROOT` at it."""
    root = tmp_path / "productivity"
    (root / "knowledge" / "projects").mkdir(parents=True)
    (root / "knowledge" / "meetings").mkdir()
    (root / "knowledge" / "skills").mkdir()
    # git repo marker so find_monorepo_root() works without running git
    (root / ".git").mkdir()
    (root / "CLAUDE.md").write_text("# monorepo test fixture\n")
    monkeypatch.setenv("LAB_ROOT", str(root))
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def seed_project(monorepo: Path):
    """Factory to create a blank project under the fixture monorepo."""
    def _create(project_id: str = "demo", *, description: str = "") -> Path:
        pdir = monorepo / "knowledge" / "projects" / project_id
        pdir.mkdir(parents=True)
        (pdir / "project.json").write_text(json.dumps({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "tags": [],
            "labels": [],
            "priority": None,
            "loe": None,
            "due": None,
            "created": "2026-04-16",
            "updated": "2026-04-16",
            "worktrees": [],
            "prs": [],
            "artifacts": [],
            "pinned": [],
        }, indent=2))
        (pdir / "tasks.json").write_text(json.dumps({"next_id": 1, "tasks": []}, indent=2))
        return pdir
    return _create
```

- [ ] **Step 2: Write `test_sanity.py`**

```python
from pathlib import Path


def test_monorepo_fixture_creates_structure(monorepo: Path) -> None:
    assert (monorepo / "knowledge" / "projects").is_dir()
    assert (monorepo / ".git").is_dir()


def test_seed_project_factory(seed_project) -> None:
    pdir = seed_project("hello")
    assert (pdir / "project.json").is_file()
    assert (pdir / "tasks.json").is_file()
```

- [ ] **Step 3: Run tests and verify**

```bash
cd ~/src/productivity-new/apps/lab
source .venv/bin/activate
pytest -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/tests
git commit -m "test(lab): conftest with monorepo fixture and sanity tests"
```

---

## Task 5: Implement `paths.py` (TDD)

**Files:**
- Create: `~/src/productivity-new/apps/lab/tests/test_paths.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/paths.py`

- [ ] **Step 1: Write failing tests**

Create `apps/lab/tests/test_paths.py`:

```python
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
    sub = monorepo / "knowledge" / "projects"
    monkeypatch.chdir(sub)
    # macOS tmp_path is under /var → /private/var symlink; compare resolved paths.
    assert find_monorepo_root().resolve() == monorepo.resolve()


def test_find_monorepo_root_raises_when_not_in_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LAB_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(MonorepoNotFound):
        find_monorepo_root()


def test_project_dir_composes_path(monorepo: Path) -> None:
    assert project_dir(monorepo, "davi-vision") == monorepo / "knowledge" / "projects" / "davi-vision"


def test_project_file_and_tasks_file(monorepo: Path) -> None:
    pdir = monorepo / "knowledge" / "projects" / "davi-vision"
    assert project_file(monorepo, "davi-vision") == pdir / "project.json"
    assert tasks_file(monorepo, "davi-vision") == pdir / "tasks.json"
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_paths.py -v
```

Expected: ModuleNotFoundError / ImportError on `lab.paths`.

- [ ] **Step 3: Implement `paths.py`**

Create `apps/lab/src/lab/paths.py`:

```python
from __future__ import annotations

import os
from pathlib import Path


class MonorepoNotFound(RuntimeError):
    """Raised when the monorepo root cannot be located."""


def find_monorepo_root(start: Path | None = None) -> Path:
    """Locate the monorepo root.

    Resolution order:
      1. `LAB_ROOT` environment variable (absolute path).
      2. Walk up from `start` (defaults to PWD) until a directory containing
         both `.git` and `knowledge/` is found.

    Raises `MonorepoNotFound` if neither resolves.
    """
    env_root = os.environ.get("LAB_ROOT")
    if env_root:
        return Path(env_root)

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / ".git").exists() and (candidate / "knowledge").is_dir():
            return candidate
    raise MonorepoNotFound(
        f"No monorepo found from {current}. Set LAB_ROOT or run inside the repo."
    )


def project_dir(root: Path, project_id: str) -> Path:
    return root / "knowledge" / "projects" / project_id


def project_file(root: Path, project_id: str) -> Path:
    return project_dir(root, project_id) / "project.json"


def tasks_file(root: Path, project_id: str) -> Path:
    return project_dir(root, project_id) / "tasks.json"
```

- [ ] **Step 4: Re-run tests — expect pass**

```bash
pytest tests/test_paths.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/src/lab/paths.py apps/lab/tests/test_paths.py
git commit -m "feat(lab): paths module for monorepo and project path resolution"
```

---

## Task 6: Implement `storage.py` (TDD)

**Files:**
- Create: `~/src/productivity-new/apps/lab/tests/test_storage.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/storage.py`

- [ ] **Step 1: Write failing tests**

Create `apps/lab/tests/test_storage.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lab.storage import read_json, write_json


def test_write_json_creates_file_atomically(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"hello": "world"})
    assert target.is_file()
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_write_json_is_atomic_no_temp_leftovers(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"x": 1})
    siblings = list(tmp_path.iterdir())
    assert siblings == [target], f"unexpected files: {siblings}"


def test_read_json_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "out.json"
    write_json(target, {"a": [1, 2, 3], "b": {"c": "d"}})
    assert read_json(target) == {"a": [1, 2, 3], "b": {"c": "d"}}


def test_read_json_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "nope.json")


def test_write_json_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b" / "out.json"
    write_json(target, {})
    assert target.is_file()
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_storage.py -v
```

- [ ] **Step 3: Implement `storage.py`**

Create `apps/lab/src/lab/storage.py`:

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    """Read a JSON file. Raises FileNotFoundError if missing."""
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to a temp file in the same directory, then rename.

    Creates parent directories if needed. Output is pretty-printed with 2-space
    indentation and a trailing newline for clean diffs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Same-directory tempfile guarantees the rename is atomic on POSIX.
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=False)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        # Clean up temp on failure
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_storage.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/src/lab/storage.py apps/lab/tests/test_storage.py
git commit -m "feat(lab): atomic JSON read/write"
```

---

## Task 7: Implement `model.py` — enums and `Project` dataclass (TDD)

**Files:**
- Create: `~/src/productivity-new/apps/lab/tests/test_model.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/model.py`

- [ ] **Step 1: Write failing tests for enums and Project**

Create `apps/lab/tests/test_model.py`:

```python
from __future__ import annotations

import pytest

from lab.model import ModelError, Priority, Project, ProjectStatus


def test_project_status_enum_values() -> None:
    assert {s.value for s in ProjectStatus} == {"active", "paused", "done", "archived"}


def test_priority_enum_values() -> None:
    assert {p.value for p in Priority} == {"P0", "P1", "P2", "P3"}


def test_project_from_dict_roundtrip() -> None:
    data = {
        "id": "davi-vision",
        "name": "DAVI Vision",
        "description": "Reshape DAVI",
        "status": "active",
        "tags": ["davi"],
        "labels": ["lipy-davi"],
        "priority": "P1",
        "loe": 10,
        "due": "2026-05-01",
        "created": "2026-04-15",
        "updated": "2026-04-16",
        "worktrees": [],
        "prs": [],
        "artifacts": [],
        "pinned": [],
    }
    p = Project.from_dict(data)
    assert p.id == "davi-vision"
    assert p.status is ProjectStatus.active
    assert p.priority is Priority.P1
    assert p.to_dict() == data


def test_project_rejects_bad_status() -> None:
    data = {"id": "x", "name": "x", "status": "weird"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_priority() -> None:
    data = {"id": "x", "name": "x", "status": "active", "priority": "P9"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_due_format() -> None:
    data = {"id": "x", "name": "x", "status": "active", "due": "tomorrow"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_id() -> None:
    with pytest.raises(ModelError):
        Project.from_dict({"id": "Bad ID!", "name": "x", "status": "active"})


def test_project_defaults_fill_missing_fields() -> None:
    p = Project.from_dict({"id": "x", "name": "x", "status": "active"})
    assert p.tags == []
    assert p.labels == []
    assert p.worktrees == []
    assert p.priority is None
    assert p.due is None
```

- [ ] **Step 2: Run — expect ImportError**

```bash
pytest tests/test_model.py -v
```

- [ ] **Step 3: Implement enums and Project**

Create `apps/lab/src/lab/model.py`:

```python
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelError(ValueError):
    """Raised when model validation fails."""


class ProjectStatus(str, Enum):
    active = "active"
    paused = "paused"
    done = "done"
    archived = "archived"


class TaskStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-_]*$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_enum(enum_cls, value, *, field_name: str):
    if value is None:
        return None
    try:
        return enum_cls(value)
    except ValueError:
        allowed = ", ".join(e.value for e in enum_cls)
        raise ModelError(f"{field_name}: {value!r} is not one of: {allowed}")


def _parse_date(value, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        raise ModelError(f"{field_name}: {value!r} is not YYYY-MM-DD")
    try:
        _dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ModelError(f"{field_name}: invalid date ({exc})") from exc
    return value


def _today() -> str:
    return _dt.date.today().isoformat()


def _validate_id(value: str, *, field_name: str = "id") -> str:
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ModelError(f"{field_name}: {value!r} must match [a-z0-9][a-z0-9\\-_]*")
    return value


@dataclass
class Project:
    id: str
    name: str
    status: ProjectStatus = ProjectStatus.active
    description: str = ""
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    priority: Priority | None = None
    loe: float | None = None
    due: str | None = None
    created: str = field(default_factory=_today)
    updated: str = field(default_factory=_today)
    worktrees: list[dict[str, Any]] = field(default_factory=list)
    prs: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    pinned: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Project:
        return cls(
            id=_validate_id(data.get("id", "")),
            name=str(data.get("name", "")),
            description=str(data.get("description", "")),
            status=_parse_enum(ProjectStatus, data.get("status", "active"), field_name="status"),
            tags=list(data.get("tags", []) or []),
            labels=list(data.get("labels", []) or []),
            priority=_parse_enum(Priority, data.get("priority"), field_name="priority"),
            loe=(None if data.get("loe") is None else float(data["loe"])),
            due=_parse_date(data.get("due"), field_name="due"),
            created=_parse_date(data.get("created", _today()), field_name="created") or _today(),
            updated=_parse_date(data.get("updated", _today()), field_name="updated") or _today(),
            worktrees=list(data.get("worktrees", []) or []),
            prs=list(data.get("prs", []) or []),
            artifacts=list(data.get("artifacts", []) or []),
            pinned=list(data.get("pinned", []) or []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status.value,
            "tags": list(self.tags),
            "labels": list(self.labels),
            "priority": self.priority.value if self.priority else None,
            "loe": self.loe,
            "due": self.due,
            "created": self.created,
            "updated": self.updated,
            "worktrees": list(self.worktrees),
            "prs": list(self.prs),
            "artifacts": list(self.artifacts),
            "pinned": list(self.pinned),
        }
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_model.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/src/lab/model.py apps/lab/tests/test_model.py
git commit -m "feat(lab): model enums and Project dataclass"
```

---

## Task 8: Extend `model.py` with `Task` dataclass (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/tests/test_model.py`
- Modify: `~/src/productivity-new/apps/lab/src/lab/model.py`

- [ ] **Step 1: Append failing tests for Task**

Append to `apps/lab/tests/test_model.py`:

```python


from lab.model import Task, TaskStatus


def test_task_status_enum_values() -> None:
    assert {s.value for s in TaskStatus} == {"todo", "in_progress", "blocked", "done"}


def test_task_from_dict_roundtrip() -> None:
    data = {
        "id": 2,
        "title": "Review",
        "status": "in_progress",
        "priority": "P1",
        "loe": 0.5,
        "due": "2026-04-20",
        "tags": ["review"],
        "labels": [],
        "blocker": None,
        "notes_file": "notes/002-review.md",
        "created": "2026-04-15",
        "updated": "2026-04-16",
        "closed_at": None,
    }
    t = Task.from_dict(data)
    assert t.id == 2
    assert t.status is TaskStatus.in_progress
    assert t.priority is Priority.P1
    assert t.to_dict() == data


def test_task_requires_priority() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": 1, "title": "x", "status": "todo"})


def test_task_rejects_negative_id() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": -1, "title": "x", "status": "todo", "priority": "P2"})


def test_task_rejects_empty_title() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": 1, "title": "", "status": "todo", "priority": "P2"})


def test_task_done_requires_closed_at_in_to_dict() -> None:
    # Storing a done task writes closed_at; model does not compute it — caller does.
    t = Task.from_dict({
        "id": 1, "title": "x", "status": "done", "priority": "P2",
        "closed_at": "2026-04-16T12:00:00-07:00",
    })
    assert t.closed_at == "2026-04-16T12:00:00-07:00"
```

- [ ] **Step 2: Run — expect failures**

```bash
pytest tests/test_model.py -v
```

- [ ] **Step 3: Append Task class to `model.py`**

Append to `apps/lab/src/lab/model.py`:

```python


@dataclass
class Task:
    id: int
    title: str
    status: TaskStatus
    priority: Priority
    loe: float | None = None
    due: str | None = None
    tags: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    blocker: str | None = None
    notes_file: str | None = None
    created: str = field(default_factory=_today)
    updated: str = field(default_factory=_today)
    closed_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        task_id = data.get("id")
        if not isinstance(task_id, int) or task_id < 1:
            raise ModelError(f"id: {task_id!r} must be a positive integer")
        title = str(data.get("title", "")).strip()
        if not title:
            raise ModelError("title must be non-empty")
        status = _parse_enum(TaskStatus, data.get("status", "todo"), field_name="status")
        priority = _parse_enum(Priority, data.get("priority"), field_name="priority")
        if priority is None:
            raise ModelError("priority is required (P0..P3)")
        return cls(
            id=task_id,
            title=title,
            status=status,
            priority=priority,
            loe=(None if data.get("loe") is None else float(data["loe"])),
            due=_parse_date(data.get("due"), field_name="due"),
            tags=list(data.get("tags", []) or []),
            labels=list(data.get("labels", []) or []),
            blocker=(str(data["blocker"]) if data.get("blocker") else None),
            notes_file=(str(data["notes_file"]) if data.get("notes_file") else None),
            created=_parse_date(data.get("created", _today()), field_name="created") or _today(),
            updated=_parse_date(data.get("updated", _today()), field_name="updated") or _today(),
            closed_at=(str(data["closed_at"]) if data.get("closed_at") else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status.value,
            "priority": self.priority.value,
            "loe": self.loe,
            "due": self.due,
            "tags": list(self.tags),
            "labels": list(self.labels),
            "blocker": self.blocker,
            "notes_file": self.notes_file,
            "created": self.created,
            "updated": self.updated,
            "closed_at": self.closed_at,
        }
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_model.py -v
```

Expected: 14 passed (8 from Task 7 + 6 new).

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/src/lab/model.py apps/lab/tests/test_model.py
git commit -m "feat(lab): Task dataclass with required priority and round-trip"
```

---

## Task 9: Register project + task subcommand groups in `cli.py`

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/cli.py`
- Create: `~/src/productivity-new/apps/lab/src/lab/commands/project.py` (stub)
- Create: `~/src/productivity-new/apps/lab/src/lab/commands/task.py` (stub)
- Create: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`
- Create: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Write failing tests for subgroup presence**

Create `apps/lab/tests/test_cli_project.py`:

```python
from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_project_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "--help"])
    assert result.exit_code == 0, result.output
    assert "project" in result.output.lower()
```

Create `apps/lab/tests/test_cli_task.py`:

```python
from __future__ import annotations

from click.testing import CliRunner

from lab.cli import main


def test_task_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["task", "--help"])
    assert result.exit_code == 0, result.output
    assert "task" in result.output.lower()
```

- [ ] **Step 2: Run — expect failure**

```bash
pytest tests/test_cli_project.py tests/test_cli_task.py -v
```

- [ ] **Step 3: Create subcommand stub files**

Create `apps/lab/src/lab/commands/project.py`:

```python
from __future__ import annotations

import click


@click.group(name="project")
def project_group() -> None:
    """Project lifecycle commands."""
```

Create `apps/lab/src/lab/commands/task.py`:

```python
from __future__ import annotations

import click


@click.group(name="task")
def task_group() -> None:
    """Task lifecycle commands."""
```

- [ ] **Step 4: Wire subgroups into `cli.py`**

Replace `apps/lab/src/lab/cli.py` with:

```python
from __future__ import annotations

import click

from lab.commands.project import project_group
from lab.commands.task import task_group


@click.group()
@click.version_option(package_name="lab")
def main() -> None:
    """Unified CLI for the productivity monorepo."""


main.add_command(project_group)
main.add_command(task_group)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run — expect pass**

```bash
pytest tests/test_cli_project.py tests/test_cli_task.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/src/lab/cli.py apps/lab/src/lab/commands apps/lab/tests/test_cli_project.py apps/lab/tests/test_cli_task.py
git commit -m "feat(lab): register project and task subgroups in CLI"
```

---

## Task 10: `lab project new` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/project.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/lab/tests/test_cli_project.py`:

```python

import json
from pathlib import Path

from lab.cli import main


def test_project_new_creates_directory_and_files(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "new", "davi-vision", "--desc", "Reshape DAVI"])
    assert result.exit_code == 0, result.output
    pdir = monorepo / "knowledge" / "projects" / "davi-vision"
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
    proj = json.loads((monorepo / "knowledge" / "projects" / "drools-rate" / "project.json").read_text())
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


def test_project_new_creates_per_project_CLAUDE_md(monorepo: Path) -> None:
    runner = CliRunner()
    runner.invoke(main, ["project", "new", "x", "--desc", "Do stuff"])
    claude = (monorepo / "knowledge" / "projects" / "x" / "CLAUDE.md").read_text()
    assert "x" in claude and "Do stuff" in claude
    assert "lab project status" in claude
```

- [ ] **Step 2: Run — expect failures**

```bash
pytest tests/test_cli_project.py -v
```

- [ ] **Step 3: Implement `project new`**

Replace `apps/lab/src/lab/commands/project.py` with:

```python
from __future__ import annotations

from pathlib import Path

import click

from lab import paths, storage
from lab.model import ModelError, Priority, Project, ProjectStatus, _validate_id  # noqa: F401 (reuse validation)

_CLAUDE_TEMPLATE = """# {name}

## Objective
{description}

## On session start
Run `lab project status` for current state.
Check the dashboard at http://localhost:3333/p/{id} (Plan 2+).

## Task operations
Use `lab task ...`. Current tasks: `lab task ls`.

## Available tools (populated in later plans)
- `apps/darwin-runner` — matplotlib charts on Darwin kernel
- `apps/darwin-backups q "…"` — query past notebooks
- `apps/trustim-ir-cli` — inResponse queries

Shared agents at repo root `.claude/agents/`. Templates at `knowledge/skills/`.
"""


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


@click.group(name="project")
def project_group() -> None:
    """Project lifecycle commands."""


@project_group.command("new")
@click.argument("project_id")
@click.option("--desc", "description", default="", help="Short description")
@click.option("--priority", type=click.Choice([p.value for p in Priority]), default=None)
@click.option("--due", default=None, help="Due date YYYY-MM-DD")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--labels", default="", help="Comma-separated MP labels")
def new(project_id: str, description: str, priority: str | None, due: str | None,
        tags: str, labels: str) -> None:
    """Create a new project under knowledge/projects/<id>/."""
    root = paths.find_monorepo_root()
    pdir = paths.project_dir(root, project_id)

    if pdir.exists():
        raise click.ClickException(f"project {project_id!r} already exists at {pdir}")

    try:
        project = Project.from_dict({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "priority": priority,
            "due": due,
            "tags": _split_csv(tags),
            "labels": _split_csv(labels),
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    (pdir / "docs").mkdir(parents=True)
    (pdir / "notes").mkdir()
    (pdir / "assets").mkdir()

    storage.write_json(paths.project_file(root, project_id), project.to_dict())
    storage.write_json(paths.tasks_file(root, project_id), {"next_id": 1, "tasks": []})

    (pdir / "CLAUDE.md").write_text(
        _CLAUDE_TEMPLATE.format(
            id=project.id,
            name=project.name,
            description=project.description or "(not yet defined — set with `lab project set <id> description \"...\"`)",
        ),
        encoding="utf-8",
    )

    click.echo(f"created {project_id} at {pdir}")
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_cli_project.py -v
```

Expected: 6 passed (1 from Task 9 + 5 new).

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab
git commit -m "feat(lab): project new with CLAUDE.md scaffolding"
```

---

## Task 11: `lab project ls` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/project.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/lab/tests/test_cli_project.py`:

```python


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
```

- [ ] **Step 2: Run — expect failures**

```bash
pytest tests/test_cli_project.py -v
```

- [ ] **Step 3: Append `ls` command**

Append to `apps/lab/src/lab/commands/project.py`:

```python


def _iter_project_files(root: Path):
    projects_root = root / "knowledge" / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        pjson = child / "project.json"
        if pjson.is_file():
            yield pjson


@project_group.command("ls")
@click.option("--status", type=click.Choice([s.value for s in ProjectStatus]), default=None)
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
def ls(status: str | None, tag_filter: str | None, label_filter: str | None) -> None:
    """List projects (default: all)."""
    root = paths.find_monorepo_root()
    rows = []
    for pjson in _iter_project_files(root):
        data = storage.read_json(pjson)
        if status and data.get("status") != status:
            continue
        if tag_filter and tag_filter not in (data.get("tags") or []):
            continue
        if label_filter and label_filter not in (data.get("labels") or []):
            continue
        rows.append(data)

    if not rows:
        click.echo("no projects")
        return

    width_id = max(len(r["id"]) for r in rows)
    for r in rows:
        priority = r.get("priority") or "--"
        due = r.get("due") or "--"
        desc = (r.get("description") or "").strip().split("\n")[0][:60]
        click.echo(f"{r['id']:<{width_id}}  {r['status']:<8}  {priority:<2}  {due:<10}  {desc}")
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_cli_project.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab
git commit -m "feat(lab): project ls with status/tag/label filters"
```

---

## Task 12: `lab project status` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/project.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`

- [ ] **Step 1: Append failing tests**

Append to `apps/lab/tests/test_cli_project.py`:

```python


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
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append `status` command**

Append to `apps/lab/src/lab/commands/project.py`:

```python


def _resolve_project_id(explicit: str | None) -> str:
    if explicit:
        return explicit
    root = paths.find_monorepo_root()
    projects_root = (root / "knowledge" / "projects").resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if candidate.parent == projects_root:
            return candidate.name
        if candidate == root:
            break
    raise click.ClickException("no project — pass <id> or cd into a project folder")


@project_group.command("status")
@click.argument("project_id", required=False)
def status(project_id: str | None) -> None:
    """Print a summary of a project (uses PWD if no id given)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")
    data = storage.read_json(pjson)

    tjson = paths.tasks_file(root, pid)
    task_counts = {"todo": 0, "in_progress": 0, "blocked": 0, "done": 0}
    if tjson.is_file():
        for t in storage.read_json(tjson).get("tasks", []):
            task_counts[t["status"]] = task_counts.get(t["status"], 0) + 1

    click.echo(f"{data['id']}  ({data['status']})")
    if data.get("description"):
        click.echo(f"  {data['description']}")
    click.echo(
        f"  tasks: todo={task_counts['todo']} in_progress={task_counts['in_progress']} "
        f"blocked={task_counts['blocked']} done={task_counts['done']}"
    )
    if data.get("priority"):
        click.echo(f"  priority: {data['priority']}")
    if data.get("due"):
        click.echo(f"  due: {data['due']}")
    if data.get("tags"):
        click.echo(f"  tags: {', '.join(data['tags'])}")
    if data.get("labels"):
        click.echo(f"  labels: {', '.join(data['labels'])}")
```

- [ ] **Step 4: Run — expect pass**

```bash
pytest tests/test_cli_project.py -v
```

Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab
git commit -m "feat(lab): project status with PWD auto-detect"
```

---

## Task 13: `lab project set` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/project.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`

- [ ] **Step 1: Append failing tests**

```python


def test_project_set_updates_field(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "description", "New desc"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "project.json").read_text())
    assert data["description"] == "New desc"


def test_project_set_status(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "set", "alpha", "status", "paused"])
    assert result.exit_code == 0
    data = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "project.json").read_text())
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
    data = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "project.json").read_text())
    assert data["priority"] == "P0"
    assert data["due"] == "2026-05-15"


def test_project_set_tags_and_labels_csv(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["project", "set", "alpha", "tags", "a,b,c"])
    runner.invoke(main, ["project", "set", "alpha", "labels", "lipy-davi"])
    data = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "project.json").read_text())
    assert data["tags"] == ["a", "b", "c"]
    assert data["labels"] == ["lipy-davi"]
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append `set` command**

At the top of `apps/lab/src/lab/commands/project.py`, add this import next to the existing imports:

```python
from datetime import date
```

Then append:

```python


_PROJECT_SETTABLE = {
    "description", "status", "priority", "due", "loe", "tags", "labels", "name",
}


@project_group.command("set")
@click.argument("project_id")
@click.argument("field")
@click.argument("value")
def set_field(project_id: str, field: str, value: str) -> None:
    """Update a single field on a project (validated)."""
    if field not in _PROJECT_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_PROJECT_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise click.ClickException(f"project {project_id!r} not found")
    data = storage.read_json(pjson)

    if field in {"tags", "labels"}:
        data[field] = _split_csv(value)
    elif field == "loe":
        data[field] = float(value) if value not in {"", "null", "none"} else None
    elif field in {"priority", "due", "status"}:
        data[field] = value if value not in {"", "null", "none"} else None
    else:
        data[field] = value

    data["updated"] = date.today().isoformat()

    try:
        Project.from_dict(data)  # validate the whole doc
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    storage.write_json(pjson, data)
    click.echo(f"{project_id}.{field} = {data[field]!r}")
```

- [ ] **Step 4: Run — expect pass**

Expected: 17 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): project set with per-field validation"
```

---

## Task 14: `lab project archive` and `lab project rm` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/project.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_project.py`

- [ ] **Step 1: Append failing tests**

```python


def test_project_archive(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "archive", "alpha"])
    assert result.exit_code == 0, result.output
    data = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "project.json").read_text())
    assert data["status"] == "archived"


def test_project_rm_requires_confirmation(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    # No confirmation → aborts
    result = runner.invoke(main, ["project", "rm", "alpha"], input="\n")
    assert result.exit_code != 0
    assert (monorepo / "knowledge" / "projects" / "alpha").exists()


def test_project_rm_with_force(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["project", "rm", "alpha", "--yes"])
    assert result.exit_code == 0, result.output
    assert not (monorepo / "knowledge" / "projects" / "alpha").exists()


def test_project_rm_missing(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["project", "rm", "nope", "--yes"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append commands**

```python


@project_group.command("archive")
@click.argument("project_id")
def archive(project_id: str) -> None:
    """Set status to archived (hidden from default dashboard)."""
    root = paths.find_monorepo_root()
    pjson = paths.project_file(root, project_id)
    if not pjson.is_file():
        raise click.ClickException(f"project {project_id!r} not found")
    data = storage.read_json(pjson)
    data["status"] = "archived"
    from datetime import date
    data["updated"] = date.today().isoformat()
    storage.write_json(pjson, data)
    click.echo(f"archived {project_id}")


@project_group.command("rm")
@click.argument("project_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
def rm(project_id: str, yes: bool) -> None:
    """Delete a project folder permanently. Worktrees, if any, must be removed first (later plan)."""
    import shutil

    root = paths.find_monorepo_root()
    pdir = paths.project_dir(root, project_id)
    if not pdir.is_dir():
        raise click.ClickException(f"project {project_id!r} not found")

    if not yes:
        click.confirm(
            f"Permanently delete {pdir}? This cannot be undone.",
            abort=True,
        )

    shutil.rmtree(pdir)
    click.echo(f"removed {project_id}")
```

- [ ] **Step 4: Run — expect pass**

Expected: 21 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): project archive and rm with confirmation"
```

---

## Task 15: `lab task new` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/task.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Append failing tests**

```python

import json
from pathlib import Path

from lab.cli import main


def test_task_new_basic(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Draft one-pager",
        "--project", "alpha", "--priority", "P1",
    ])
    assert result.exit_code == 0, result.output
    tasks = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())
    assert tasks["next_id"] == 2
    assert len(tasks["tasks"]) == 1
    t = tasks["tasks"][0]
    assert t["id"] == 1
    assert t["title"] == "Draft one-pager"
    assert t["priority"] == "P1"
    assert t["status"] == "todo"


def test_task_new_with_file_creates_notes(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Review one-pager with Jesus",
        "--project", "alpha", "--priority", "P1", "--file",
    ])
    assert result.exit_code == 0, result.output
    notes_dir = monorepo / "knowledge" / "projects" / "alpha" / "notes"
    notes = list(notes_dir.iterdir())
    assert len(notes) == 1
    content = notes[0].read_text()
    assert "Review one-pager with Jesus" in content


def test_task_new_auto_detects_project_from_pwd(monorepo: Path, seed_project, monkeypatch) -> None:
    pdir = seed_project("alpha")
    monkeypatch.chdir(pdir)
    runner = CliRunner()
    result = runner.invoke(main, ["task", "new", "Inline task", "--priority", "P2"])
    assert result.exit_code == 0, result.output


def test_task_new_requires_priority(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "new", "No priority", "--project", "alpha"])
    assert result.exit_code != 0


def test_task_new_full_fields(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Review", "--project", "alpha",
        "--priority", "P1", "--loe", "0.5", "--due", "2026-04-20",
        "--tags", "review,meet", "--labels", "lipy-davi",
    ])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["loe"] == 0.5
    assert t["due"] == "2026-04-20"
    assert t["tags"] == ["review", "meet"]
    assert t["labels"] == ["lipy-davi"]


def test_task_new_next_id_increments(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "a", "--project", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "new", "b", "--project", "alpha", "--priority", "P2"])
    tasks = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())
    assert tasks["next_id"] == 3
    assert [t["id"] for t in tasks["tasks"]] == [1, 2]
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Implement `task` module with `new` command**

Replace `apps/lab/src/lab/commands/task.py`:

```python
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import click

from lab import paths, storage
from lab.model import ModelError, Priority, Task, TaskStatus


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    return _SLUG_RE.sub("-", title.lower()).strip("-")[:40] or "task"


def _resolve_project_id(explicit: str | None) -> str:
    if explicit:
        return explicit
    root = paths.find_monorepo_root()
    projects_root = (root / "knowledge" / "projects").resolve()
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if candidate.parent == projects_root:
            return candidate.name
        if candidate == root:
            break
    raise click.ClickException("no project — pass --project <id> or cd into a project folder")


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _load_tasks(root: Path, project_id: str) -> dict:
    tjson = paths.tasks_file(root, project_id)
    if not tjson.is_file():
        raise click.ClickException(f"project {project_id!r} has no tasks.json")
    return storage.read_json(tjson)


def _save_tasks(root: Path, project_id: str, data: dict) -> None:
    storage.write_json(paths.tasks_file(root, project_id), data)


@click.group(name="task")
def task_group() -> None:
    """Task lifecycle commands."""


@task_group.command("new")
@click.argument("title")
@click.option("--project", "project_id", default=None)
@click.option("--priority", type=click.Choice([p.value for p in Priority]), required=True)
@click.option("--loe", type=float, default=None)
@click.option("--due", default=None)
@click.option("--tags", default="")
@click.option("--labels", default="")
@click.option("--file", "create_file", is_flag=True, default=False, help="Create a notes md file")
def new(title: str, project_id: str | None, priority: str, loe: float | None,
        due: str | None, tags: str, labels: str, create_file: bool) -> None:
    """Create a new task in a project (default: PWD project)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    pjson = paths.project_file(root, pid)
    if not pjson.is_file():
        raise click.ClickException(f"project {pid!r} not found")

    tasks_doc = _load_tasks(root, pid)
    task_id = int(tasks_doc.get("next_id", 1))
    slug = _slugify(title)
    notes_file = None
    if create_file:
        notes_rel = f"notes/{task_id:03d}-{slug}.md"
        notes_path = paths.project_dir(root, pid) / notes_rel
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        if not notes_path.exists():
            notes_path.write_text(f"# {title}\n\n", encoding="utf-8")
        notes_file = notes_rel

    try:
        task = Task.from_dict({
            "id": task_id,
            "title": title,
            "status": "todo",
            "priority": priority,
            "loe": loe,
            "due": due,
            "tags": _split_csv(tags),
            "labels": _split_csv(labels),
            "notes_file": notes_file,
        })
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    tasks_doc["tasks"].append(task.to_dict())
    tasks_doc["next_id"] = task_id + 1
    _save_tasks(root, pid, tasks_doc)

    click.echo(f"{pid}#{task_id}  {title}")
```

- [ ] **Step 4: Run — expect pass**

Expected: 7 passed (1 existing + 6 new).

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): task new with optional notes file and PWD auto-detect"
```

---

## Task 16: `lab task ls` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/task.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Append failing tests**

```python


def test_task_ls_empty(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "ls", "--project", "alpha"])
    assert result.exit_code == 0
    assert "no tasks" in result.output.lower()


def test_task_ls_cross_project(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "alpha-task", "--project", "alpha", "--priority", "P1"])
    runner.invoke(main, ["task", "new", "beta-task", "--project", "beta", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls"])
    assert result.exit_code == 0
    assert "alpha-task" in result.output
    assert "beta-task" in result.output


def test_task_ls_filter_by_status(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "open-one", "--project", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "new", "will-close", "--project", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "done", "2", "--project", "alpha"])

    result = runner.invoke(main, ["task", "ls", "--project", "alpha", "--status", "open"])
    assert "open-one" in result.output
    assert "will-close" not in result.output

    result = runner.invoke(main, ["task", "ls", "--project", "alpha", "--status", "done"])
    assert "will-close" in result.output
    assert "open-one" not in result.output


def test_task_ls_filter_by_due_window(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    from datetime import date, timedelta
    near = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    runner.invoke(main, ["task", "new", "near", "--project", "alpha", "--priority", "P2", "--due", near])
    runner.invoke(main, ["task", "new", "far", "--project", "alpha", "--priority", "P2", "--due", far])

    result = runner.invoke(main, ["task", "ls", "--project", "alpha", "--due", "7d"])
    assert "near" in result.output
    assert "far" not in result.output
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append `ls` command**

```python


def _iter_all_tasks(root: Path):
    projects_root = root / "knowledge" / "projects"
    if not projects_root.is_dir():
        return
    for child in sorted(projects_root.iterdir()):
        tjson = child / "tasks.json"
        if not tjson.is_file():
            continue
        doc = storage.read_json(tjson)
        for t in doc.get("tasks", []):
            yield child.name, t


def _parse_due_window(value: str) -> int | None:
    m = re.fullmatch(r"(\d+)d", value)
    if not m:
        raise click.ClickException(f"--due must be Nd (e.g. 7d); got {value!r}")
    return int(m.group(1))


@task_group.command("ls")
@click.option("--project", "project_id", default=None)
@click.option("--status", default=None, help="todo|in_progress|blocked|done|open (= not done)")
@click.option("--priority", default=None, help="Comma-separated (e.g. P0,P1)")
@click.option("--tag", "tag_filter", default=None)
@click.option("--label", "label_filter", default=None)
@click.option("--due", "due_window", default=None, help="Nd — due within N days")
def ls(project_id: str | None, status: str | None, priority: str | None,
       tag_filter: str | None, label_filter: str | None,
       due_window: str | None) -> None:
    """List tasks. Default: all projects. Filter with --project, --status, --priority, --tag, --label, --due."""
    from datetime import date, timedelta

    root = paths.find_monorepo_root()

    if project_id:
        it = ((project_id, t) for t in _load_tasks(root, project_id).get("tasks", []))
    else:
        it = _iter_all_tasks(root)

    pr_set = set(_split_csv(priority)) if priority else None
    horizon = None
    if due_window:
        days = _parse_due_window(due_window)
        horizon = date.today() + timedelta(days=days)

    rows = []
    for pid, t in it:
        if status == "open":
            if t["status"] == "done":
                continue
        elif status:
            if t["status"] != status:
                continue
        if pr_set and t["priority"] not in pr_set:
            continue
        if tag_filter and tag_filter not in (t.get("tags") or []):
            continue
        if label_filter and label_filter not in (t.get("labels") or []):
            continue
        if horizon:
            due = t.get("due")
            if not due or date.fromisoformat(due) > horizon:
                continue
        rows.append((pid, t))

    if not rows:
        click.echo("no tasks")
        return

    w_pid = max(len(pid) for pid, _ in rows)
    for pid, t in rows:
        due = t.get("due") or "--"
        click.echo(
            f"{pid:<{w_pid}}  #{t['id']:<3}  {t['status']:<11}  {t['priority']}  {due:<10}  {t['title']}"
        )
```

- [ ] **Step 4: Run — expect pass**

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): task ls with status/priority/tag/label/due filters"
```

---

## Task 17: `lab task done` and `lab task reopen` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/task.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Append failing tests**

```python


def test_task_done_sets_closed_at(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "ship it", "--project", "alpha", "--priority", "P1"])
    result = runner.invoke(main, ["task", "done", "1", "--project", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "done"
    assert t["closed_at"] is not None


def test_task_reopen_clears_closed_at(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "ship", "--project", "alpha", "--priority", "P1"])
    runner.invoke(main, ["task", "done", "1", "--project", "alpha"])
    result = runner.invoke(main, ["task", "reopen", "1", "--project", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "in_progress"
    assert t["closed_at"] is None


def test_task_done_missing_task(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "done", "99", "--project", "alpha"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append commands**

```python


def _find_task(tasks_doc: dict, task_id: int) -> dict:
    for t in tasks_doc.get("tasks", []):
        if t["id"] == task_id:
            return t
    raise click.ClickException(f"task #{task_id} not found")


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(tz=timezone.utc).astimezone().isoformat(timespec="seconds")


@task_group.command("done")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def done(task_id: int, project_id: str | None) -> None:
    """Mark a task done (sets closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "done"
    t["closed_at"] = _now_iso()
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  done")


@task_group.command("reopen")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def reopen(task_id: int, project_id: str | None) -> None:
    """Reopen a done task (status → in_progress, clears closed_at)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["closed_at"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  reopened")
```

- [ ] **Step 4: Run — expect pass**

Expected: 14 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): task done / reopen with closed_at"
```

---

## Task 18: `lab task block` and `lab task unblock` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/task.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Append failing tests**

```python


def test_task_block_sets_blocker(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "blocked-task", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "block", "1", "waiting on legal", "--project", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "blocked"
    assert t["blocker"] == "waiting on legal"


def test_task_unblock_clears(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--project", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "block", "1", "stuck", "--project", "alpha"])
    result = runner.invoke(main, ["task", "unblock", "1", "--project", "alpha"])
    assert result.exit_code == 0
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "in_progress"
    assert t["blocker"] is None
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append commands**

```python


@task_group.command("block")
@click.argument("task_id", type=int)
@click.argument("reason")
@click.option("--project", "project_id", default=None)
def block(task_id: int, reason: str, project_id: str | None) -> None:
    """Mark a task blocked with a reason."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "blocked"
    t["blocker"] = reason
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  blocked: {reason}")


@task_group.command("unblock")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def unblock(task_id: int, project_id: str | None) -> None:
    """Clear a task's blocker (status → in_progress)."""
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    t["status"] = "in_progress"
    t["blocker"] = None
    t["updated"] = date.today().isoformat()
    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}  unblocked")
```

- [ ] **Step 4: Run — expect pass**

Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): task block / unblock"
```

---

## Task 19: `lab task show` and `lab task set` (TDD)

**Files:**
- Modify: `~/src/productivity-new/apps/lab/src/lab/commands/task.py`
- Modify: `~/src/productivity-new/apps/lab/tests/test_cli_task.py`

- [ ] **Step 1: Append failing tests**

```python


def test_task_show(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "Review", "--project", "alpha", "--priority", "P1", "--file"])
    result = runner.invoke(main, ["task", "show", "1", "--project", "alpha"])
    assert result.exit_code == 0
    assert "Review" in result.output
    assert "P1" in result.output
    # Notes file content is shown too
    assert "# Review" in result.output


def test_task_set_field(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "priority", "P0", "--project", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["priority"] == "P0"


def test_task_set_rejects_unknown_field(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--project", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "foo", "bar", "--project", "alpha"])
    assert result.exit_code != 0


def test_task_set_tags_csv(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--project", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "set", "1", "tags", "a,b", "--project", "alpha"])
    t = json.loads((monorepo / "knowledge" / "projects" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["tags"] == ["a", "b"]
```

- [ ] **Step 2: Run — expect failures**

- [ ] **Step 3: Append commands**

```python


_TASK_SETTABLE = {"title", "priority", "loe", "due", "tags", "labels", "status"}


@task_group.command("show")
@click.argument("task_id", type=int)
@click.option("--project", "project_id", default=None)
def show(task_id: int, project_id: str | None) -> None:
    """Print a task's fields and notes file content (if any)."""
    import json as _json

    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)
    click.echo(_json.dumps(t, indent=2))
    notes_file = t.get("notes_file")
    if notes_file:
        notes_path = paths.project_dir(root, pid) / notes_file
        if notes_path.is_file():
            click.echo("")
            click.echo(f"--- {notes_file} ---")
            click.echo(notes_path.read_text())


@task_group.command("set")
@click.argument("task_id", type=int)
@click.argument("field")
@click.argument("value")
@click.option("--project", "project_id", default=None)
def set_field(task_id: int, field: str, value: str, project_id: str | None) -> None:
    """Update a single task field (validated)."""
    if field not in _TASK_SETTABLE:
        raise click.ClickException(
            f"{field} is not settable. Allowed: {sorted(_TASK_SETTABLE)}"
        )
    root = paths.find_monorepo_root()
    pid = _resolve_project_id(project_id)
    doc = _load_tasks(root, pid)
    t = _find_task(doc, task_id)

    if field in {"tags", "labels"}:
        t[field] = _split_csv(value)
    elif field == "loe":
        t[field] = float(value)
    elif field in {"priority", "due", "status", "title"}:
        t[field] = value

    t["updated"] = date.today().isoformat()

    try:
        Task.from_dict(t)  # validate
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc

    _save_tasks(root, pid, doc)
    click.echo(f"{pid}#{task_id}.{field} = {t[field]!r}")
```

- [ ] **Step 4: Run — expect pass**

Expected: 20 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/lab && git commit -m "feat(lab): task show and task set"
```

---

## Task 20: Install and smoke-test `lab` on PATH

**Files:** (no new files — verify end-to-end)

- [ ] **Step 1: Run `make install` from monorepo root**

```bash
cd ~/src/productivity-new
make install
```

Expected:
```
Installed lab → /Users/jcortes/.local/bin/lab
Ensure /Users/jcortes/.local/bin is on your PATH.
```

- [ ] **Step 2: Smoke-test `lab` from a terminal**

In a new terminal (to pick up PATH):

```bash
lab --version
lab --help
lab project --help
lab task --help
```

Expected: all four print help text without error.

- [ ] **Step 3: Live end-to-end walkthrough**

```bash
cd ~/src/productivity-new
lab project new inbox --desc "Catch-all for standalone reminders"
lab project new davi-test-vision --desc "Test project" --priority P1 --labels lipy-davi
lab project ls

cd knowledge/projects/davi-test-vision
lab task new "Draft one-pager" --priority P1 --due 2026-04-20 --file
lab task new "Review with Jesus" --priority P1 --loe 0.5
lab task ls
lab task done 1
lab task block 2 "waiting on Jesus availability"
lab task ls --status open
lab project status
```

Verify output matches expectations: two projects listed, two tasks, second one blocked, first one done.

- [ ] **Step 4: Commit** (if any hand-fixes needed during smoke test)

```bash
cd ~/src/productivity-new
git status
# If changes, commit as: "fix(lab): smoke-test corrections"
```

No commit needed if smoke test passed cleanly.

---

## Task 21: End-to-end integration test

**Files:**
- Create: `~/src/productivity-new/apps/lab/tests/test_integration_e2e.py`

- [ ] **Step 1: Write the integration test**

Create `apps/lab/tests/test_integration_e2e.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_full_project_lifecycle(monorepo: Path) -> None:
    """Create project → add tasks → flip statuses → list → archive."""
    runner = CliRunner()

    # Create two projects
    r = runner.invoke(main, ["project", "new", "inbox", "--desc", "Catch-all"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["project", "new", "davi-test", "--desc", "Test", "--priority", "P1"])
    assert r.exit_code == 0, r.output

    # Add tasks to davi-test
    for i, (title, pri) in enumerate([("draft", "P1"), ("review", "P1"), ("ship", "P2")], start=1):
        r = runner.invoke(main, ["task", "new", title, "--project", "davi-test", "--priority", pri])
        assert r.exit_code == 0, r.output

    # Add a reminder to inbox
    r = runner.invoke(main, [
        "task", "new", "email someone", "--project", "inbox", "--priority", "P3",
    ])
    assert r.exit_code == 0

    # Flip states
    runner.invoke(main, ["task", "done", "1", "--project", "davi-test"])
    runner.invoke(main, ["task", "block", "2", "waiting on Jesus", "--project", "davi-test"])

    # Cross-project ls
    r = runner.invoke(main, ["task", "ls"])
    assert r.exit_code == 0
    assert "draft" in r.output
    assert "email someone" in r.output

    # Filter: open tasks only
    r = runner.invoke(main, ["task", "ls", "--status", "open"])
    assert "draft" not in r.output  # done
    assert "review" in r.output      # blocked still counts as open
    assert "ship" in r.output
    assert "email someone" in r.output

    # Filter: high-priority (P0/P1) open
    r = runner.invoke(main, ["task", "ls", "--status", "open", "--priority", "P0,P1"])
    assert "review" in r.output
    assert "ship" not in r.output     # P2
    assert "email someone" not in r.output  # P3

    # Archive davi-test
    runner.invoke(main, ["project", "archive", "davi-test"])
    r = runner.invoke(main, ["project", "ls", "--status", "active"])
    assert "davi-test" not in r.output
    assert "inbox" in r.output

    # Verify on-disk state
    davi = json.loads((monorepo / "knowledge" / "projects" / "davi-test" / "project.json").read_text())
    assert davi["status"] == "archived"
    tasks = json.loads((monorepo / "knowledge" / "projects" / "davi-test" / "tasks.json").read_text())
    statuses = {t["id"]: t["status"] for t in tasks["tasks"]}
    assert statuses == {1: "done", 2: "blocked", 3: "todo"}
```

- [ ] **Step 2: Run the integration test**

```bash
cd ~/src/productivity-new/apps/lab
source .venv/bin/activate
pytest tests/test_integration_e2e.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Run entire test suite with coverage**

```bash
pytest -v
```

Expected: all tests pass (21 + 1 = ~22+), coverage ≥ 90% on `lab/`.

- [ ] **Step 4: Commit**

```bash
cd ~/src/productivity-new
git add apps/lab/tests/test_integration_e2e.py
git commit -m "test(lab): end-to-end integration covering full project + task lifecycle"
```

---

## Plan 1 — Done when

All of these are true:

1. `~/src/productivity-new/` exists as a git repo with the folder structure from §4 of the spec (minus `multiproducts/`, `apps/backend`, `apps/frontend`, and the tool apps — those come later).
2. `make install` symlinks `lab` into `~/.local/bin/lab` successfully.
3. Running `lab --help` from any directory prints the top-level help.
4. All commands listed at the top of this plan work end-to-end.
5. `pytest -v` passes the full suite with ≥ 90 % coverage on `lab/` package.
6. The commit log tells a clean story, one commit per task.

## What's NOT in Plan 1 (pointer list)

| Feature | Plan |
|---|---|
| Backend FastAPI service, watcher, global `.index.json` | Plan 2 |
| Frontend dashboard, project view, timeline, list view, markdown renderer | Plan 3 |
| `lab project add / remove` (worktrees) + MP prefix config + `lab mp` | Plan 4 |
| `lab search` full-text | Plan 5 |
| `lab pr add`, `lab artifact add`, `lab note` | Plan 5 |
| Migration agent + `lab migrate` (ingests `~/projects/*`) | Plan 6 |
| `apps/darwin-runner`, `apps/darwin-backups`, `apps/trustim-ir-cli` moved in | Plan 7 |
| gdiff + mdview folded into backend | Plan 8 |
| `make seed` sample projects | Plan 9 |

Plan 1 is self-contained: once merged, you can already use `lab` to track everything, even while the web UI and worktrees are still future work.
