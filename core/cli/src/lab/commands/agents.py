from __future__ import annotations

import os
from pathlib import Path

import click

from lab import agent_context, agentsync, paths, terminal_context, terminal_status
from lab.commands.context import context_cmd


@click.group(name='agents')
def agents_group() -> None:
    """Launch agents with Lab context; keep workspace instructions independent."""


@agents_group.command('run', context_settings={'ignore_unknown_options': True})
@click.option('--vault', type=click.Path(path_type=Path, exists=True, file_okay=False),
              help='Pin Lab commands in this agent process to an owning vault.')
@click.option('--workspace', 'workspace_id', help='Owning workspace ID, including launches in linked worktrees.')
@click.option('--objective', 'objective_id', help='Owning Objective ID within that workspace.')
@click.option('--prompt-file', type=click.Path(path_type=Path, exists=True, dir_okay=False),
              help='Read an initial task from a UTF-8 file; keep the provider interactive.')
@click.argument('agent', type=click.Choice(agent_context.AGENTS))
@click.argument('args', nargs=-1, type=click.UNPROCESSED)
def run(vault: Path | None, workspace_id: str | None, objective_id: str | None,
        prompt_file: Path | None, agent: str, args: tuple[str, ...]) -> None:
    """Launch AGENT with framework context and its own repository instructions.

    Example: lab agents run codex -- resume --last
    """
    env = dict(os.environ)
    if vault:
        if str(vault.resolve()) != env.get('LAB_VAULT'):
            env.pop('LAB_CONTEXT_WORKSPACE', None)
            env.pop('LAB_CONTEXT_OBJECTIVE', None)
        env['LAB_VAULT'] = str(vault.resolve())
    if workspace_id:
        env['LAB_CONTEXT_WORKSPACE'] = workspace_id
        env.pop('LAB_CONTEXT_OBJECTIVE', None)
    if objective_id:
        env['LAB_CONTEXT_OBJECTIVE'] = objective_id
    try:
        if prompt_file:
            prompt = prompt_file.read_text(encoding='utf-8')
            if not prompt.strip() or '\x00' in prompt or len(prompt.encode('utf-8')) > 120000:
                raise agent_context.ContextError('Initial task must contain 1–120000 UTF-8 bytes without NUL bytes')
            args = (*args, *(['--interactive', prompt] if agent == 'copilot' else ['--', prompt]))
        argv, env = agent_context.prepare_launch(agent, list(args), env=env)
        terminal, previous_llm = None, ''
        try:
            # Keep the last acknowledged version for changelog diffs. The
            # bootstrap requires llm, which always prints full instructions.
            terminal = terminal_context.current(env)
            previous_llm = terminal.option(terminal_status.LLM_OPTION)
            terminal.set_option(terminal_status.LLM_OPTION, agent)
        except terminal_context.TerminalContextError:
            # Non-tmux launches remain supported. A failed marker is retried by
            # the agent's first context update rather than blocking the launch.
            terminal = None
        try:
            os.execvpe(argv[0], argv, env)
        except OSError:
            if terminal:
                try:
                    terminal.set_option(terminal_status.LLM_OPTION, previous_llm)
                except terminal_context.TerminalContextError:
                    pass
            raise
    except (agent_context.ContextError, OSError, UnicodeError) as exc:
        raise click.ClickException(str(exc)) from exc


@agents_group.command('sync')
@click.option('--dry-run', is_flag=True)
@click.option('--notebooks-only', is_flag=True, hidden=True)
def sync(dry_run: bool, notebooks_only: bool) -> None:
    """Compatibility check; no longer writes or links agent files."""
    click.echo(agentsync.NOTICE)
    click.echo('Use `lab context` to read the guide or `lab agents detach --dry-run` to inspect legacy links.')


@agents_group.command('refresh')
@click.option('--vault', type=click.Path(path_type=Path, exists=True, file_okay=False),
              help='Owning vault path; defaults to the selected vault.')
