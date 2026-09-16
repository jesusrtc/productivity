"""Schema 2 presentation and link resolution for Assistant routes."""
from pathlib import Path
import hashlib
import json
from urllib.parse import urlparse, unquote, urlencode

from fastapi import HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from lab import assistant_records as records, assistant_documents as documents


def kind(row):
    if row['type'] == 'task':
        return 'task'
    return {'meeting':'meeting','series':'series','question':'note','document':'note'}.get(row.get('note_type'), 'note')


def tab_revision(row):
    # A physical file's mtime and root updated timestamp also change when a
    # sibling/child is edited. Hash only this tab's own content and metadata.
    ignored = {'mtime', 'updated', 'path', 'document_path', 'embedded', 'legacy_metadata', 'aliases', 'legacy_path'}
    if row.get('embedded'):
        ignored.update({'workspace', 'project'})
    content = {key:value for key,value in row.items() if key not in ignored}
    return hashlib.sha256(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def detail(root, reference, collection=None):
    try:
        source, metadata, body = records.resolve(root, reference, collection)
        rows = list(records.records(root))
        by_key = {records.key(row):row for row in rows}
        progress = records.progress_map(rows)
        current = by_key[records.key(metadata)]
        ancestor = current
        seen = set()
        while records.parent_key(ancestor):
            if records.key(ancestor) in seen:
                raise ValueError('Document parent cycle')
            seen.add(records.key(ancestor))
            ancestor = by_key[records.parent_key(ancestor)]
        def node(row):
            children = sorted([r for r in rows if records.parent_key(r) == records.key(row)],
                              key=lambda r:(r.get('position',0),r['id']))
            return {k:v for k,v in row.items() if k not in {'body','legacy_metadata'}} | {
                'kind':kind(row), 'tab_revision':tab_revision(row), 'description':row.get('tldr') or documents.summary(row.get('body','')),
                'progress':progress[records.key(row)], 'children':[node(child) for child in children]}
        return {'path':source.relative_to(root).as_posix(), 'metadata':metadata, 'body':body,
                'workspace':records.workspace(root,metadata.get('workspace')),
                'progress':progress[records.key(metadata)], 'embedded':current.get('embedded',False),
                'tldr':metadata.get('tldr') or '', 'root_path':ancestor['path'], 'root_kind':kind(ancestor),
                'tree':node(ancestor), 'subtasks':[r for r in records.descendants(rows,current) if r['type']=='task']}
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def local_target(root, document, src):
    source, meta, _ = records.resolve(root, document)
    parsed = urlparse(src)
    if parsed.scheme or parsed.netloc:
        raise ValueError('Only local references are resolved here')
    raw = Path(unquote(parsed.path)).expanduser()
    if parsed.fragment.startswith('tab='):
        oldbase = (root / meta.get('legacy_path', documents.physical(source).relative_to(root).as_posix())).parent
        candidates = [documents.physical(source)] if not parsed.path else ([raw] if raw.is_absolute() else [source.parent/raw, oldbase/raw])
        for candidate in candidates:
            candidate = candidate.resolve()
            if not candidate.is_relative_to(root.resolve()):
                continue
            try:
                owner, _, _ = records.resolve(root, candidate.relative_to(root).as_posix())
                ref = documents.physical(owner).relative_to(root).as_posix() + '#' + unquote(parsed.fragment)
                target, tab, _ = records.resolve(root, ref)
                return target, tab, ''
            except ValueError:
                continue
        raise ValueError('Subtab link not found')
    if raw.is_absolute():
        target = raw.resolve()
    else:
        # Existing bodies retain their original relative base; newly authored links
        # can point at canonical files when no legacy target exists.
        oldbase = (root / meta.get('legacy_path', source.relative_to(root).as_posix())).parent
        target = (oldbase / raw).resolve()
    relative = None
    if target.is_relative_to(root.resolve()):
        relative = target.relative_to(root).as_posix()
        try:
            resolved, row, _ = records.resolve(root, relative)
            return resolved, row, parsed.fragment
        except ValueError:
            mapped = records.manifest(root).get('asset_aliases',{}).get(relative)
            if mapped:
                return records.safe(root, root / mapped), None, parsed.fragment
    if not target.exists() and not raw.is_absolute():
        candidate = (source.parent / raw).resolve()
        if candidate.is_relative_to(root.resolve()):
            try:
                resolved, row, _ = records.resolve(root, candidate.relative_to(root).as_posix())
                return resolved, row, parsed.fragment
            except ValueError:
                if candidate.is_file():
                    target = candidate
    return target, None, parsed.fragment


def asset(root, document, src, allowed_roots, *, link=False):
    try:
        target, row, fragment = local_target(root, document, src)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not any(target == allowed or target.is_relative_to(allowed) for allowed in allowed_roots):
        raise HTTPException(status_code=403, detail='Asset is outside Assistant/workspace roots')
    physical = documents.physical(target)
    if not physical.is_file():
        raise HTTPException(status_code=404, detail='Asset not found')
    if link and row:
        field = {'task':'task','meeting':'meeting','series':'series','note':'note'}[kind(row)]
        return RedirectResponse('/?' + urlencode({'view':'assistant',field:target.relative_to(root).as_posix()}))
    return FileResponse(physical)
