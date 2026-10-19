"""Resolve only the calling Lab pane, never the tmux client's current selection."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
import shlex
import subprocess


class TerminalContextError(RuntimeError):
    pass


def tmux(socket: str, *args: str) -> str:
    try:
        result = subprocess.run(['tmux', '-S', socket, *args], capture_output=True,
                                text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TerminalContextError(f'Cannot reach this terminal’s tmux session: {exc}') from exc
    if result.returncode:
        raise TerminalContextError((result.stderr or 'tmux command failed').strip())
    return result.stdout.strip()


@dataclass(frozen=True)
class TerminalContext:
    socket: str
    pane: str
    session_id: str
    name: str

    def option(self, name: str) -> str:
        return tmux(self.socket, 'show-options', '-qv', '-t', self.session_id, name)

    def set_option(self, name: str, value: str) -> None:
        tmux(self.socket, 'set-option', '-t', self.session_id, name, value)

    def compare_set_option(self, name: str, value: str, expected: dict[str, str]) -> bool:
        """Atomically preserve a newer report or lifecycle event during hooks."""
        if (not re.fullmatch(r'@lab_[a-z_]+', name)
                or not re.fullmatch(r'[A-Za-z0-9+/=]*', value)
                or any(not re.fullmatch(r'@lab_[a-z_]+', key)
                       or not re.fullmatch(r'[A-Za-z0-9+/=]*', token) for key, token in expected.items())):
            raise TerminalContextError('Invalid progress option token')
        condition = '1'
        for key, token in expected.items():
            condition = '#{&&:' + condition + ',#{==:#{' + key + '},' + token + '}}'
        command = 'set-option -t ' + shlex.quote(self.session_id) + ' ' + name + ' ' + value
        output = tmux(self.socket, 'if-shell', '-F', '-t', self.session_id + ':', condition,
                      command, 'display-message -p lab-progress-skipped')
        return 'lab-progress-skipped' not in output


def current(env: dict[str, str] | None = None) -> TerminalContext:
    env = os.environ if env is None else env
    address = env.get('TMUX', '').rsplit(',', 2)
    pane = env.get('TMUX_PANE', '')
    if len(address) != 3 or not address[0] or not re.fullmatch(r'%\d+', pane):
        raise TerminalContextError('Run this command inside the owning Lab tmux terminal (TMUX and TMUX_PANE are required).')
    identity = tmux(address[0], 'display-message', '-p', '-t', pane,
                    '#{session_id}\t#{session_name}').split('\t', 1)
    prefix = env.get('LAB_TMUX_PREFIX')
    if (len(identity) != 2 or not re.fullmatch(r'\$\d+', identity[0])
            or not identity[1].startswith((prefix,) if prefix else ('neurona-', 'lab-'))):
        raise TerminalContextError('The current pane does not belong to a Lab terminal.')
    return TerminalContext(address[0], pane, identity[0], identity[1])
