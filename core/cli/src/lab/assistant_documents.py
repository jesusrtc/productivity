"""One Markdown document per task/note, with stable embedded subtab IDs.

The index is a disposable metadata/search cache. Markdown is authoritative.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import re
import uuid

from lab import assistant_records as records

FORMAT = 'embedded-subtabs-v1'
MARKER = re.compile(r'\r?\n<!-- lab:subtab ([A-Za-z0-9_-]+) -->\r?\n(.*?)\r?\n<!-- /lab:subtab \1 -->\r?\n', re.S)
_CACHE = {}


def enabled(root):
    return bool(root) and records.manifest(root).get('document_format') == FORMAT


def physical(source):
    return Path(str(source).split('#tab=', 1)[0])


def unpack(data):
    metadata, body = records.split_document(data)
    tabs = metadata.get('tabs', [])
    if not isinstance(tabs, list) or any(not isinstance(tab,dict) or not isinstance(tab.get('id'),str) or tab.get('type') not in {'task','note'} or tab.get('schema') != 2 for tab in tabs):
        raise ValueError('tabs must contain schema-2 task/note metadata with stable IDs')
    matches = list(MARKER.finditer(body))
    if len(re.findall(r'^<!-- lab:subtab ',body,re.M)) != len(matches):
        raise ValueError('Malformed subtab body markers')
    main = body[:matches[0].start()] if matches else body
    sections = {match[1]: match[2] for match in matches}
    if len(sections) != len(matches) or {tab['id'] for tab in tabs} != set(sections) or len(tabs) != len(sections):
        raise ValueError('Every subtab needs one unique metadata entry and matching body markers')
    if matches and (matches[-1].end() != len(body) or any(a.end() != b.start() for a,b in zip(matches, matches[1:]))):
        raise ValueError('Keep subtab content inside its body markers')
    return {k:v for k,v in metadata.items() if k != 'tabs'}, main, [(tab, sections[tab['id']]) for tab in tabs]


def pack(metadata, body, tabs):
    content = body
    for tab, text in tabs:
        if re.search(r'^<!-- /?lab:subtab ', text, re.M):
            raise ValueError('Subtab body markers are reserved; do not put them in content')
        content += f"\n<!-- lab:subtab {tab['id']} -->\n{text}\n<!-- /lab:subtab {tab['id']} -->\n"
    return records.encode_document({**metadata, **({'tabs':[tab for tab,_ in tabs]} if tabs else {})}, content)


def read(source):
    target = physical(source)
    metadata, body, tabs = unpack(target.read_bytes())
    if '#tab=' in str(source):
        identifier = str(source).split('#tab=', 1)[1]
        matches = [(tab, text) for tab, text in tabs if tab['id'] == identifier]
        if len(matches) != 1:
            raise ValueError('Subtab not found')
        tab, text = matches[0]
        return {**tab,'workspace':metadata.get('workspace'),'project':metadata.get('project')}, text
    return metadata, body


def write(source, metadata, body):
    target = physical(source)
    if target.exists():
        owner, main, tabs = unpack(target.read_bytes())
    else:
        owner, main, tabs = metadata, body, []
    if '#tab=' in str(source):
        identifier = str(source).split('#tab=',1)[1]
        if identifier not in {tab['id'] for tab,_ in tabs}:
            raise ValueError('Subtab not found')
        metadata = {k:v for k,v in metadata.items() if k not in {'project','workspace'}}
        tabs = [(metadata, body) if tab['id'] == identifier else (tab,text) for tab,text in tabs]
        owner['updated'] = metadata['updated']
    else:
        owner, main = metadata, body
    records.atomic_bytes(target, pack(owner, main, tabs))


def _fingerprint(root):
    from lab import assistant_storage as storage
    files = sorted(path for folder in storage.folders(root) for path in (root/folder).glob('*.md'))
    # Every record still checks its components and resolves its current target.
    # Reuse only this scan's root boundary, not a source's validation or stat.
    resolved_root = root.resolve()
    signature = []
    for source in [*files, root/'.assistant/workspaces.json', root/'.assistant/manifest.json']:
        records.safe(root, source, resolved_root=resolved_root)
        if source.exists():
            stat = source.stat()
            signature.append((source.relative_to(root).as_posix(), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
    return files, signature


def summary(body):
    lines = [line.strip() for line in body.splitlines() if line.strip() and not line.startswith(('#','<!--','```'))]
    return re.sub(r'\s+', ' ', lines[0] if lines else '')[:200]


def snapshot(root, *, force=False):
    from lab import assistant_storage as storage
    files, signature = _fingerprint(root)
    cache = _CACHE.get(str(root))
    index_path = root/'.assistant/index.json'
    index_signature = (index_path.stat().st_mtime_ns, index_path.stat().st_size) if index_path.is_file() else None
    if not force and cache and cache[0] == signature and cache[2] == index_signature:
        return deepcopy(cache[1])
    rows = []
    for source in files:
        metadata, body, tabs = unpack(source.read_bytes())
        path = source.relative_to(root).as_posix()
        if metadata.get('type') not in {'task','note','project'} or metadata.get('id') != source.stem or storage.folder(root, str(metadata.get('type'))) != source.parent.name or metadata.get('schema') != 2:
            raise ValueError('Invalid document identity: ' + path)
        if metadata.get('parent'):
            raise ValueError('Top-level documents cannot have a parent; embed them as subtabs')
        owner = records.key(metadata)
        identities = {owner, *(records.key(tab) for tab,_ in tabs)}
        for tab, text in [(metadata,body), *tabs]:
            if tab is not metadata and records.parent_key(tab) not in identities:
                raise ValueError('A subtab parent must be in the same Markdown document')
            rows.append({**tab, **({field:metadata.get(field) for field in ('project','workspace','task_format')} if tab is not metadata else {}), 'path':path if tab is metadata else path+'#tab='+tab['id'],
                         'document_path':path, 'embedded':tab is not metadata,
                         'body':text, 'mtime':source.stat().st_mtime})
    records.validate_graph(rows, {row['id'] for row in records.workspaces(root)})
    progress = records.progress_map(rows)
    entries = [{k:v for k,v in row.items() if k not in {'body','legacy_metadata','mtime'}} |
               {'description':row.get('tldr') or summary(row['body']), 'progress':progress[records.key(row)]}
               for row in rows]
    index = {'schema':1, 'document_format':FORMAT, 'fingerprint':signature, 'records':entries}
    encoded = (json.dumps(index,ensure_ascii=False,indent=2) + '\n').encode()
    if not index_path.is_file() or index_path.read_bytes() != encoded:
        records.atomic_bytes(index_path,encoded)
    _CACHE[str(root)] = (signature, rows, (index_path.stat().st_mtime_ns,index_path.stat().st_size))
    return deepcopy(rows)


def create(root, record_type, title, identifier, body, fields):
    from lab import assistant as db
    with records.lock(root):
        rows = snapshot(root)
        if any(row['id'] == identifier for row in rows):
            raise ValueError('Record ID already exists')
        parent = fields.get('parent')
        now = db.now_iso()
        metadata = dict(schema=2, type=record_type, id=identifier, title=title, created=now, updated=now)
        if record_type in {'task','note'}:
            metadata.update(project=None,workspace=None,parent=None)
        if record_type == 'task' or fields.get('track_task'):
            metadata.update(status='not_started',priority='P2')
        if record_type in {'task','note'}:
            metadata.update(track_task=record_type == 'task' or bool(fields.get('status')), keep_in_documents=record_type == 'note')
            if parent:
                metadata.pop('keep_in_documents', None)
        if record_type == 'note':
            metadata['note_type'] = 'subtab' if parent else 'plain'
        metadata.update(fields)
        if metadata.get('status') in {'inbox','ready'}:
            metadata['status'] = 'not_started'
        for field in fields:
            if field not in {'id','schema','type'} and not (record_type == 'project' and field == 'status'):
                records.validate_value(root, metadata, field, metadata[field])
        from lab import assistant_tasks as tasks
        owned_tasks = tasks.enabled(root) and record_type in {'task','note'}
        initial_task = None
        if owned_tasks:
            if metadata.get('track_task') or record_type == 'task':
                initial_task = {key:value for key,value in metadata.items() if key in tasks.FIELDS}
                initial_task.update(id=identifier, title=title, priority=metadata.get('priority','P2'),
                                    status=tasks.LEGACY_STATUS.get(metadata.get('status'),metadata.get('status') or 'not_started'),
                                    tab_id=identifier,parent_id=None,created=now,updated=now)
                initial_task['done'] = initial_task['status'] in {'done','skipped'}
            metadata['track_task'] = False
            if not parent:
                metadata['task_format'] = tasks.FORMAT
                metadata['tasks'] = [initial_task] if initial_task else []
            for field in tasks.FIELDS - {'title','tldr','attributes'}:
                metadata.pop(field,None)
        if parent:
            parent_row = next((row for row in rows if records.key(row) == records.parent_key(metadata)), None)
            if not parent_row:
                raise ValueError('Parent not found')
            target = root/parent_row['document_path']
            owner, main, tabs = unpack(target.read_bytes())
            metadata.setdefault('position', max((tab.get('position',0) for tab,_ in tabs), default=-1)+1)
            for field in ('project','workspace'):
                metadata.pop(field,None)
            source = Path(str(target)+'#tab='+identifier)
            candidate = {**metadata,'path':source.relative_to(root).as_posix(),'body':body}
            records.validate_graph([*rows,candidate], {row['id'] for row in records.workspaces(root)})
            owner['updated'] = now
            if initial_task:
                owner.setdefault('tasks',[]).append(initial_task)
            records.atomic_bytes(target, pack(owner,main,[*tabs,(metadata,body)]))
        else:
            from lab import assistant_storage as storage
            source = records.safe(root,root/storage.folder(root,record_type)/(identifier+'.md'))
            records.validate_graph([*rows,{**metadata,'path':source.relative_to(root).as_posix(),'body':body}],
                                   {row['id'] for row in records.workspaces(root)})
            records.atomic_bytes(source,pack(metadata,body,[]))
        snapshot(root,force=True)
        return source


def migrate(root, *, dry_run=True):
    """Convert a v2 document graph with a verified backup and rollback on failure."""
    if enabled(root):
        return {'changed':False, 'format':FORMAT, 'records':len(snapshot(root))}
    if not records.enabled(root):
        raise ValueError('Migrate to Assistant records v2 first')
    from lab import assistant as db
    with records.lock(root):
        rows = list(records.records(root))
        records.validate_graph(rows,{row['id'] for row in records.workspaces(root)})
        roots = [row for row in rows if not row.get('parent')]
        report = {'changed':True,'format':FORMAT,'documents':len(roots), 'subtabs':len(rows)-len(roots)}
        outputs = {}
        for row in roots:
            meta = {k:v for k,v in row.items() if k not in {'path','body','mtime'}}
            tabs = []
            for child in records.descendants(rows,row):
                tab = {k:v for k,v in child.items() if k not in {'path','body','mtime'}}
                tab['aliases'] = list(dict.fromkeys([*(tab.get('aliases') or []),child['path']]))
                tab.setdefault('legacy_path', child['path'])
                legacy_links = {field:tab.pop(field) for field in ('project','workspace') if field in tab}
                if any(value != meta.get(field) for field,value in legacy_links.items()):
                    tab['legacy_metadata'] = {**tab.get('legacy_metadata',{}),'subtab_previous_links':legacy_links}
                tab.setdefault('status', 'not_started')
                tab.setdefault('priority', 'P2')
                tabs.append((tab,child['body']))
            outputs[row['path']] = pack(meta,row['body'],tabs)
            restored, main, embedded = unpack(outputs[row['path']])
            if main != row['body'] or [(m['id'],b) for m,b in embedded] != [(m['id'],b) for m,b in tabs]:
                raise ValueError('Document body verification failed')
        if dry_run:
            return report
        identifier = db.now_iso().replace(':','').replace('+','') + '-' + uuid.uuid4().hex[:8]
        backup = root/'.assistant/backups'/('embedded-'+identifier)
        backup.mkdir(parents=True)
        originals = {row['path']:(root/row['path']).read_bytes() for row in rows}
        for name in ('AGENTS.md','README.md'):
            if (root/name).is_file():
                originals[name] = (root/name).read_bytes()
        originals['.assistant/manifest.json'] = (root/'.assistant/manifest.json').read_bytes()
        hashes = {}
        for path, data in originals.items():
            records.atomic_bytes(backup/path,data)
            hashes[path] = hashlib.sha256(data).hexdigest()
            if hashlib.sha256((backup/path).read_bytes()).hexdigest() != hashes[path]:
                raise ValueError('Backup verification failed')
        journal = root/'.assistant/migrations'/('embedded-'+identifier+'.json')
        records.write_json(journal, {**report,'state':'prepared','backup':str(backup),'sha256':hashes})
        oldmanifest = records.manifest(root)
        try:
            records.write_json(root/'.assistant/manifest.json',{**oldmanifest,'state':'migrating'})
            for path,data in outputs.items():
                records.atomic_bytes(root/path,data)
            for row in rows:
                if row['path'] not in outputs:
                    (root/row['path']).unlink()
            records.write_json(root/'.assistant/manifest.json',{**oldmanifest,'state':'active','document_format':FORMAT})
            result = snapshot(root,force=True)
            if {(r['id'],r['body']) for r in result} != {(r['id'],r['body']) for r in rows}:
                raise ValueError('Post-migration body verification failed')
            templates = Path(__file__).parent/'resources/assistant/embedded'
            for name in ('AGENTS.md','README.md'):
                if not (root/name).exists():
                    records.atomic_bytes(root/name,(templates/name).read_bytes())
            records.write_json(journal,{**report,'state':'complete','backup':str(backup),'sha256':hashes})
        except Exception:
            for path,data in originals.items():
                records.atomic_bytes(root/path,data)
            for name in ('AGENTS.md','README.md'):
                if name not in originals:
                    (root/name).unlink(missing_ok=True)
            _CACHE.pop(str(root),None)
            (root/'.assistant/index.json').unlink(missing_ok=True)
            records.write_json(journal,{**report,'state':'rolled_back','backup':str(backup),'sha256':hashes})
            raise
        return {**report,'backup':str(backup),'journal':str(journal)}
