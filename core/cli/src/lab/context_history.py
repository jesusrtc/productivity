"""Framework changelog snapshots keyed by the version acknowledged in tmux."""
import difflib
import re

from lab import paths


def snapshot_path(version):
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,20}', version):
        return None
    return paths.global_config_dir() / 'state/agent-context' / (version + '.changelog.md')


def changes(previous, version, current):
    if previous == version:
        return ''
    target = snapshot_path(previous)
    try:
        before = target.read_text(encoding='utf-8') if target else None
    except FileNotFoundError:
        before = None
    if before is None:
        return ('## Lab changelog changes\n\n'
                'No earlier changelog snapshot is available for this terminal. '
                'This read establishes its baseline; use `lab context changelog` for the full history.\n')
    delta = '\n'.join(difflib.unified_diff(before.splitlines(), current.splitlines(),
                    fromfile=f'Lab changelog @ {previous}', tofile=f'Lab changelog @ {version}', lineterm=''))
    return f'## Lab changelog changes\n\n```diff\n{delta.rstrip()}\n```\n' if delta else ''


def record(version, content):
    from lab.assistant_records import atomic_bytes
    target = snapshot_path(version)
    if target is None:
        raise ValueError('Invalid Lab context version')
    data = content.encode('utf-8')
    if not target.is_file() or target.read_bytes() != data:
        atomic_bytes(target, data)
