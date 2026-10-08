"""Reopen configured tasks even when no browser is viewing their workspace."""
import asyncio
import logging
from pathlib import Path

from lab import assistant_tasks, assistant_records, naming, objectives, paths, workspace_identity

log = logging.getLogger(__name__)


def reconcile(roots, assistant_root=None):
    for root in dict.fromkeys(Path(root) for root in roots):
        try:
            folders = list(naming.workspaces_dir(root).iterdir())
        except OSError:
            continue
        for folder in folders:
            if not naming.workspace_metadata_file(folder).is_file():
                continue
            try:
                objectives.refresh_recurring(root, workspace_identity.id_at(folder))
            except (OSError, ValueError):
                log.exception('Could not reconcile tasks in %s', folder)
    if assistant_root and (assistant_root / '.assistant' / 'manifest.json').is_file():
        try:
            rows = list(assistant_records.records(assistant_root))
        except (OSError, ValueError):
            log.exception('Could not read Assistant tasks')
            return
        for row in rows:
            if row.get('task_format') == assistant_tasks.FORMAT and not row.get('parent'):
                # Reuse this tick's materialized snapshot for path resolution;
                # each due transition still rereads its file under the lock.
                if not any(isinstance(task, dict) and isinstance(task.get('recurrence'), dict) for task in row.get('tasks',[]) or []):
                    continue
                try:
                    assistant_tasks.refresh_recurring(assistant_root, row['id'], record_rows=rows)
                except (OSError, ValueError):
                    log.exception('Could not reconcile Assistant document %s', row['id'])


async def run(app):
    while True:
        try:
            roots = [app.state.index_cache.root, *(row['path'] for row in paths.read_vault_registry()['vaults'] if row.get('path'))]
            await asyncio.to_thread(reconcile, roots, paths.assistant_root())
        except Exception:
            log.exception('Task schedule tick failed')
        await asyncio.sleep(30)
