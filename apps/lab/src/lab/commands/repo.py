from __future__ import annotations

import subprocess

import click

from lab import mp as mp_mod
from lab import paths


@click.group(name="repo")
def repo_group() -> None:
    """Repository discovery + MP prefix configuration."""


@repo_group.command("ls")
def ls() -> None:
    """List repos available under repositories/ and their configured prefix."""
    root = paths.find_monorepo_root()
    repo_root = root / "repositories"
    prefixes = mp_mod.load_prefixes()
    if not repo_root.is_dir():
        click.echo("(no repositories/ dir — run `make pull-repos`)")
        return
    repos = sorted(
        d.name for d in repo_root.iterdir() if d.is_dir() and (d / ".git").exists()
    )
    if not repos:
        click.echo("(no repos cloned — run `make pull-repos`)")
        return
    width = max(len(r) for r in repos)
    for r in repos:
        pfx = prefixes.get(r, "(no prefix)")
        click.echo(f"{r:<{width}}  {pfx}")


@repo_group.command("prefix")
@click.argument("mp")
@click.argument("prefix")
def prefix(mp: str, prefix: str) -> None:
    """Set/update the short prefix for an MP (e.g. lipy-davi → davi)."""
    prefixes = mp_mod.load_prefixes()
    prefixes[mp] = prefix
    mp_mod.save_prefixes(prefixes)
    click.echo(f"{mp} → {prefix}")


def _default_branch(repo_dir: str) -> str | None:
    """Ask origin what its default branch is (works for master/main/etc)."""
    r = subprocess.run(
        ["git", "-C", repo_dir, "remote", "show", "origin"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("HEAD branch:"):
            name = line.split(":", 1)[1].strip()
            return None if name in ("", "(unknown)") else name
    return None


@repo_group.command("pull")
@click.option("--only", default=None,
              help="Pull a single repo instead of the whole list.")
def pull(only: str | None) -> None:
    """Clone every repo in repositories.list into repositories/.

    Checks out each repo's remote default branch (master, main, ...) and
    pulls. Idempotent: existing clones just get `git pull`. Thin wrapper
    over the same logic `make pull-repos` runs; use whichever you prefer.
    """
    root = paths.find_monorepo_root()
    repo_root = root / "repositories"
    repo_root.mkdir(exist_ok=True)

    list_file = root / "repositories.list"
    if only:
        names = [only]
    elif list_file.is_file():
        names = [ln.strip() for ln in list_file.read_text().splitlines() if ln.strip()]
    else:
        raise click.ClickException(
            f"no repositories.list at {list_file}. Create one (one repo name per line) "
            f"or pass --only <repo>."
        )

    failed: list[str] = []
    for name in names:
        dest = repo_root / name
        if not dest.is_dir():
            click.echo(f"cloning {name}…")
            clone = subprocess.run(
                ["mint", "clone", name],
                cwd=str(repo_root), capture_output=True, text=True,
            )
            if clone.returncode != 0:
                tail = (clone.stderr or clone.stdout).strip().splitlines()[-3:]
                click.echo(f"  ✗ {name}: {' | '.join(tail)}")
                failed.append(name)
                continue
        click.echo(f"updating {name}…")
        default = _default_branch(str(dest))
        if not default:
            click.echo(f"  ↳ skip {name}: origin has no default branch (empty remote?)")
            continue
        subprocess.run(
            ["git", "checkout", default, "--quiet"], cwd=str(dest),
            capture_output=True, text=True,
        )
        pull_r = subprocess.run(
            ["git", "pull", "--quiet"], cwd=str(dest),
            capture_output=True, text=True,
        )
        if pull_r.returncode != 0:
            msg = (pull_r.stderr or pull_r.stdout).strip() or "pull failed"
            click.echo(f"  ✗ {name}: {msg}")
            failed.append(name)

    if failed:
        raise click.ClickException(f"{len(failed)}/{len(names)} failed: {', '.join(failed)}")
    click.echo(f"OK — {len(names)} repo(s) updated in {repo_root}")
