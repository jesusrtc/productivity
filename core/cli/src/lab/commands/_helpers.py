"""Shared helpers used by multiple command modules.

Centralizes the ``--project``/PWD resolution pattern so subcommand files
(``pr.py``, ``artifact.py``, ``search.py``, ``project.py``, ``task.py``) share
one canonical implementation instead of copy-pasting.
"""
from __future__ import annotations

import click

from lab import paths
from lab.model import ModelError, validate_id


def require_valid_id(project_id: str) -> str:
    """Validate a project id and surface ModelError as ClickException."""
    try:
        return validate_id(project_id)
    except ModelError as exc:
        raise click.ClickException(str(exc)) from exc


def resolve_project_id(explicit: str | None) -> str:
    """Return the project id the user is operating on.

    If ``explicit`` is given, validate and return it. Otherwise walk up from
    PWD looking for a project folder. Raises ClickException if neither works.
    """
    if explicit:
        return require_valid_id(explicit)
    root = paths.find_monorepo_root()
    try:
        return paths.find_project_id_from_pwd(root)
    except paths.ProjectNotFound as exc:
        raise click.ClickException(str(exc)) from exc
