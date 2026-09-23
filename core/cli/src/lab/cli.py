from __future__ import annotations

from importlib import import_module

import click

# Agent launches run in a fresh process. Loading unrelated notebook, Assistant
# and other commands adds startup work before the agent can produce output.
# Help and completion still resolve the same command objects through Click.
_COMMANDS = {
    'workspace': ('workspace', 'workspace_group'),
    'assistant': ('assistant', 'assistant_group'),
    'config': ('config', 'config_group'),
    'agents': ('agents', 'agents_group'),
    'agent': ('agents', 'agents_group'),
    'migrations': ('migrations', 'migrations_cmd'),
    'context': ('context', 'context_cmd'),
    'app': ('app', 'app_group'),
    'task': ('task', 'task_group'),
    'terminal': ('terminal', 'terminal_group'),
    'pr': ('pr', 'pr_group'),
    'artifact': ('artifact', 'artifact_group'),
    'link': ('link', 'link_group'),
    'notebook': ('notebook', 'notebook_group'),
    'ref': ('ref', 'ref_group'),
    'index': ('index', 'index_group'),
    'repo': ('repo', 'repo_group'),
    'search': ('search', 'search_cmd'),
    'init': ('vault', 'init_cmd'),
    'vault': ('vault', 'vault_group'),
    'start': ('service', 'start'),
    'stop': ('service', 'stop'),
    'open': ('service', 'open_cmd'),
}


class _LazyGroup(click.Group):
    def list_commands(self, ctx):
        return sorted(set(_COMMANDS) | set(super().list_commands(ctx)))

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is None and cmd_name in _COMMANDS:
            module, attribute = _COMMANDS[cmd_name]
            command = getattr(import_module('lab.commands.' + module), attribute)
            self.add_command(command, name=cmd_name)
        return command


@click.group(cls=_LazyGroup)
@click.version_option(package_name="lab")
def main() -> None:
    """CLI for Lab vaults and the local Lab server."""


if __name__ == "__main__":
    main()
