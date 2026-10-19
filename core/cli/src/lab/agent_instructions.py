"""Template-managed Lab sections; all other instruction bytes are user-owned."""
from __future__ import annotations

import fcntl
import os
from pathlib import Path
import stat
import tempfile

from lab import objective_store

TEMPLATE = Path(__file__).parent / 'resources/agent-context/managed-section.md'
START = b'<!-- lab:managed-context:start -->'
END = b'<!-- lab:managed-context:end -->'


def render(original: bytes) -> bytes:
    """Move/replace complete marked sections, preserving everything outside them."""
    bom = b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b''
    lines = original[len(bom):].splitlines(keepends=True)
    kept, inside, separator = [], False, False
    for line in lines:
        marker = line.rstrip(b'\r\n')
        if marker == START:
            if inside:
                raise ValueError('Nested Lab managed markers; repair the section before refreshing')
            inside, separator = True, False
        elif marker == END:
            if not inside:
                raise ValueError('Unmatched Lab managed end marker; repair the section before refreshing')
            inside, separator = False, True
        elif not inside:
            # The one empty line after our end marker belongs to the section.
            if not (separator and line in (b'\n', b'\r\n')):
                kept.append(line)
            separator = False
    if inside:
        raise ValueError('Unclosed Lab managed section; repair its end marker before refreshing')
    newline = b'\r\n' if b'\r\n' in original else b'\n'
    block = TEMPLATE.read_bytes().replace(b'\r\n', b'\n').rstrip(b'\n')
    return bom + block.replace(b'\n', newline) + newline * 2 + b''.join(kept)


def _refresh_file(folder: Path) -> dict:
    target = folder / 'AGENTS.md'
    result = {'path': str(target)}
    try:
        before = target.lstat() if target.exists() or target.is_symlink() else None
        if before and not stat.S_ISREG(before.st_mode):
            return {**result, 'status': 'skipped', 'detail': 'AGENTS.md is a symlink or non-regular file; left unchanged'}
        original = target.read_bytes() if before else b''
        updated = render(original)
        if before and updated == original:
            return {**result, 'status': 'unchanged'}
        fd, name = tempfile.mkstemp(prefix='.AGENTS.md.', dir=folder)
        try:
            with os.fdopen(fd, 'wb') as output:
                output.write(updated)
                output.flush()
                os.fchmod(output.fileno(), stat.S_IMODE(before.st_mode) if before else 0o644)
                os.fsync(output.fileno())
            if before:
                current = target.lstat()
                if (current.st_ino, current.st_mtime_ns, current.st_size) != (before.st_ino, before.st_mtime_ns, before.st_size) or target.read_bytes() != original:
                    raise ValueError('AGENTS.md changed during refresh; retry with the latest file')
                os.replace(name, target)
            else:
                # Do not replace a file another process created while we rendered.
                os.link(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        return {**result, 'status': 'updated' if before else 'created'}
    except (OSError, ValueError) as exc:
        return {**result, 'status': 'error', 'detail': str(exc)}


def refresh(root: Path, *, workspace_id: str | None = None,
            objective_id: str | None = None) -> dict:
    """Refresh only the selected vault, workspace and Objective, never checkouts."""
    root = root.resolve()
    if not root.is_dir():
        raise ValueError('Vault not found')
    folders = [('vault', root)]
    if objective_id and not workspace_id:
        raise ValueError('Choose the owning workspace for this Objective')
    if workspace_id:
        from lab.objectives import directory
        workspace = directory(root, workspace_id)
        if not workspace.resolve().is_relative_to(root):
            raise ValueError('Workspace must belong to this vault')
        folders.append(('workspace', workspace))
        if objective_id:
            with objective_store.lock(workspace):
                objective = next((o for o in objective_store.read(workspace)['objectives']
                                  if o['id'] == objective_id), None)
            if objective is None:
                raise ValueError('Objective not found')
            folder = Path(objective['path'])
            if not folder.is_dir() or not folder.resolve().is_relative_to(workspace.resolve()):
                raise ValueError('Objective folder not found in this workspace')
            folders.append(('objective', folder))
    lock = root / '.lab/state/agent-instructions.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            files = [{**_refresh_file(folder), 'scope': scope} for scope, folder in folders]
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
    return {'ok': all(row['status'] in {'created', 'updated', 'unchanged'} for row in files), 'files': files}
