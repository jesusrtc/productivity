from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest
from click.testing import CliRunner

from lab import agent_context, agentsync, paths
from lab.cli import main


def snapshot(root):
    return {str(p.relative_to(root)): (os.readlink(p) if p.is_symlink() else p.read_bytes())
            for p in root.rglob('*') if p.is_file() or p.is_symlink()}


def test_context_reads_packaged_topics_without_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv('LAB_ROOT', raising=False)
    for topic in agent_context.TOPICS:
        result = CliRunner().invoke(main, ['context', topic])
        assert result.exit_code == 0, result.output
        assert len(result.output) > 100
    overview = agent_context.read_context()
    assert '<details>' in overview and 'take precedence' in overview
    assert 'lab context notebooks' in overview
    assert not list(tmp_path.iterdir())


def test_sync_is_read_only_and_does_not_impose_agent_files(monorepo, seed_workspace):
    workspace = seed_workspace('independent')
    (workspace / 'AGENTS.md').write_text('Local rules\n')
    (workspace / 'CLAUDE.md').write_text('Different Claude rules\n')
    before = snapshot(monorepo)
    for flags in ([], ['--notebooks-only'], ['--dry-run']):
        result = CliRunner().invoke(main, ['agents', 'sync', *flags])
        assert result.exit_code == 0, result.output
        assert 'user-owned' in result.output
        assert snapshot(monorepo) == before
    agentsync.sync_all(monorepo)
    agentsync.sync_notebook_instructions(monorepo)
    assert snapshot(monorepo) == before


