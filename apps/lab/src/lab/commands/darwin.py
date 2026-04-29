from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import click

from lab import paths


def _darwin_runner_bin() -> str:
    """Resolve the darwin-runner binary.

    Prefer ``~/.local/bin/darwin-runner`` (what ``make install`` creates).
    Fall back to the in-repo script so ``lab darwin`` still works in a
    fresh clone where ``make install`` hasn't run yet.
    """
    on_path = shutil.which("darwin-runner")
    if on_path:
        return on_path
    root = paths.find_monorepo_root()
    in_repo = root / "apps" / "darwin-runner" / "darwin-runner"
    if in_repo.is_file():
        return str(in_repo)
    raise click.ClickException(
        "darwin-runner not found. Run `make install` at the monorepo root "
        "or point $PATH at apps/darwin-runner/."
    )


def _invoke(args: list[str], *, cwd: Path | None = None) -> int:
    """Run darwin-runner and forward the exit code. Output streams through."""
    cmd = [_darwin_runner_bin(), *args]
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    return r.returncode


@click.group(name="darwin")
def darwin_group() -> None:
    """Run Darwin notebook analyses (wraps darwin-runner).

    All subcommands forward to ``darwin-runner``; outputs go to the
    current project's ``notebooks/`` directory so the rendered notebook
    shows up in the project view and updates live as new cells land.
    """


@darwin_group.command(name="setup")
def darwin_setup() -> None:
    """One-time install of lipy-darwin-local-client (darwin-runner setup)."""
    sys.exit(_invoke(["setup"]))


@darwin_group.command(name="start")
@click.option("--force", is_flag=True, help="Restart even if proxy is already up.")
def darwin_start(force: bool) -> None:
    """Start the proxy and connect to the Darwin pod."""
    args = ["start"] + (["--force"] if force else [])
    sys.exit(_invoke(args))


@darwin_group.command(name="stop")
def darwin_stop() -> None:
    """Disconnect from Darwin and stop the proxy."""
    sys.exit(_invoke(["stop"]))


@darwin_group.command(name="status")
def darwin_status() -> None:
    """Show proxy + stored kernel state for the current project."""
    sys.exit(_invoke(["status"]))


def _resolve_code(code: str | None, file: Path | None) -> str:
    """Return the snippet to run — either ``CODE`` or the contents of ``FILE``."""
    if (code is None) == (file is None):
        raise click.ClickException(
            "pass exactly one of CODE (positional) or --file <path>; "
            "--file is the quote-safe option for multi-line SQL / Python."
        )
    if file is not None:
        try:
            return file.read_text()
        except OSError as exc:
            raise click.ClickException(f"could not read {file}: {exc}") from exc
    return code  # type: ignore[return-value]


def _run_common(code: str, *, local: bool, timeout: int,
                notebook: str | None, label: str | None) -> None:
    args = ["run-local" if local else "run", code]
    if timeout:
        args += ["--timeout", str(timeout)]
    if notebook:
        args += ["--notebook", notebook]
    if label:
        if local:
            raise click.ClickException("--label is only valid with `run` (remote)")
        args += ["--label", label]
    sys.exit(_invoke(args))


@darwin_group.command(name="run")
@click.argument("code", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None,
              help="Read the snippet from a file. Use this whenever the code "
                   "contains inner quotes, backslashes, or spans multiple "
                   "lines — avoids shell/quote collisions.")
@click.option("--timeout", type=int, default=600, show_default=True,
              help="Kernel execution timeout in seconds.")
@click.option("--notebook", default=None,
              help="Append cells to notebooks/<NAME>.ipynb "
                   "(defaults to the project id when omitted).")
@click.option("--label", default=None,
              help="Run in an ephemeral kernel (created and destroyed per run).")
def darwin_run(code: str | None, file_path: Path | None, timeout: int,
               notebook: str | None, label: str | None) -> None:
    """Execute CODE on the Darwin remote kernel.

    Must be run from inside a ``knowledge/projects/<id>/`` directory so
    ``darwin-runner`` can resolve ``project.json`` and pick the notebook
    + kernel state. Prefer ``--file <path>`` over inline quoting when the
    snippet is multi-line or contains nested quotes.
    """
    resolved = _resolve_code(code, file_path)
    _run_common(resolved, local=False, timeout=timeout, notebook=notebook, label=label)


@darwin_group.command(name="run-local")
@click.argument("code", required=False)
@click.option("--file", "file_path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Read the snippet from a file (quote-safe).")
@click.option("--notebook", default=None,
              help="Append cells to notebooks/<NAME>.ipynb "
                   "(defaults to the project id when omitted).")
def darwin_run_local(code: str | None, file_path: Path | None,
                     notebook: str | None) -> None:
    """Execute CODE against a local ipykernel (no Darwin pod)."""
    resolved = _resolve_code(code, file_path)
    _run_common(resolved, local=True, timeout=600, notebook=notebook, label=None)
