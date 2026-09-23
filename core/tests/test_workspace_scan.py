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
