import subprocess

import pytest
from click.testing import CliRunner

from lab import terminal_context, terminal_status
from lab.cli import main


@pytest.mark.parametrize('state,expected', [('working','working'), ('wip','working'),
    ('attention','attention'), ('input','attention'), ('review','attention'), ('finished','finished')])
def test_report_targets_own_pane_and_socket_with_literal_message(monkeypatch, state, expected):
    monkeypatch.setenv('TMUX', '/tmp/own,socket,123,0')
    monkeypatch.setenv('TMUX_PANE', '%42')
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, '$7\tneurona-owned\n' if 'display-message' in argv else '', '')
    monkeypatch.setattr(terminal_context.subprocess, 'run', run)
    message = 'Review | <draft> "quoted"; $(touch nope) #{pane_id}\n¿Listo?'
    result = CliRunner().invoke(main, ['notifications', state, message])
    assert result.exit_code == 0, result.output
    assert calls[0] == ['tmux','-S','/tmp/own,socket','display-message','-p','-t','%42','#{session_id}\t#{session_name}']
    assert calls[1][:7] == ['tmux','-S','/tmp/own,socket','set-option','-t','$7','@lab_status']
    report = terminal_status.decode(calls[1][7])
    assert report['state'] == expected and report['message'] == message
    assert '|' not in calls[1][7] and '\n' not in calls[1][7]
    if expected in ('attention', 'finished'):
        assert calls[2][:7] == ['tmux','-S','/tmp/own,socket','set-option','-t','$7','@lab_notification']
        assert terminal_status.decode(calls[2][7]) == report
    else:
        assert len(calls) == 2, 'working must preserve the last notification'


def test_report_without_tmux_never_guesses_current_session(monkeypatch):
    monkeypatch.delenv('TMUX', raising=False)
    monkeypatch.setattr(terminal_context.subprocess, 'run', lambda *a, **k: pytest.fail('must not guess'))
    result = CliRunner().invoke(main, ['notifications', 'finished'])
    assert result.exit_code != 0 and 'inside the owning Lab tmux terminal' in result.output


@pytest.mark.parametrize('identity', ['$7\tpersonal', 'bad\tneurona-owned'])
def test_report_rejects_unowned_or_invalid_session(monkeypatch, identity):
    monkeypatch.setenv('TMUX', '/tmp/socket,123,0')
    monkeypatch.setenv('TMUX_PANE', '%42')
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    calls = []
    monkeypatch.setattr(terminal_context, 'tmux', lambda *args: calls.append(args) or identity)
    result = CliRunner().invoke(main, ['notifications', 'attention'])
    assert result.exit_code != 0 and len(calls) == 1


def test_invalid_message_and_failed_tmux_do_not_report_success(monkeypatch):
    result = CliRunner().invoke(main, ['notifications','working','x'*501])
    assert result.exit_code != 0 and '500 characters' in result.output
    monkeypatch.setenv('TMUX', '/tmp/socket,123,0')
    monkeypatch.setenv('TMUX_PANE', '%42')
    monkeypatch.setattr(terminal_context.subprocess, 'run', lambda *a, **k:
        subprocess.CompletedProcess([], 1, '', 'session vanished'))
    result = CliRunner().invoke(main, ['notifications', 'finished'])
    assert result.exit_code != 0 and 'session vanished' in result.output


@pytest.mark.parametrize('value', ['', 'not base64', 'e30=', terminal_status.encode({'version':1}), 'a'*8193])
def test_invalid_report_is_unknown(value):
    assert terminal_status.decode(value) is None
