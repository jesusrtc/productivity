from __future__ import annotations

import click

from lab.commands.agents import agents_group
from lab.commands.app import app_group
from lab.commands.artifact import artifact_group
from lab.commands.config import config_group
from lab.commands.index import index_group
from lab.commands.link import link_group
from lab.commands.ref import ref_group
from lab.commands.repo import repo_group
from lab.commands.pr import pr_group
from lab.commands.project import project_group
from lab.commands.search import search_cmd
from lab.commands.service import open_cmd, start, stop
from lab.commands.task import task_group
from lab.commands.workspace import init_cmd, workspace_group


@click.group()
@click.version_option(package_name="lab")
def main() -> None:
    """CLI for Lab workspaces and the local Lab server."""


main.add_command(project_group)
main.add_command(config_group)
main.add_command(agents_group)
main.add_command(app_group)
main.add_command(task_group)
main.add_command(pr_group)
main.add_command(artifact_group)
main.add_command(link_group)
main.add_command(ref_group)
main.add_command(index_group)
main.add_command(repo_group)
main.add_command(search_cmd)
main.add_command(init_cmd)
main.add_command(workspace_group)
main.add_command(start)
main.add_command(stop)
main.add_command(open_cmd)


if __name__ == "__main__":
    main()
