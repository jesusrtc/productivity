"""Scope-owned links shared across workspaces, with per-scope revisions."""
import hashlib
import json
from pathlib import Path

from lab import paths, settings, storage


def file():
    return paths.global_config_dir() / 'scope-links.json'


def _all():
    try:
        data = storage.read_json(file())
        if not isinstance(data, dict):
            raise ValueError('Scope link metadata must be an object')
        return data
    except FileNotFoundError:
        return {}


def revision(links):
    return hashlib.sha256(json.dumps(links, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def read(path):
    with settings._GLOBAL_WRITE_LOCK:
        links = _all().get(str(Path(path).resolve()), [])
        return {'links': links, 'revision': revision(links)}


def write(path, links, expected):
    with settings._GLOBAL_WRITE_LOCK:
        all_links = _all()
        key = str(Path(path).resolve())
        if revision(all_links.get(key, [])) != expected:
            raise ValueError('Scope links changed elsewhere. Reopen the editor before saving.')
        if links:
            all_links[key] = links
        else:
            all_links.pop(key, None)
        storage.write_json(file(), all_links)
        return {'links': links, 'revision': revision(links)}
