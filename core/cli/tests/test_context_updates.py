import os

import pytest
from click.testing import CliRunner

from lab import agent_context, context_history, terminal_context, terminal_status
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
            assert args[-2] in (agent_context.CONTEXT_VERSION_OPTION, terminal_status.LLM_OPTION)
            markers[target, args[-2]] = args[-1]
        return markers.get((target, args[-1]), '')
    monkeypatch.setattr(terminal_context, 'tmux', tmux)
    return markers


def test_update_is_silent_until_changed_and_isolated_by_session(session, monkeypatch):
    runner = CliRunner()
    version = runner.invoke(main, ['context', 'version'])
    assert version.exit_code == 0 and version.output.strip().isdecimal()
    assert not session, 'version must not acknowledge context'
    first = runner.invoke(main, ['context', 'update'])
    assert first.exit_code == 0 and 'Lab framework capabilities' in first.output
    assert session == {('$7', agent_context.CONTEXT_VERSION_OPTION): version.output.strip()}
    assert agent_context.read_context('user-guide').strip() in first.output
    assert agent_context.read_context('changelog').strip() not in first.output
    assert 'establishes its baseline' in first.output
    for alias in [['context'], ['agent', 'context'], ['agents', 'context']]:
        unchanged = runner.invoke(main, [*alias, 'update'])
        assert unchanged.exit_code == 0 and unchanged.output == ''
    monkeypatch.setattr(context, 'context_version', lambda: '123')
    changed = runner.invoke(main, ['context', 'update'])
    assert changed.exit_code == 0 and 'Lab context version: 123.' in changed.output
    assert session == {('$7', agent_context.CONTEXT_VERSION_OPTION): '123'}
    assert runner.invoke(main, ['context', 'update']).output == ''
    monkeypatch.setenv('TMUX_PANE', '%43')
    assert 'Lab framework capabilities' in runner.invoke(main, ['context', 'update']).output
    assert session == {(name, agent_context.CONTEXT_VERSION_OPTION): '123' for name in ('$7', '$8')}


@pytest.mark.parametrize('failure', ['read', 'output'])
def test_failed_update_is_not_acknowledged(session, monkeypatch, failure):
    def fail(*args, **kwargs):
        raise OSError('test failure')
    monkeypatch.setattr(context if failure == 'read' else context.click,
                        'llm_context' if failure == 'read' else 'echo', fail)
    result = CliRunner().invoke(main, ['context', 'update'])
    assert result.exit_code != 0 and not session


def test_update_outside_tmux_prints_without_saving_or_guessing(monorepo, monkeypatch):
    monkeypatch.delenv('TMUX', raising=False)
    monkeypatch.delenv('TMUX_PANE', raising=False)
    monkeypatch.setattr(terminal_context, 'tmux', lambda *args: pytest.fail('must not guess'))
    for topic in ('llm', 'update', 'llm', 'update'):
        result = CliRunner().invoke(main, ['context', topic])
        assert result.exit_code == 0 and 'Lab framework capabilities' in result.output
        assert '# Lab user guide' in result.output and '# Lab changelog' in result.output
    for name in ('llm', 'version', 'update'):
        assert CliRunner().invoke(main, ['context', name, '--path']).exit_code != 0


def test_version_tracks_content_not_install_path_or_mtime(tmp_path, monkeypatch):
    root = tmp_path / 'guides'
    root.mkdir()
    monkeypatch.setattr(agent_context, 'GUIDE_DIR', root)
    monkeypatch.setattr(agent_context, 'guide_path', lambda topic: root / topic)
    (root / 'bootstrap').mkdir()
    for name in [*agent_context.TOPICS, 'instruction-paths.md', 'bootstrap/AGENTS.md', 'managed-section.md']:
        (root / name).write_text(name)
    version = agent_context.context_version()
    for path in root.rglob('*'):
        os.utime(path, (1, 1))
    assert agent_context.context_version() == version
    for name in ('overview', 'user-guide', 'notebooks', 'instruction-paths.md', 'bootstrap/AGENTS.md', 'managed-section.md'):
        path = root / name
        original = path.read_text()
        path.write_text(original + '\nNew instructions')
        assert agent_context.context_version() != version
        path.write_text(original)
    assert agent_context.context_version() == version


@pytest.mark.parametrize('marker', ['', '0', '1', 'codex'])
def test_llm_always_loads_full_context_and_marks_own_terminal(session, marker):
    runner = CliRunner()
    version = agent_context.context_version()
    session['$7', agent_context.CONTEXT_VERSION_OPTION] = version
    session['$7', terminal_status.LLM_OPTION] = marker
    for alias in (['context'], ['agent', 'context'], ['agents', 'context']):
        result = runner.invoke(main, [*alias, 'llm'])
        assert result.exit_code == 0, result.output
        assert agent_context.read_context('user-guide').strip() in result.output
        assert agent_context.read_context('changelog').strip() not in result.output
        assert f'Source: `{agent_context.guide_path("user-guide")}`' in result.output
        assert 'lab context update' in result.output and 'lab notifications attention' in result.output
        assert 'You are in Lab terminal `neurona-owned`, pane `%42`' in result.output
        assert session == {('$7', terminal_status.LLM_OPTION): 'codex' if marker == 'codex' else '1',
                           ('$7', agent_context.CONTEXT_VERSION_OPTION): version}
        assert runner.invoke(main, [*alias, 'update']).output == ''


