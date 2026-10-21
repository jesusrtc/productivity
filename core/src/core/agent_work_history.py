"""Authorized previews of files an agent explicitly reported changing."""
import mimetypes
from pathlib import Path
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core import auth, subagent_terminals
from lab import agent_work

router = APIRouter()


class History(subagent_terminals.Parent):
    include_children: bool = False


def canonical(row):
    socket = subagent_terminals._tmux(row, 'display-message', '-p', '-t', row['tmux_id'] + ':', '#{socket_path}').strip()
    return {**subagent_terminals._identity(row), 'tmux_socket':str(Path(socket).resolve())}


@router.post('/api/term/work/history')
def history(body: History, request: Request):
    _, row, _ = subagent_terminals._parent(body.parent, request)
    return agent_work.history(canonical(row), body.include_children)


def _record(ident, request):
    auth.require_admin(request)
    row = agent_work.file_record(str(ident))
    if not row:
        raise HTTPException(404, 'Reported file not found')
    path = Path(row['path'])
    if not path.is_file():
        raise HTTPException(404, 'This file was deleted or moved after it was reported')
    return row, path


@router.get('/api/term/work/files/{ident}')
def preview(ident: uuid.UUID, request: Request):
    row, path = _record(ident, request)
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    if path.stat().st_size > 2_000_000:
        return {'kind':'binary', 'name':path.name, 'mime':mime, 'detail':'Open or download this file to view it.'}
    if mime.startswith('image/') or mime == 'application/pdf':
        return {'kind':'image' if mime.startswith('image/') else 'pdf', 'name':path.name, 'mime':mime}
    try:
        content = path.read_text(encoding='utf-8')
    except (UnicodeError, OSError):
        return {'kind':'binary', 'name':path.name, 'mime':mime}
    return {'kind':'markdown' if path.suffix.lower() in ('.md','.markdown') else 'text',
            'name':path.name, 'content':content, 'mime':mime}


@router.get('/api/term/work/files/{ident}/content')
def content(ident: uuid.UUID, request: Request, download: bool = False):
    _, path = _record(ident, request)
    # HTML is downloaded, never executed in the Lab origin by a history preview.
    mime = mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
    inline = not download and (mime.startswith('image/') or mime == 'application/pdf')
    return FileResponse(path, media_type=mime, filename=path.name,
        content_disposition_type='inline' if inline else 'attachment',
        headers={'Content-Security-Policy':"sandbox; default-src 'none'"})


@router.get('/api/term/work/files/{ident}/asset')
def relative_image(ident: uuid.UUID, request: Request, file: str):
    _, document = _record(ident, request)
    if Path(file).is_absolute() or '\x00' in file:
        raise HTTPException(400, 'Use a relative image reference')
    image = (document.parent / file).resolve()
    mime = mimetypes.guess_type(image.name)[0] or ''
    if not image.is_file() or not mime.startswith('image/'):
        raise HTTPException(404, 'Image not found')
    return FileResponse(image, media_type=mime,
        headers={'Content-Security-Policy':"sandbox; default-src 'none'"})
