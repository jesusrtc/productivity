from pathlib import Path

from core import workspace_scan


def test_linked_git_root_cannot_reset_depth_forever(client, seed_workspace):
    root = seed_workspace("cycle")
    (root / ".git").mkdir()
    (root / "docs/note.md").write_text("hello")
    (root / "docs/back").symlink_to(root, target_is_directory=True)
    (root / "linked-docs").symlink_to(root / "docs", target_is_directory=True)
    rows = client.get("/api/workspace-files", params={"path": str(root)}).json()
    names = {row["path"] for row in rows}
    assert "docs/note.md" in names
    assert "linked-docs/note.md" in names
    assert "docs/back" in names
    assert not any("back/" in name for name in names)
    response = client.get("/api/workspace-mtime", params={"path": str(root)})
    assert response.status_code == 200
    assert response.json()["mtime"] is not None


def test_scandir_is_closed_before_yielding_or_descending(tmp_path, monkeypatch):
    (tmp_path / "a/b/c").mkdir(parents=True)
    (tmp_path / "a/b/c/file.py").write_text("pass")
    real_scandir = workspace_scan.os.scandir
    opened = []

    class TrackedScandir:
        def __init__(self, path):
            assert not opened, "parent scandir descriptor is still open"
            self.iterator = real_scandir(path)

        def __enter__(self):
            opened.append(self)
            return self.iterator

        def __exit__(self, *args):
            self.iterator.close()
            opened.remove(self)

    monkeypatch.setattr(workspace_scan.os, "scandir", TrackedScandir)
    entries = []
    for entry in workspace_scan.walk(tmp_path):
        assert not opened
        entries.append(entry.path)
    assert tmp_path / "a/b/c/file.py" in entries


def test_mtime_reports_resource_exhaustion_instead_of_partial_success(client, seed_workspace, monkeypatch):
    import errno
    root = seed_workspace("exhausted")
    real_scandir = workspace_scan.os.scandir

    def fail(path):
        if Path(path) == root / "docs":
            raise OSError(errno.EMFILE, "too many open files")
        return real_scandir(path)

    monkeypatch.setattr(workspace_scan.os, "scandir", fail)
    response = client.get("/api/workspace-mtime", params={"path": str(root)})
    assert response.status_code == 503


def test_files_and_mtime_collect_one_background_snapshot(client, seed_workspace, monkeypatch):
    client = client._inner  # Exercise production caching, not fixture materialization.
    import threading
    from core import workspace_snapshot
    from core.routes import diff

    monkeypatch.setattr(workspace_snapshot, 'REQUEST_WAIT_SECONDS', .01)
    root = seed_workspace('slow')
    (root / 'docs/complete.md').write_text('complete')
    release = threading.Event()
    calls = []
    original = diff._collect_workspace_snapshot

    def slow(path, hidden, progress):
        calls.append(path)
        progress.step(path / 'docs', 'scandir')
        release.wait(2)
        return original(path, hidden, progress)

    monkeypatch.setattr(diff, '_collect_workspace_snapshot', slow)
    try:
        files = client.get('/api/workspace-files', params={'path': str(root)})
        mtime = client.get('/api/workspace-mtime', params={'path': str(root)})
        assert files.status_code == mtime.status_code == 202
        assert files.headers['retry-after'] == '2'
        assert files.json()['scan']['state'] == 'scanning'
        assert mtime.json()['mtime'] is None
        assert calls == [root]
        release.set()
        assert client.app.state.workspace_snapshots._entries[next(iter(client.app.state.workspace_snapshots._entries))].done.wait(1)
        files = client.get('/api/workspace-files', params={'path': str(root), 'refresh': 'false'})
        mtime = client.get('/api/workspace-mtime', params={'path': str(root)})
        assert files.status_code == mtime.status_code == 200
        assert files.headers['x-lab-scan-state'] == 'ready'
        assert 'docs/complete.md' in {row['path'] for row in files.json()}
        assert mtime.json()['mtime'] is not None
        assert mtime.json()['revision']
        assert files.headers['x-lab-files-revision'] == mtime.json()['revision']
        assert calls == [root]
    finally:
        release.set()


def test_cached_notebook_running_indicator_does_not_resolve_paths(client, seed_workspace, monkeypatch):
    from core.routes import nb_exec
    root = seed_workspace('notebook')
    notebook = root / 'docs/note.ipynb'
    notebook.write_text('{}')
    client.get('/api/workspace-files', params={'path': str(root)})
    canonical = str(notebook.resolve())
    monkeypatch.setattr(nb_exec, '_pending_paths', {canonical: 1})
    original = Path.resolve

    def reject_notebook_resolution(path, *args, **kwargs):
        if str(path) == str(notebook):
            raise AssertionError('cached listing performed notebook filesystem I/O')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'resolve', reject_notebook_resolution)
    params = {'path': str(root), 'refresh': 'false'}
    rows = client.get('/api/workspace-files', params=params).json()
    assert next(row for row in rows if row['path'] == 'docs/note.ipynb')['pending'] is True
    monkeypatch.setattr(nb_exec, '_pending_paths', {})
    rows = client.get('/api/workspace-files', params=params).json()
    assert 'pending' not in next(row for row in rows if row['path'] == 'docs/note.ipynb')


def test_revision_detects_deletion_even_when_latest_mtime_stays_the_same(client, seed_workspace):
    import os
    import time
    root = seed_workspace('deletion')
    future = root / 'docs/future.md'
    future.write_text('future')
    ts = time.time() + 10_000
    os.utime(future, (ts, ts))
    removed = root / 'docs/remove.md'
    removed.write_text('remove')
    first = client.get('/api/workspace-mtime', params={'path': str(root)}).json()
    removed.unlink()
    client.get('/api/workspace-files', params={'path': str(root)})
    second = client.get('/api/workspace-mtime', params={'path': str(root)}).json()
    assert first['mtime'] == second['mtime']
    assert first['revision'] != second['revision']
