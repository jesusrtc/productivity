"""META skill discovery stays scoped, complete and read-only."""
import os
from pathlib import Path

import pytest

from core import agent_skills


def flatten(rows):
    entries = {}
    for row in rows:
        entries[row['path']] = row
        entries.update(flatten(row.get('children', [])))
    return entries


@pytest.mark.parametrize('scope', ['vault', 'workspace', 'objective'])
def test_api_lists_existing_skill_folders_and_all_children(client, monorepo, seed_workspace, scope):
    workspace = seed_workspace()
    root = {'vault': monorepo, 'workspace': workspace, 'objective': workspace / 'objectives/build'}[scope]
    root.mkdir(parents=True, exist_ok=True)
    (root / 'AGENTS.md').write_text('Instructions')
    for relative in agent_skills.SKILL_FOLDERS:
        folder = root / relative / 'sample'
        (folder / 'scripts/deep/.hidden/empty').mkdir(parents=True)
        (folder / 'SKILL.md').write_text('Skill')
        (folder / 'scripts/deep/.hidden/run.py').write_text('print(1)')
    before = sorted(str(path.relative_to(root)) for path in root.rglob('*'))
    response = client.get('/api/agents/context/files', params={'path': str(root), 'include_skills': True})
    assert response.status_code == 200, response.text
    data = response.json()
    assert [row['path'] for row in data['files']] == ['AGENTS.md']
    assert [row['path'] for row in data['skills']] == list(agent_skills.SKILL_FOLDERS)
    entries = flatten(data['skills'])
    for relative in agent_skills.SKILL_FOLDERS:
        assert entries[relative + '/sample/scripts/deep/.hidden/empty']['type'] == 'dir'
        assert entries[relative + '/sample/scripts/deep/.hidden/run.py']['type'] == 'file'
    assert sorted(str(path.relative_to(root)) for path in root.rglob('*')) == before
    legacy = client.get('/api/agents/context/files', params={'path': str(root)})
    assert isinstance(legacy.json(), list)


def test_absent_folders_are_omitted_and_discovery_does_not_walk_the_repository(tmp_path, monkeypatch):
    (tmp_path / 'unrelated/large/tree').mkdir(parents=True)
    (tmp_path / '.claude/skills/empty').mkdir(parents=True)
    (tmp_path / '.github').mkdir()
    (tmp_path / '.github/skills').write_text('A file is not a skills folder')
    original = os.scandir
    scanned = []
    def scan(path):
        scanned.append(Path(path))
        assert Path(path).is_relative_to(tmp_path / '.claude/skills')
        return original(path)
    monkeypatch.setattr(os, 'scandir', scan)
    rows = agent_skills.collect(tmp_path)
    assert [row['path'] for row in rows] == ['.claude/skills']
    assert rows[0]['children'][0]['name'] == 'empty'
    assert len(scanned) == 2


def test_skill_symlinks_keep_source_paths_and_stop_ancestor_cycles(tmp_path):
    root = tmp_path / 'scope'
    (root / '.agents').mkdir(parents=True)
    shared = tmp_path / 'shared'
    (shared / 'example/references').mkdir(parents=True)
    (shared / 'example/SKILL.md').write_text('Skill')
    (shared / 'example/references/loop').symlink_to(shared, target_is_directory=True)
    (shared / 'broken').symlink_to(tmp_path / 'missing')
    (root / '.agents/skills').symlink_to(shared, target_is_directory=True)
    rows = agent_skills.collect(root)
    assert rows[0]['is_symlink'] and rows[0]['symlink_target'] == str(shared)
    entries = flatten(rows)
    assert '.agents/skills/example/SKILL.md' in entries
    assert entries['.agents/skills/example/references/loop']['cycle']
    assert entries['.agents/skills/example/references/loop']['children'] == []
    assert entries['.agents/skills/broken']['broken']


def test_skill_discovery_requires_access_to_its_scope(client, tmp_path):
    outside = tmp_path / 'private'
    (outside / '.agents/skills').mkdir(parents=True)
    response = client.get('/api/agents/context/files', params={'path': str(outside), 'include_skills': True})
    assert response.status_code == 403