@click.option('--workspace', 'workspace_id', help='Also refresh this workspace.')
@click.option('--objective', 'objective_id', help='Also refresh this Objective in the selected workspace.')
def refresh(vault: Path | None, workspace_id: str | None, objective_id: str | None) -> None:
    """Create/update the top Lab managed section in the selected AGENTS.md files.

    Preserves all instructions outside the marked section. No recursive scan.
    """
    from lab import agent_instructions
    try:
        report = agent_instructions.refresh(vault or paths.find_vault_root(),
                                            workspace_id=workspace_id, objective_id=objective_id)
    except (OSError, ValueError, paths.MonorepoNotFound) as exc:
        raise click.ClickException(str(exc)) from exc
    for row in report['files']:
        click.echo(f"{row['status']}: {row['path']}" + (f" — {row['detail']}" if row.get('detail') else ''))
    if not report['ok']:
        raise click.ClickException('Some instruction files were not refreshed; see details above.')


@agents_group.command('detach')
@click.option('--root', type=click.Path(path_type=Path, exists=True, file_okay=False),
              help='Inspect or detach links in this vault/framework root.')
@click.option('--all-vaults', is_flag=True, help='Include registered vaults and the framework checkout.')
@click.option('--dry-run', is_flag=True, help='List recognized legacy links without changing files.')
def detach(root: Path | None, all_vaults: bool, dry_run: bool) -> None:
    """Remove recognized legacy Lab agent symlinks, preserving real files.

    An audit with original link targets is saved outside the workspaces.
    Custom link targets and every real instruction, skill and memory file stay.
    """
    if root and all_vaults:
        raise click.UsageError('Choose --root or --all-vaults')
    if all_vaults:
        roots = [Path(row['path']) for row in paths.read_vault_registry()['vaults']]
        try:
            roots.append(paths.find_framework_root())
        except paths.MonorepoNotFound:
            pass
    else:
        try:
            roots = [root or paths.find_vault_root()]
        except paths.MonorepoNotFound as exc:
            raise click.ClickException(str(exc)) from exc
    errors = []
    for current in dict.fromkeys(p.resolve() for p in roots):
        if not current.is_dir():
            errors.append(f'{current}: unavailable; not migrated')
            continue
        report = agentsync.detach(current, dry_run=dry_run)
        click.echo(str(current))
        for action in report['actions']:
            click.echo(('  would ' if dry_run else '  ') + action)
        if not report['actions']:
            click.echo('  no recognized legacy links')
        if report.get('audit'):
            click.echo('  audit: ' + report['audit'])
        errors.extend(report['errors'])
    if errors:
        raise click.ClickException('\n'.join(errors))


@agents_group.command('doctor')
@click.option('--require-cli', is_flag=True,
              help='Fail if claude, codex, or copilot is not launchable locally.')
def doctor(require_cli: bool) -> None:
    """Check packaged context and agent CLIs without requiring workspace files."""
    try:
        root = paths.find_vault_root()
    except paths.MonorepoNotFound:
        root = None
    report = agentsync.doctor_all(root, include_cli=True)
    for row in report['checks'] + report['cli']:
        click.echo(f"{'ok' if row['ok'] else 'FAIL':4} {row['label']} ({row['detail']})")
    click.echo(report['notice'])
    if report['legacy_links']:
        click.echo(f"{len(report['legacy_links'])} legacy links found; inspect with `lab agents detach --dry-run`.")
    if not report['ok'] or (require_cli and not report['cli_ok']):
        raise click.ClickException('agent setup has problems')


# Both lab agents context and the singular lab agent alias read the same guide.
agents_group.add_command(context_cmd)

# Imported only with this command group, preserving the CLI's lazy startup.
from lab.commands.subagents import spawn, children, read_child
agents_group.add_command(spawn)
agents_group.add_command(children)
agents_group.add_command(read_child)
from lab.commands.agent_work import work, files
agents_group.add_command(work)
agents_group.add_command(files)
