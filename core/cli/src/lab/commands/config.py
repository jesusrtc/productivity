from __future__ import annotations

import click

from lab import paths, settings


@click.group(name="config")
def config_group() -> None:
    """Global lab/agent settings (default agent, model, theme)."""


@config_group.command("show")
def show() -> None:
    """Print every setting and its effective value."""
    root = paths.find_monorepo_root()
    cfg = settings.load(root)
    for key in settings.DEFAULTS:
        click.echo(f"{key} = {cfg.get(key)!r}")


@config_group.command("get")
@click.argument("key")
def get(key: str) -> None:
    """Print one setting's value."""
    if key not in settings.DEFAULTS:
        raise click.ClickException(
            f"unknown setting {key!r} (allowed: {', '.join(settings.DEFAULTS)})"
        )
    root = paths.find_monorepo_root()
    value = settings.load(root).get(key)
    click.echo("" if value is None else value)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def set_cmd(key: str, value: str) -> None:
    """Set a setting (validated): defaultAgent | model | theme."""
    root = paths.find_monorepo_root()
    try:
        cfg = settings.set_value(root, key, value)
    except settings.SettingsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{key} = {cfg.get(key)!r}")