@pytest.mark.parametrize('failure', ['read', 'output', 'flush'])
def test_failed_llm_output_does_not_acknowledge_context(session, monkeypatch, failure):
    session['$7', agent_context.CONTEXT_VERSION_OPTION] = 'previous'
    def fail(*args, **kwargs):
        raise OSError('test failure')
    if failure == 'read':
        monkeypatch.setattr(context, 'llm_context', fail)
    elif failure == 'output':
        monkeypatch.setattr(context.click, 'echo', fail)
    else:
        from types import SimpleNamespace
        monkeypatch.setattr(context.click, 'get_text_stream', lambda *args:SimpleNamespace(flush=fail))
    result = CliRunner().invoke(main, ['context', 'llm'])
    assert result.exit_code != 0
    assert session['$7', agent_context.CONTEXT_VERSION_OPTION] == 'previous'
    assert session['$7', terminal_status.LLM_OPTION] == '1'


def test_plain_overview_does_not_mark_llm_or_consume_update(session):
    result = CliRunner().invoke(main, ['context'])
    assert result.exit_code == 0 and not session


def test_llm_does_not_mark_a_non_lab_tmux_session(session, monkeypatch):
    calls=[]
    monkeypatch.setattr(terminal_context, 'tmux', lambda *args:calls.append(args) or '$7\tpersonal')
    result = CliRunner().invoke(main, ['context', 'llm'])
    assert result.exit_code != 0 and 'does not belong to a Lab terminal' in result.output
    assert len(calls)==1 and not session


def test_changelog_delta_uses_each_terminals_acknowledged_version(session, monkeypatch):
    current_log = '# Changes\n\nNew rule\n' + '\n'.join(f'Historic entry {i}' for i in range(20)) + '\n'
    old_log = current_log.replace('New rule', 'Previous rule')
    context_history.record('111', old_log)
    session['$7', agent_context.CONTEXT_VERSION_OPTION] = '111'
    session['$8', agent_context.CONTEXT_VERSION_OPTION] = '111'
    original_read = agent_context.read_context
    monkeypatch.setattr(context, 'read_context', lambda topic: current_log if topic == 'changelog' else original_read(topic))
    monkeypatch.setattr(context, 'context_version', lambda: '222')
    result = CliRunner().invoke(main, ['context', 'llm'])
    assert result.exit_code == 0, result.output
    assert '-Previous rule' in result.output and '+New rule' in result.output
    assert 'Historic entry 19' not in result.output
    assert session['$7', agent_context.CONTEXT_VERSION_OPTION] == '222'
    assert session['$8', agent_context.CONTEXT_VERSION_OPTION] == '111'
    assert context_history.snapshot_path('222').read_text() == current_log
    again = CliRunner().invoke(main, ['context', 'llm'])
    assert '# Lab user guide' in again.output and '```diff' not in again.output
    assert CliRunner().invoke(main, ['context', 'update']).output == ''
    monkeypatch.setenv('TMUX_PANE', '%43')
    assert '+New rule' in CliRunner().invoke(main, ['context', 'update']).output
    monkeypatch.setattr(context, 'context_version', lambda: '333')
    result = CliRunner().invoke(main, ['context', 'update'])
    assert result.exit_code == 0 and '```diff' not in result.output
    assert session['$8', agent_context.CONTEXT_VERSION_OPTION] == '333'


def test_failed_snapshot_cannot_acknowledge_context(session, monkeypatch):
    session['$7', agent_context.CONTEXT_VERSION_OPTION] = '111'
    def fail(*args):
        raise OSError('Snapshot storage unavailable')
    monkeypatch.setattr(context_history, 'record', fail)
    result = CliRunner().invoke(main, ['context', 'update'])
    assert result.exit_code != 0 and session['$7', agent_context.CONTEXT_VERSION_OPTION] == '111'


def test_missing_baseline_never_invents_a_diff(session):
    session['$7', agent_context.CONTEXT_VERSION_OPTION] = '123'
    result = CliRunner().invoke(main, ['context', 'llm'])
    assert result.exit_code == 0 and 'No earlier changelog snapshot' in result.output
    assert '```diff' not in result.output


def test_changelog_diff_keeps_changed_last_lines_separate(monorepo):
    context_history.record('111', 'Old last line')
    assert '-Old last line\n+New last line\n' in context_history.changes('111', '222', 'New last line')
