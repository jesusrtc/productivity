"""Session discovery scales with workspace files, not sessions × files."""
import json
import uuid
from collections import Counter

from lab import paths, workspace_identity as identity


def test_batch_owners_preserve_index_precedence_recovery_and_fresh_edits(
    monorepo, seed_workspace, monkeypatch,
):
    folder = seed_workspace('stable-id')
    renamed = folder.with_name('renamed-folder')
    folder.rename(renamed)
    indexed, recovered, home = (str(uuid.uuid4()) for _ in range(3))
    names = ['neurona-' + value.replace('-', '') for value in (indexed, recovered, home)]
    metadata = renamed / 'workspace.json'
    data = json.loads(metadata.read_text())
    data['sessions'] = [
        {'name': 'fallback', 'session_id': indexed},
        {'name': 'recovered', 'session_id': recovered},
    ]
    metadata.write_text(json.dumps(data))
    state = paths.vault_state_dir(monorepo)
    state.mkdir(parents=True, exist_ok=True)
    index = state / 'session-index.json'
    index.write_text(json.dumps({'entry': {
        'session_id': indexed, 'workspace_id': 'index-wins', 'logical_name': 'indexed',
    }}))
    framework = monorepo.parent / 'framework'
    framework.mkdir()
    monkeypatch.setenv('LAB_FRAMEWORK_ROOT', str(framework))
    home_metadata = identity._session_metadata(monorepo, '__self__')
    home_metadata.parent.mkdir(parents=True, exist_ok=True)
    home_metadata.write_text(json.dumps({'sessions': [{'name': 'home', 'session_id': home}]}))
    foreign = ['neurona-' + uuid.uuid4().hex for _ in range(100)]
    wanted = names + foreign + ['lab-demo-bash', 'neurona-not-a-uuid']
    reads = Counter()
    original = identity._read

    def read(path):
        reads[path] += 1
        return original(path)

    monkeypatch.setattr(identity, '_read', read)
    assert identity.session_owners(monorepo, wanted) == {
        names[0]: ('index-wins', 'indexed'),
        names[1]: ('stable-id', 'recovered'),
        names[2]: ('__self__', 'home'),
    }
    assert max(reads.values()) == 1
    assert reads[metadata] == 1
    assert reads[index] == 1
    # A subsequent call observes disk changes; no negative cross-request cache.
    index.unlink()
    data['sessions'][1]['name'] = 'edited'
    metadata.write_text(json.dumps(data))
    assert identity.session_owners(monorepo, names) == {
        names[0]: ('stable-id', 'fallback'),
        names[1]: ('stable-id', 'edited'),
        names[2]: ('__self__', 'home'),
    }
    assert identity.session_owner(monorepo, names[1]) == ('stable-id', 'edited')


def test_known_or_legacy_names_do_not_walk_workspace_files(monorepo, monkeypatch):
    def unexpected(*_args):
        raise AssertionError('Legacy/empty names do not require UUID discovery')

    monkeypatch.setattr(identity, '_read', unexpected)
    assert identity.session_owners(monorepo, []) == {}
    assert identity.session_owner(monorepo, 'lab-demo-bash') is None


def test_registry_checks_foreign_uuids_once_and_preserves_live_owned_rows(
    monorepo, monkeypatch,
):
    from core.routes import term

    owned = 'neurona-' + uuid.uuid4().hex
    foreign = ['neurona-' + uuid.uuid4().hex for _ in range(40)]
    metadata = {owned: {'workspace_id': 'demo', 'logical_name': 'one',
                        'session_id': str(uuid.uuid4()), 'tmux_socket': 'default'}}
    monkeypatch.setattr(term, '_load_meta', lambda root: metadata.copy())
    original = identity.session_owners
    calls = []

    def owners(root, names):
        calls.append(set(names))
        return original(root, names)

    def unexpected(*_args):
        raise AssertionError('Foreign UUIDs cannot be parsed as legacy names')

    monkeypatch.setattr(identity, 'session_owners', owners)
    monkeypatch.setattr(term, '_parse_tmux_name', unexpected)
    monkeypatch.setattr(term, '_save_meta', unexpected)
    live = [{'name': name, 'tmux_socket': 'default'} for name in [owned, *foreign]]
    assert term._sync_meta(monorepo, live) == metadata
    assert calls == [set(foreign)]
