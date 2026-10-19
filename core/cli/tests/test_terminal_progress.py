import json

from click.testing import CliRunner
import pytest

from lab import terminal_progress as progress, terminal_status
from lab.cli import main


def report(state='working', at=100, identity='a'):
    return {'version': 1, 'state': state, 'id': identity * 32, 'message': 'Validating migration',
            'updated_at': at, 'revision': int(at * 1000)}


class Terminal:
    def __init__(self, current=None):
        self.options = {terminal_status.OPTION: terminal_status.encode(current or report())}

    def option(self, name):
        return self.options.get(name, '')

    def set_option(self, name, value):
        assert name == progress.HOOK_OPTION, 'hooks must never invent reports or alter user notifications'
        self.options[name] = value

    def compare_set_option(self, name, value, expected):
        if any(self.option(key) != token for key, token in expected.items()):
            return False
        self.set_option(name, value)
        return True

    def hook(self, event, now, **extra):
        return progress.handle_hook(event, {'sessionId': 'copilot-session', **extra}, self, now=now)


def test_checkpoint_is_due_after_twenty_minutes_and_activity_does_not_refresh_report():
    terminal = Terminal(report(at=99))
    terminal.hook('prompt', 100)
    terminal.options[terminal_status.OPTION] = original = terminal_status.encode(report(at=101, identity='b'))
    assert terminal.hook('post-tool', 1300) == {}
    reminder = terminal.hook('post-tool', 1301)
    assert 'lab notifications working' in reminder['additionalContext']
    assert terminal.option(terminal_status.OPTION) == original
    assert terminal.hook('post-tool', 1302) == {}, 'no reminder spam on each tool'
    hook = progress.decode(terminal.option(progress.HOOK_OPTION))
    assert hook['last_activity_at'] == 1300
    assert progress.next_alert(report(at=101, identity='b'), hook, {}, now=1900) is None
    alert = progress.next_alert(report(at=101, identity='b'), hook, {}, now=1901)
    assert alert['kind'] == 'stale', 'recent tool activity does not hide stale progress'
    terminal.options[terminal_status.OPTION] = terminal_status.encode(report(at=1902, identity='c'))
    assert terminal.hook('post-tool', 1903) == {}
    assert not progress.view(report(at=1902, identity='c'), hook, alert)['alert']['active']


@pytest.mark.parametrize('state', ['attention', 'finished'])
def test_explicit_final_state_suppresses_alert_and_stop_block(state):
    terminal = Terminal()
    terminal.hook('prompt', 101)
    final = report(state, 102, 'b')
    terminal.options[terminal_status.OPTION] = terminal_status.encode(final)
    assert terminal.hook('post-tool', 10000) == {}
    assert terminal.hook('stop', 10001) == {}
    assert progress.next_alert(final, progress.decode(terminal.option(progress.HOOK_OPTION)), {}, now=10002) is None


def test_previous_finish_cannot_satisfy_a_new_prompt_and_stop_is_bounded():
    terminal = Terminal(report('finished'))
    terminal.hook('prompt', 101)
    assert terminal.hook('stop', 102)['decision'] == 'block'
    assert terminal.hook('stop', 103, stop_hook_active=True) == {}
    assert terminal.hook('stop', 104) == {}, 'self-limit even if the provider omits its guard'
    hook = progress.decode(terminal.option(progress.HOOK_OPTION))
    alert = progress.next_alert(report('finished'), hook, {}, now=105)
    assert alert['kind'] == 'stopped' and alert['source'].startswith('turn:')
    assert progress.next_alert(report('finished'), hook, alert, now=100000) is None
    assert progress.view(report('finished'), hook, alert, now=105)['alert']['active']
    assert not progress.view(report('finished', 106, 'b'), hook, alert, now=107)['alert']['active']


def test_session_end_and_subagents_do_not_report_completion():
    terminal = Terminal()
    terminal.hook('prompt', 101)
    before = dict(terminal.options)
    assert terminal.hook('post-tool', 5000, agentId='child') == {}
    assert terminal.hook('stop', 5000, agent_id='child') == {}
    assert terminal.options == before
    assert terminal.hook('end', 5001) == {}
    hook = progress.decode(terminal.option(progress.HOOK_OPTION))
    alert = progress.next_alert(report(), hook, {}, now=5002)
    assert alert['kind'] == 'exited'
    assert terminal_status.decode(terminal.option(terminal_status.OPTION))['state'] == 'working'


def test_opening_copilot_alone_does_not_start_a_reporting_window():
    terminal = Terminal(report('finished'))
    assert terminal.hook('start', 5000) == {}
    hook = progress.decode(terminal.option(progress.HOOK_OPTION))
    assert progress.work(report('finished'), hook) is None
    assert terminal.hook('post-tool', 5100) == {}
    assert progress.work(report('finished'), progress.decode(terminal.option(progress.HOOK_OPTION)))['since'] == 5100


def test_cli_hook_json_and_reporting_failure_are_fail_open(monkeypatch):
    from lab import terminal_context
    monkeypatch.setenv('TMUX', '/tmp/socket,1,0')
    monkeypatch.setenv('TMUX_PANE', '%1')
    terminal = Terminal()
    monkeypatch.setattr(terminal_context, 'current', lambda: terminal)
    runner = CliRunner()
    result = runner.invoke(main, ['progress', 'hook', 'prompt'], input=json.dumps({'sessionId': 'one'}))
    assert result.exit_code == 0 and json.loads(result.stdout) == {}
    result = runner.invoke(main, ['progress', 'hook', 'stop'], input=json.dumps({'sessionId': 'one'}))
    assert result.exit_code == 0 and json.loads(result.stdout)['decision'] == 'block'
    def denied():
        raise terminal_context.TerminalContextError('permission denied')
    monkeypatch.setattr(terminal_context, 'current', denied)
    result = runner.invoke(main, ['progress', 'hook', 'stop'], input='{"sessionId":"one"}')
    assert result.exit_code == 0 and json.loads(result.stdout) == {}
    assert 'permission denied' in result.stderr


def test_invalid_or_disabled_progress_never_raises_an_active_alert():
    assert progress.decode('broken') == {} and progress.decode('e30=') == {}
    alert = progress.next_alert(report(), {}, {}, now=1900)
    assert not progress.view(report(), {}, alert, enabled=False)['alert']['active']
    assert 'alert' not in progress.view(report(), {}, {'version': 1, 'source': 'a' * 32})
    assert progress.work(None, {'started_at': float('nan'), 'turn_id': 'bad'}) is None
    assert progress.next_alert(report(), {}, {'version': 1, 'source': 'a' * 32}, now=1900)


def test_late_events_and_concurrent_new_reports_cannot_reopen_finished_work():
    terminal = Terminal()
    terminal.hook('prompt', 101)
    before = dict(terminal.options)
    assert progress.handle_hook('end', {'sessionId': 'old-session'}, terminal, now=102) == {}
    assert terminal.options == before
    compare = terminal.compare_set_option
    def raced(name, value, expected):
        terminal.options[terminal_status.OPTION] = terminal_status.encode(report('finished', 2000, 'b'))
        terminal.compare_set_option = compare
        return False
    terminal.compare_set_option = raced
    assert terminal.hook('post-tool', 2001) == {}, 'retry sees the new finish and suppresses the stale reminder'
    assert terminal_status.decode(terminal.option(terminal_status.OPTION))['state'] == 'finished'
