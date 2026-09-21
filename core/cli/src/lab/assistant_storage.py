"""Explicit, reversible migration from tasks/notes to one documents directory."""
import hashlib
import uuid

from lab import assistant_records as records, assistant_documents as documents

LAYOUT = 'unified-documents-v1'


def enabled(root):
    return records.manifest(root).get('storage_layout') == LAYOUT


def folders(root):
    return ('documents', 'projects') if enabled(root) else ('tasks', 'notes', 'projects')


def folder(root, record_type):
    return 'documents' if enabled(root) and record_type in {'task', 'note'} else record_type + 's'


def canonical(root, reference):
    path, separator, tab = str(reference).partition('#tab=')
    target = records.manifest(root).get('path_aliases', {}).get(path, path)
    return target + separator + tab


def origin(root, source, metadata):
    path = documents.physical(source).relative_to(root).as_posix()
    return metadata.get('legacy_path') or records.manifest(root).get('document_origins', {}).get(path, path)


def migrate(root, *, dry_run=True):
    if not records.enabled(root) or not documents.enabled(root):
        raise ValueError('Migrate to schema 2 and embedded subtabs first; read lab migrations assistant-documents')
    from lab import assistant as db
    with records.lock(root):
        for name in folders(root):
            records.safe(root, root/name)
        rows = documents.snapshot(root, force=True)
        if enabled(root):
            return {'changed': False, 'layout': LAYOUT, 'records': len(rows)}
        roots = [row for row in rows if not row.get('parent') and row['type'] in {'task', 'note'}]
        moves = {row['path']: 'documents/' + row['id'] + '.md' for row in roots}
        if len(set(moves.values())) != len(moves):
            raise ValueError('Task and note IDs collide in documents/')
        # An unregistered Markdown file must never silently join the database.
        records.safe(root, root/'documents')
        if (root/'documents').exists() and not (root/'documents').is_dir():
            raise ValueError('documents/ must be a directory')
        if any((root/'documents').glob('*.md')):
            raise ValueError('documents/ already contains Markdown; resolve the collision before migrating')
        for target in moves.values():
            records.safe(root, root/target)
            if (root/target).exists():
                raise ValueError('Migration destination already exists: ' + target)
        oldmanifest = records.manifest(root)
        aliases = {**oldmanifest.get('path_aliases', {}), **moves}
        origins = {**oldmanifest.get('document_origins', {}), **{new:old for old,new in moves.items()}}
        report = {'changed': True, 'layout': LAYOUT, 'documents': len(moves),
                  'subtabs': sum(bool(row.get('parent')) for row in rows), 'moves': moves}
        if dry_run:
            return report
        identifier = 'documents-' + db.now_iso().replace(':','').replace('+','') + '-' + uuid.uuid4().hex[:8]
        backup = records.safe(root, root/'.assistant/backups'/identifier)
        journal = records.safe(root, root/'.assistant/migrations'/(identifier+'.json'))
        originals = {path:(root/path).read_bytes() for path in moves}
        originals['.assistant/manifest.json'] = (root/'.assistant/manifest.json').read_bytes()
        for name in ('AGENTS.md','README.md'):
            if (root/name).is_file():
                originals[name] = (root/name).read_bytes()
        hashes = {path:hashlib.sha256(data).hexdigest() for path,data in originals.items()}
        for path,data in originals.items():
            records.atomic_bytes(backup/path, data)
            if hashlib.sha256((backup/path).read_bytes()).hexdigest() != hashes[path]:
                raise ValueError('Backup verification failed: ' + path)
        def record(state):
            records.write_json(journal, {**report, 'state':state, 'backup':str(backup), 'sha256':hashes})
        record('prepared')
        created = []
        had_documents = (root/'documents').exists()
        try:
            records.write_json(root/'.assistant/manifest.json', {**oldmanifest, 'state':'migrating'})
            for old,new in moves.items():
                records.atomic_bytes(root/new, originals[old])
                created.append(new)
                if (root/new).read_bytes() != originals[old]:
                    raise ValueError('Document verification failed: ' + new)
            for old in moves:
                (root/old).unlink()
            records.write_json(root/'.assistant/manifest.json', {**oldmanifest, 'state':'active',
                'storage_layout':LAYOUT, 'path_aliases':aliases, 'document_origins':origins})
            result = documents.snapshot(root, force=True)
            def content(items):
                return {records.key(row): {k:v for k,v in row.items() if k not in {'path','document_path','mtime'}} for row in items}
            if content(result) != content(rows):
                raise ValueError('Post-migration identity/content verification failed')
            for row in rows:
                if records.resolve(root,row['path'])[1]['id'] != row['id']:
                    raise ValueError('Legacy reference verification failed: ' + row['path'])
            record('complete')
        except Exception:
            for path,data in originals.items():
                records.atomic_bytes(root/path, data)
            for path in created:
                (root/path).unlink(missing_ok=True)
            if not had_documents and (root/'documents').is_dir() and not any((root/'documents').iterdir()):
                (root/'documents').rmdir()
            documents._CACHE.pop(str(root), None)
            (root/'.assistant/index.json').unlink(missing_ok=True)
            record('rolled_back')
            raise
        # Leave any non-Markdown attachments at their original relative paths.
        for name in ('tasks','notes'):
            directory = root/name
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        return {**report, 'backup':str(backup), 'journal':str(journal)}
