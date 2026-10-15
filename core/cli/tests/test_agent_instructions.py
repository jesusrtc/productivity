from pathlib import Path

import pytest
from click.testing import CliRunner

from lab import agent_instructions as instructions, objectives
from lab.cli import main


@pytest.mark.parametrize('original', [b'', b'# My rules\n\nKeep everything.\n',
    b'\xef\xbb\xbf# Rules\r\n\r\nDo not reformat.\r\n', '# Investigación\nSin salto'.encode()])
def test_refresh_preserves_user_bytes_and_is_idempotent(tmp_path, original):
    target = tmp_path / 'AGENTS.md'
    target.write_bytes(original)
    target.chmod(0o640)
    report = instructions.refresh(tmp_path)
    assert report['ok'] and report['files'][0]['status'] == 'updated'
    updated = target.read_bytes()
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    assert updated[len(bom):].startswith(instructions.START)
    assert updated.endswith(original[len(bom):])
    assert b'Important: On startup, run `lab context llm`, read its full output' in updated
    assert updated.count(instructions.START) == 1
    assert target.stat().st_mode & 0o777 == 0o640
    before = target.stat()
    assert instructions.refresh(tmp_path)['files'][0]['status'] == 'unchanged'
    assert target.read_bytes() == updated and target.stat().st_mtime_ns == before.st_mtime_ns


def test_new_template_replaces_duplicates_and_moves_section_to_top(tmp_path, monkeypatch):
    old = instructions.render(b'')
    target = tmp_path / 'AGENTS.md'
    target.write_bytes(b'# First user section\n\n' + old + b'## Second\n' + old + b'Last line')
    template = tmp_path / 'latest-template.md'
    template.write_bytes(instructions.TEMPLATE.read_bytes().replace(b'On startup,', b'On every startup,'))
    monkeypatch.setattr(instructions, 'TEMPLATE', template)
    assert instructions.refresh(tmp_path)['ok']
    assert target.read_bytes() == instructions.render(b'# First user section\n\n## Second\nLast line')
    assert instructions.refresh(tmp_path)['files'][0]['status'] == 'unchanged'


@pytest.mark.parametrize('bad', [instructions.START + b'\nUser rules without an end',
    instructions.END + b'\nUser rules', instructions.START + b'\n' + instructions.START + b'\n' + instructions.END])
def test_malformed_markers_leave_entire_file_untouched(tmp_path, bad):
    target = tmp_path / 'AGENTS.md'
    target.write_bytes(bad)
    report = instructions.refresh(tmp_path)
    assert not report['ok'] and report['files'][0]['status'] == 'error'
    assert target.read_bytes() == bad


@pytest.mark.parametrize('kind', ['symlink', 'broken-symlink', 'directory'])
def test_refresh_does_not_replace_links_or_directories(tmp_path, kind):
    target = tmp_path / 'AGENTS.md'
    external = tmp_path / 'user-rules.md'
    if kind == 'directory':
        target.mkdir()
    else:
        if kind == 'symlink':
            external.write_bytes(b'External rules')
        target.symlink_to(external)
    report = instructions.refresh(tmp_path)
    assert not report['ok'] and report['files'][0]['status'] == 'skipped'
    if kind == 'directory':
        assert target.is_dir()
    else:
        assert target.is_symlink()
        assert external.read_bytes() == b'External rules' if external.exists() else kind == 'broken-symlink'


def test_cli_refresh_targets_only_selected_owning_scopes(monorepo, seed_workspace):
    workspace = seed_workspace()
    first = objectives.mutate(monorepo, 'demo', {'type': 'create', 'name': 'First'})['objectives'][0]
    second = objectives.mutate(monorepo, 'demo', {'type': 'create', 'name': 'Second'})['objectives'][1]
    other = seed_workspace('other')
    result = CliRunner().invoke(main, ['agents', 'refresh', '--workspace', 'demo', '--objective', first['id']])
    assert result.exit_code == 0, result.output
    for root in [monorepo, workspace, Path(first['path'])]:
        assert (root / 'AGENTS.md').read_bytes() == instructions.render(b'')
    for root in [other, Path(second['path'])]:
        assert not (root / 'AGENTS.md').exists()


def test_invalid_scope_does_not_write_parent_instructions(monorepo, seed_workspace):
    workspace = seed_workspace()
    for fields in ({'objective_id': 'missing'}, {'workspace_id': '../escape'},
                   {'workspace_id': 'demo', 'objective_id': 'missing'}):
        with pytest.raises(ValueError):
            instructions.refresh(monorepo, **fields)
    assert not (monorepo / 'AGENTS.md').exists()
    assert not (workspace / 'AGENTS.md').exists()


def test_atomic_write_failure_preserves_original(tmp_path, monkeypatch):
    target = tmp_path / 'AGENTS.md'
    target.write_bytes(b'# Keep my rules')
    def fail(*args):
        raise OSError('Write failed')
    monkeypatch.setattr(instructions.os, 'replace', fail)
    report = instructions.refresh(tmp_path)
    assert not report['ok'] and target.read_bytes() == b'# Keep my rules'
    assert not list(tmp_path.glob('.AGENTS.md.*'))
