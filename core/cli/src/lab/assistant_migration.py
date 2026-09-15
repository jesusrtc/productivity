"""Explicit, backed-up migration from workspace-owned documents to schema 2."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import uuid

from lab import assistant_records as records, naming


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plan(root):
    root = root.resolve()
    base = naming.workspaces_dir(root)
    if not base.is_dir():
        raise ValueError('No legacy Assistant workspace folder found')
    for folder in ('tasks', 'notes', 'projects'):
        target = root / folder
        if target.exists() and target != base:
            raise ValueError(f'Destination already exists: {folder}')
    files, documents, refs, assets = {}, [], [], {}
    mapping_paths = set()
    for folder in sorted(base.iterdir()):
        source = naming.workspace_document_file(folder)
        if not folder.is_dir() or not source.is_file():
            continue
        records.safe(root, source)
        meta, body = records.split_document(source.read_bytes())
        original = dict(meta)
        if 'project_path' in meta:
            meta = { {'workspace':'vault', 'workspace_path':'vault_path', 'project_path':'workspace_path'}.get(k,k):v for k,v in meta.items() }
        if meta.get('id', folder.name) != folder.name:
            raise ValueError('Workspace ID does not match its folder: ' + folder.name)
        refs.append({**meta, 'id': folder.name, 'name': meta.get('name') or folder.name,
                     'body': body, 'legacy_metadata': original,
                     'path': '.assistant/workspaces.json', 'aliases': [source.relative_to(root).as_posix()]})
        mapping_paths.add(source)
    known_workspaces = {ref['id'] for ref in refs}
    for source in sorted(base.rglob('*')):
        records.safe(root, source)
        if not source.is_file():
            continue
        old = source.relative_to(root).as_posix()
        data = source.read_bytes()
        files[old] = digest(data)
        if source in mapping_paths:
            continue
        parts = source.relative_to(base).parts
        record_kind = None
        if len(parts) == 3 and source.suffix == '.md':
            record_kind = {'tasks':'task','subtasks':'subtask','meetings':'meeting','meeting-series':'series'}.get(parts[1])
        elif len(parts) == 5 and parts[1] == 'meetings' and source.suffix == '.md':
            record_kind = {'questions':'question','documents':'document'}.get(parts[3])
        if record_kind is None:
            target = ('.assistant/assets/' + parts[2] + '/raw.txt') if len(parts) == 4 and parts[1] == 'meetings' and parts[3] == 'raw.txt' else '.assistant/assets/legacy/' + old
            if target in assets.values():
                raise ValueError('Duplicate asset destination')
            assets[old] = target
            continue
        meta, body = records.split_document(data)
        if meta.get('id') != source.stem or parts[0] not in known_workspaces:
            raise ValueError('Missing identity or workspace mapping: ' + old)
        workspace = meta.get('project') if 'project' in meta else meta.get('workspace', parts[0])
        if workspace != parts[0]:
            raise ValueError('Record workspace does not match its folder: ' + old)
        parent = None
        if record_kind == 'subtask':
            parent = {'type':'task', 'id':meta.get('parent')}
        if record_kind in {'question','document'}:
            if meta.get('meeting') != parts[2]:
                raise ValueError('Content parent does not match its folder: ' + old)
            parent = {'type':'note', 'id':parts[2]}
        record_type = 'task' if record_kind in {'task','subtask'} else 'note'
        # Preserve every original field, including nested unknown values, separately.
        converted = {**meta, 'schema':2, 'type':record_type, 'workspace':workspace,
                     'project':None, 'parent':parent, 'position':len(documents),
                     'aliases':[old], 'legacy_path':old, 'legacy_metadata':meta}
        converted.pop('parent_workspace', None)
        converted.pop('parent_project', None)
        if record_type == 'note':
            converted['note_type'] = record_kind
        target = record_type + 's/' + source.name
        documents.append({'metadata':converted, 'body':body, 'path':target, 'source':old,
                          'body_sha256':digest(body.encode('utf-8'))})
    rows = [doc['metadata'] | {'path':doc['path'], 'body':doc['body']} for doc in documents]
    records.validate_graph(rows, known_workspaces)
    return {'base':base.name, 'files':files, 'documents':documents, 'workspaces':refs,
            'asset_aliases':assets, 'counts':dict(Counter(row['type'] for row in rows))}


def verify_migration(root, report):
    result = records.verify(root)
    for doc in report['documents']:
        source, metadata, body = records.resolve(root, doc['source'])
        if source.relative_to(root).as_posix() != doc['path'] or digest(body.encode()) != doc['body_sha256']:
            raise ValueError('Migrated body or alias mismatch: ' + doc['source'])
    for old, new in report['asset_aliases'].items():
        if digest((root / new).read_bytes()) != report['files'][old]:
            raise ValueError('Migrated asset mismatch: ' + old)
    return result


def migrate(root, *, dry_run=True, checkpoint=None):
    root = root.resolve()
    if records.enabled(root):
        return {**records.verify(root), 'already_migrated':True}
    with records.lock(root):
        report = plan(root)
        summary = {'schema':2, 'counts':report['counts'], 'workspaces':len(report['workspaces']),
                   'projects':0, 'files':len(report['files']), 'dry_run':dry_run}
        if dry_run:
            return summary
        run = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
        journal = root / '.assistant/migrations' / run
        stage = journal / 'stage'
        backup = root / '.assistant/backups' / run
        backup.mkdir(parents=True)
        for folder in ('tasks','notes','projects'):
            (stage / folder).mkdir(parents=True)
        for doc in report['documents']:
            records.write_document(stage / doc['path'], doc['metadata'], doc['body'])
        records.write_json(stage / '.assistant/workspaces.json', {'schema':2, 'workspaces':report['workspaces']})
        for old, new in report['asset_aliases'].items():
            records.atomic_bytes(stage / new, (root / old).read_bytes())
        records.write_json(stage / '.assistant/manifest.json', {'schema':2, 'state':'active', 'asset_aliases':report['asset_aliases']})
        verify_migration(stage, report)
        # Full source backup includes unmapped files. A second hash pass detects edits during staging.
        shutil.copytree(root / report['base'], backup / report['base'])
        for filename in ('AGENTS.md','README.md'):
            if (root / filename).is_file():
                shutil.copy2(root / filename, backup / filename)
        for old, sha in report['files'].items():
            if digest((backup / old).read_bytes()) != sha or digest((root / old).read_bytes()) != sha:
                raise ValueError('Source changed during staging; live data was not modified: ' + old)
        actual_files = {p.relative_to(root).as_posix() for p in (root / report['base']).rglob('*') if p.is_file()}
        if actual_files != set(report['files']):
            raise ValueError('Source file set changed during staging')
        records.write_json(journal / 'journal.json', {**report, 'state':'prepared', 'backup':str(backup)})
        old_manifest = records.manifest(root)
        promoted = []
        docs_written = []
        archived = journal / 'original'
        try:
            records.write_json(root / '.assistant/manifest.json', {'schema':1, 'state':'migrating', 'run':run})
            (root / report['base']).rename(archived)
            if checkpoint:
                checkpoint('archived')
            for folder in ('tasks','notes','projects'):
                (stage / folder).rename(root / folder)
                promoted.append(root / folder)
            for name in ('workspaces.json','assets'):
                candidate = stage / '.assistant' / name
                if candidate.exists():
                    target = root / '.assistant' / name
                    if target.exists():
                        raise ValueError('Migration destination already exists: ' + str(target))
                    candidate.rename(target)
                    promoted.append(target)
            records.write_json(root / '.assistant/manifest.json', {'schema':2,'state':'active','migration':run,
                               'asset_aliases':report['asset_aliases']})
            result = verify_migration(root, report)
            from importlib.resources import files
            templates = files('lab').joinpath('resources/assistant')
            for name in ('AGENTS.md','README.md'):
                docs_written.append(name)
                records.atomic_bytes(root / name, templates.joinpath(name).read_bytes())
            records.write_json(journal / 'journal.json', {**report, 'state':'complete','backup':str(backup),'verification':result})
            # Keep original tree as an additional recovery copy; no source data is deleted.
            return {**summary, **result, 'backup':str(backup), 'journal':str(journal / 'journal.json')}
        except BaseException:
            for name in docs_written:
                original = backup / name
                if original.is_file():
                    records.atomic_bytes(root / name, original.read_bytes())
                else:
                    (root / name).unlink(missing_ok=True)
            for target in reversed(promoted):
                destination = stage / target.relative_to(root)
                destination.parent.mkdir(parents=True, exist_ok=True)
                target.rename(destination)
            if archived.exists():
                archived.rename(root / report['base'])
            if old_manifest:
                records.write_json(root / '.assistant/manifest.json', old_manifest)
            else:
                (root / '.assistant/manifest.json').unlink(missing_ok=True)
            records.write_json(journal / 'journal.json', {**report,'state':'rolled_back','backup':str(backup)})
            raise
