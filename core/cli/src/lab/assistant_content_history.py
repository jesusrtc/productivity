"""Bounded, persistent body snapshots for individual Assistant document tabs."""
from __future__ import annotations

import hashlib
import json
import uuid

from lab import assistant_records as records

LIMIT = 20


def _path(root, metadata):
    identity = json.dumps([metadata['type'], metadata['id']], separators=(',', ':'))
    return root / '.assistant/content-history' / (hashlib.sha256(identity.encode()).hexdigest() + '.json')


def _read(root, metadata):
    path = _path(root, metadata)
    if not path.exists():
        return []
    rows = json.loads(path.read_text())
    if not isinstance(rows, list):
        raise ValueError('Invalid document content history')
    return rows[:LIMIT]


def remember(root, metadata, body):
    """Called under the record write lock, before replacing its body."""
    from lab import assistant as db
    rows = _read(root, metadata)
    rows.insert(0, {'id':uuid.uuid4().hex, 'saved_at':db.now_iso(), 'body':body})
    records.write_json(_path(root, metadata), rows[:LIMIT])


def versions(root, reference):
    _, metadata, _ = records.resolve(root, reference, 'documents')
    return [{'id':row['id'], 'saved_at':row['saved_at'], 'preview':row['body'][:240]}
            for row in _read(root, metadata)]


def body(root, metadata, revision):
    for row in _read(root, metadata):
        if row['id'] == revision:
            return row['body']
    raise ValueError('Saved version not found for this tab')
