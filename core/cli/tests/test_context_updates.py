import os

import pytest
from click.testing import CliRunner

from lab import agent_context, terminal_context
from lab.cli import main
from lab.commands import context


@pytest.fixture
def session(monorepo, monkeypatch):
    monkeypatch.setenv('TMUX', '/tmp/owned,socket,123,0')
    monkeypatch.setenv('TMUX_PANE', '%42')
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    markers = {}
    def tmux(socket, *args):
        assert socket == '/tmp/owned,socket'
        if args[0] == 'display-message':
            return ('$7' if args[3] == '%42' else '$8') + '\tneurona-owned'
        target = args[args.index('-t') + 1]
        assert args[0] in ('show-options', 'set-option')
        if args[0] == 'set-option':
            assert args[-2] == agent_context.CONTEXT_VERSION_OPTION
            markers[target] = args[-1]
        return markers.get(target, '')
    monkeypatch.setattr(terminal_context, 'tmux', tmux)
    return markers


def test_update_is_silent_until_changed_and_isolated_by_session(session, monkeypatch):
    runner = CliRunner()
    version = runner.invoke(main, ['context', 'version'])
    assert version.exit_code == 0 and version.output.strip().isdecimal()
    assert not session, 'version must not acknowledge context'
    first = runner.invoke(main, ['context', 'update'])
    assert first.exit_code == 0 and 'Lab framework capabilities' in first.output
    assert session == {'$7': version.output.strip()}
    for alias in [['context'], ['agent', 'context'], ['agents', 'context']]:
        unchanged = runner.invoke(main, [*alias, 'update'])
        assert unchanged.exit_code == 0 and unchanged.output == ''
    monkeypatch.setattr(context, 'context_version', lambda: '123')
    changed = runner.invoke(main, ['context', 'update'])
    assert changed.exit_code == 0 and 'Lab context version: 123.' in changed.output
    assert session == {'$7': '123'}
    assert runner.invoke(main, ['context', 'update']).output == ''
    monkeypatch.setenv('TMUX_PANE', '%43')
    assert 'Lab framework capabilities' in runner.invoke(main, ['context', 'update']).output
    assert session == {'$7': '123', '$8': '123'}


@pytest.mark.parametrize('failure', ['read', 'output'])
def test_failed_update_is_not_acknowledged(session, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise OSError('test failure')
    monkeypatch.setattr(context if failure == 'read' else context.click,
                        'current_context' if failure == 'read' else 'echo', fail)
    result = CliRunner().invoke(main, ['context', 'update'])
    assert result.exit_code != 0 and not session


def test_update_outside_tmux_prints_without_saving_or_guessing(monorepo, monkeypatch):
    monkeypatch.delenv('TMUX', raising=False)
    monkeypatch.delenv('TMUX_PANE', raising=False)
    monkeypatch.setattr(terminal_context, 'tmux', lambda *args: pytest.fail('must not guess'))
    for _ in range(2):
        result = CliRunner().invoke(main, ['context', 'update'])
        assert result.exit_code == 0 and 'Lab framework capabilities' in result.output
    for name in ('version', 'update'):
        assert CliRunner().invoke(main, ['context', name, '--path']).exit_code != 0


def test_version_tracks_content_not_install_path_or_mtime(tmp_path, monkeypatch):
    root = tmp_path / 'guides'
    root.mkdir()
    monkeypatch.setattr(agent_context, 'GUIDE_DIR', root)
    monkeypatch.setattr(agent_context, 'guide_path', lambda topic: root / topic)
    for name in [*agent_context.TOPICS, 'instruction-paths.md']:
        (root / name).write_text(name)
    version = agent_context.context_version()
    for path in root.iterdir():
        os.utime(path, (1, 1))
    assert agent_context.context_version() == version
    for name in ('overview', 'user-guide', 'notebooks', 'instruction-paths.md'):
        path = root / name
        original = path.read_text()
        path.write_text(original + '\nNew instructions')
        assert agent_context.context_version() != version
        path.write_text(original)
    assert agent_context.context_version() == version
