from __future__ import annotations

import subprocess
from pathlib import Path

import click

from lab import mp as mp_mod
from lab import paths


# Repos whose `skills/` directory should be symlinked into the
# monorepo's `.claude/skills/` after a pull. Mapping: repo name on
# disk under `repositories/` → prefix to apply when creating the
# symlink name. The trustim skill folders get an `investigation-`
# prefix so they sort together in the skill list; folders that
# already begin or end with "investigation" are de-duplicated rather
# than getting `investigation-investigation-…`.
_SKILL_LINK_REPOS = {
    "trustim-investigation": "investigation",
}


def _symlink_name_for(skill_folder: str, prefix: str) -> str:
    """Apply ``prefix`` to ``skill_folder`` without doubling it.

    Examples (prefix="investigation"):
      scraping-investigation     → investigation-scraping
      jss-dihe-investigation     → investigation-jss-dihe
      investigation-writing      → investigation-writing  (unchanged)
      investigation-report-...   → investigation-report-... (unchanged)
      ir-cli                     → investigation-ir-cli
    """
    suffix = f"-{prefix}"
    clean = skill_folder[: -len(suffix)] if skill_folder.endswith(suffix) else skill_folder
    if clean.startswith(f"{prefix}-") or clean == prefix:
        return clean
    return f"{prefix}-{clean}"


def _refresh_skill_symlinks(root: Path, repo_name: str | None = None) -> int:
    """Refresh `.claude/skills/<prefix>-<name>` symlinks from each
    configured repo's `skills/` directory.

    If ``repo_name`` is passed, only refresh that one repo's symlinks.
    Stale symlinks (pointing into a repo's skills/ dir but no longer
    matching the source) are removed before fresh ones are created.
    Returns the total count of symlinks in place after the refresh.
    """
    dst_dir = root / ".claude" / "skills"
    dst_dir.mkdir(parents=True, exist_ok=True)
    targets = (
        {repo_name: _SKILL_LINK_REPOS[repo_name]}
        if repo_name and repo_name in _SKILL_LINK_REPOS
        else _SKILL_LINK_REPOS
    )
    # First pass: remove any existing symlinks that point inside the
    # repos we're about to refresh. Anything outside that scope (your
    # own owned skills like one-pager, html-proposal, etc.) is left
    # alone because it's a real directory, not a symlink.
    repo_skill_roots = {
        rn: (root / "repositories" / rn / "skills").resolve()
        for rn in targets
    }
    for child in dst_dir.iterdir():
        if not child.is_symlink():
            continue
        try:
            tgt = child.resolve()
        except OSError:
            child.unlink()
            continue
        for rsr in repo_skill_roots.values():
            if rsr == tgt or rsr in tgt.parents:
                child.unlink()
                break
    # Second pass: create fresh symlinks per repo.
    count = 0
    for rn, prefix in targets.items():
        src_dir = root / "repositories" / rn / "skills"
        if not src_dir.is_dir():
            continue
        for skill in sorted(src_dir.iterdir()):
            if not skill.is_dir():
                continue
            link_name = _symlink_name_for(skill.name, prefix)
            link = dst_dir / link_name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(skill)
            count += 1
    return count


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


def _scan_clones(repo_root) -> list[str]:
    if not repo_root.is_dir():
        return []
    return sorted(
        d.name for d in repo_root.iterdir()
        if d.is_dir() and (d / ".git").exists()
    )


@repo_group.command("pull")
@click.option("--only", default=None,
              help="Pull a single repo instead of the whole list.")
def pull(only: str | None) -> None:
    """Clone+pull every repo under repositories/.

    The directory is the source of truth: anything with a .git in
    repositories/ is included, and repositories.list is rewritten to
    match. If repositories/ is empty (fresh checkout), bootstraps from
    repositories.list instead.
    """
    root = paths.find_monorepo_root()
    repo_root = root / "repositories"
    repo_root.mkdir(exist_ok=True)

    list_file = root / "repositories.list"

    if only:
        names = [only]
    else:
        on_disk = _scan_clones(repo_root)
        listed = (
            [ln.strip() for ln in list_file.read_text().splitlines() if ln.strip()]
            if list_file.is_file() else []
        )
        # Disk wins when it has anything — that way a manual `mint clone`
        # gets picked up and a manual `rm -rf` sticks. Only fall back to
        # the list for fresh checkouts where nothing is cloned yet.
        names = on_disk if on_disk else listed
        if not names:
            raise click.ClickException(
                f"no clones in {repo_root} and no repositories.list at {list_file}. "
                f"Clone something with `mint clone <repo>` (or pass --only <repo>)."
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

    # Resync the list with whatever ended up on disk so it stays a
    # faithful mirror across add/remove. Skip in --only mode (targeted).
    if not only:
        final = _scan_clones(repo_root)
        if final:
            list_file.write_text("\n".join(final) + "\n")

    # After pulling, refresh skill symlinks for any repo we manage that
    # ships its own skill stack (currently just trustim-investigation).
    # Idempotent — safe to run on every pull. Quiet when no relevant
    # repo was pulled.
    relevant = [n for n in names if n in _SKILL_LINK_REPOS]
    for rn in relevant:
        n_links = _refresh_skill_symlinks(root, rn)
        click.echo(f"  ↻ refreshed {n_links} {rn} skill symlink(s) in .claude/skills/")

    if failed:
        raise click.ClickException(f"{len(failed)}/{len(names)} failed: {', '.join(failed)}")
    click.echo(f"OK — {len(names)} repo(s) updated in {repo_root}")


@repo_group.command("refresh-skills")
@click.option("--only", default=None,
              help="Refresh symlinks for a single repo (default: every configured repo).")
def refresh_skills(only: str | None) -> None:
    """Refresh `.claude/skills/<prefix>-<name>` symlinks from each
    configured repo's `skills/` directory. Auto-run by `lab repo pull`;
    this command is for manual touch-ups when symlinks are stale or
    missing.

    Currently refreshes: trustim-investigation (prefix: `investigation-`).
    """
    root = paths.find_monorepo_root()
    if only and only not in _SKILL_LINK_REPOS:
        configured = ", ".join(sorted(_SKILL_LINK_REPOS)) or "(none)"
        raise click.ClickException(
            f"{only!r} isn't a skill-linked repo. Configured: {configured}"
        )
    n = _refresh_skill_symlinks(root, only)
    where = root / ".claude" / "skills"
    click.echo(f"refreshed {n} skill symlink(s) in {where}")