def test_detach_preserves_files_custom_links_and_targets(monorepo, seed_workspace, tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    workspace = seed_workspace('independent')
    agents = workspace / 'AGENTS.md'
    agents.write_text('Workspace rules\n')
    (workspace / 'CLAUDE.md').symlink_to('AGENTS.md')
    skills = monorepo / '.claude/skills'
    skills.mkdir(parents=True)
    (skills / 'custom.md').write_text('Real skills\n')
    (workspace / '.claude').mkdir()
    (workspace / '.claude/skills').symlink_to(skills)
    (workspace / '.claude/settings.local.json').write_text('{"user":"owned"}\n')
    (workspace / '.github').mkdir()
    custom = workspace / 'custom.md'; custom.write_text('Copilot rules\n')
    (workspace / '.github/copilot-instructions.md').symlink_to('../custom.md')
    memory = workspace / '.agents/memory'; memory.mkdir(parents=True)
    (memory / 'MEMORY.md').write_text('Durable knowledge\n')
    home_memory = paths.claude_memory_dir(workspace)
    home_memory.parent.mkdir(parents=True)
    home_memory.symlink_to(memory)
    before = snapshot(monorepo)
    preview = agentsync.detach(monorepo, dry_run=True)
    assert len(preview['links']) == 3
    assert snapshot(monorepo) == before
    assert not paths.global_config_dir().exists()
    report = agentsync.detach(monorepo)
    assert len(report['actions']) == 3 and not report['errors']
    assert agents.read_text() == 'Workspace rules\n'
    assert (memory / 'MEMORY.md').read_text() == 'Durable knowledge\n'
    assert (skills / 'custom.md').read_text() == 'Real skills\n'
    assert (workspace / '.github/copilot-instructions.md').is_symlink()
    assert (workspace / '.claude/settings.local.json').read_text() == '{"user":"owned"}\n'
    assert not home_memory.is_symlink()
    assert json.loads(Path(report['audit']).read_text())['links'] == preview['links']
    assert agentsync.detach(monorepo)['actions'] == []


def test_detach_does_not_follow_directory_links(monorepo, seed_workspace, tmp_path):
    workspace = seed_workspace('independent')
    external = tmp_path / 'external'; external.mkdir()
    link = external / 'copilot-instructions.md'
    link.symlink_to(workspace / 'AGENTS.md')
    (workspace / '.github').symlink_to(external)
    assert agentsync.legacy_links(monorepo) == []
    assert link.is_symlink()


def test_detach_removes_dangling_known_link_but_preserves_real_claude(monorepo, seed_workspace):
    workspace = seed_workspace('independent')
    (workspace / 'CLAUDE.md').write_text('handwritten\n')
    (workspace / '.agents').mkdir()
    (workspace / '.agents/skills').symlink_to('../../../.claude/skills')
    report = agentsync.detach(monorepo)
    assert len(report['actions']) == 1
    assert (workspace / 'CLAUDE.md').read_text() == 'handwritten\n'


def test_doctor_checks_context_not_workspace_files(monorepo, monkeypatch):
    monkeypatch.setattr(agentsync.shutil, 'which', lambda cmd: None)
    before = snapshot(monorepo)
    result = CliRunner().invoke(main, ['agents', 'doctor'])
    assert result.exit_code == 0 and 'Lab context: markdown' in result.output
    result = CliRunner().invoke(main, ['agents', 'doctor', '--require-cli'])
    assert result.exit_code != 0
    assert snapshot(monorepo) == before


@pytest.fixture
def binaries(tmp_path):
    directory = tmp_path / 'bin'; directory.mkdir()
    for name in agent_context.AGENTS:
        file = directory / name
        file.write_text(f'#!{sys.executable}\nimport json,sys\n'
                        'for line in sys.stdin:\n'
                        ' r=json.loads(line)\n'
                        ' result={"config":{"developer_instructions":"EXISTING_PROJECT_RULES"}} if r["method"]=="config/read" else {}\n'
                        ' print(json.dumps({"id":r["id"],"result":result}),flush=True)\n')
        file.chmod(0o755)
    return directory


def test_codex_merges_existing_context_through_rpc(tmp_path, binaries):
    args = ['resume', '--last', '--model', 'custom', '-c', 'developer_instructions="EXPLICIT_RULES"']
    argv, env = agent_context.prepare_launch('codex', args, cwd=tmp_path, env={'PATH': str(binaries)})
    assert json.loads(argv[2].split('=', 1)[1]).endswith('EXISTING_PROJECT_RULES')
    assert 'Lab framework capabilities' in argv[2]
    assert argv[3:] == ['resume', '--last', '--model', 'custom']
    assert env == {'PATH': str(binaries)}


def test_codex_config_args_keep_cwd_and_literal_prompt(tmp_path):
    config, args, cwd = agent_context._codex_config_options([
        '--cd=sub', '--config=developer_instructions="custom"', '-c', 'model="test"',
        '--', '-c', 'this is prompt text'], tmp_path)
    assert config == ['-c', 'developer_instructions="custom"', '-c', 'model="test"']
    assert args == ['--cd=sub', '-c', 'model="test"', '--', '-c', 'this is prompt text']
    assert cwd == tmp_path / 'sub'


def test_codex_rpc_failure_does_not_launch_without_user_instructions(tmp_path, binaries):
    (binaries / 'codex').write_text(f'#!{sys.executable}\n')
    with pytest.raises(agent_context.ContextError):
        agent_context.prepare_launch('codex', [], cwd=tmp_path, env={'PATH': str(binaries)})


def test_claude_appends_context_and_preserves_resume(tmp_path, binaries):
    argv, _ = agent_context.prepare_launch('claude', ['--resume', 'session'], cwd=tmp_path, env={'PATH': str(binaries)})
    assert argv[1:] == ['--append-system-prompt-file', str(agent_context.guide_path()), '--resume', 'session']
    extra = tmp_path / 'extra.md'; extra.write_text('USER_APPEND')
    argv, _ = agent_context.prepare_launch('claude', ['--append-system-prompt-file', str(extra), '--resume', 'session'], cwd=tmp_path, env={'PATH': str(binaries)})
    assert argv[1] == '--append-system-prompt'
    assert 'USER_APPEND' in argv[2] and 'Lab framework capabilities' in argv[2]
    assert argv[-2:] == ['--resume', 'session']


def test_copilot_preserves_existing_environment_and_args(tmp_path, binaries):
    original = {'PATH': str(binaries), 'COPILOT_CUSTOM_INSTRUCTIONS_DIRS': '/custom/one,/custom/two', 'COPILOT_HOME': '/custom/home'}
    argv, env = agent_context.prepare_launch('copilot', ['--resume', 'abc'], cwd=tmp_path, env=original)
    assert argv[1:] == ['--resume', 'abc']
    assert env['COPILOT_HOME'] == '/custom/home'
    assert env['COPILOT_CUSTOM_INSTRUCTIONS_DIRS'] == '/custom/one,/custom/two,' + str(agent_context.GUIDE_DIR)
    assert original['COPILOT_CUSTOM_INSTRUCTIONS_DIRS'] == '/custom/one,/custom/two'


def test_run_execs_agent_with_pinned_vault_without_writing(monorepo, binaries, monkeypatch):
    monkeypatch.setenv('PATH', str(binaries))
    before = snapshot(monorepo)
    calls = []
    monkeypatch.setattr(os, 'execvpe', lambda binary, argv, env: calls.append((binary, argv, env)))
    result = CliRunner().invoke(main, ['agents', 'run', '--vault', str(monorepo), 'copilot', '--', '--session-id', 'abc', '--autopilot'])
    assert result.exit_code == 0, result.output
    assert calls[0][1][1:] == ['--session-id', 'abc', '--autopilot']
    assert calls[0][2]['LAB_VAULT'] == str(monorepo.resolve())
    assert snapshot(monorepo) == before


def test_claude_resume_refreshes_supported_snapshots_but_honors_user_choice(tmp_path, binaries, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(agent_context.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='2.1.268 (Claude Code)'))
    argv, _ = agent_context.prepare_launch('claude', ['--resume', 'session'], cwd=tmp_path, env={'PATH': str(binaries)})
    assert argv[1:3] == ['--system-prompt-snapshot', 'off']
    argv, _ = agent_context.prepare_launch('claude', ['--resume', 'session', '--system-prompt-snapshot', 'on'], cwd=tmp_path, env={'PATH': str(binaries)})
    assert argv.count('--system-prompt-snapshot') == 1
    assert argv[-1] == 'on'
