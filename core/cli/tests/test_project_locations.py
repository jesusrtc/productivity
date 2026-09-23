import json
import subprocess

from click.testing import CliRunner
from lab import settings
from lab.cli import main


def test_cli_shared_layout_custom_destination_and_remove(monorepo, seed_workspace, tmp_path):
    seed_workspace('demo')
    source = tmp_path / 'src'
    repo = source / 'lab'
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                    'commit', '-qm', 'Initial', '--allow-empty'], check=True)
    settings.update_global(monorepo, {'projectsFolder': str(source), 'worktreesFolder': str(source / '.worktrees')})
    runner = CliRunner()
    assert str(repo) in runner.invoke(main, ['repo', 'ls']).output
    result = runner.invoke(main, ['workspace', 'add', 'demo', 'lab', '--branch', 'new-feature-branch'])
    assert result.exit_code == 0, result.output
    tree = source / '.worktrees/lab/new-feature-branch'
    assert (tree / '.git').is_file()
    stored = json.loads((monorepo / 'workspaces/demo/workspace.json').read_text())['worktrees'][0]
    assert stored['dir'] == str(tree) and stored['repo'] == str(repo)
    result = runner.invoke(main, ['workspace', 'remove', 'demo', 'lab'])
    assert result.exit_code == 0, result.output
    assert not tree.exists()
    custom = tmp_path / 'custom worktrees/special'
    result = runner.invoke(main, ['workspace', 'add', 'demo', 'other-name', '--project-path', str(repo),
                                  '--worktree-path', str(custom), '--branch', 'another-feature'])
    assert result.exit_code == 0, result.output
    assert (custom / '.git').is_file()
    # An exact destination is a one-time override, not a new project default.
    assert settings.load(monorepo)['projectLocations'] == []
