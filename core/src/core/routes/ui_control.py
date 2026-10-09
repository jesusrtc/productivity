"""Owner CLI access to the API catalogue and an explicitly selected Lab view."""
from __future__ import annotations

import asyncio
import secrets

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from core import auth

router = APIRouter()
ACTIONS = frozenset({'inspect', 'click', 'contextmenu', 'hover', 'fill', 'key',
                     'drag', 'pointer-drag', 'scroll', 'wait', 'workspace-open', 'document-open',
                     'objective-select', 'task-open', 'terminal-select', 'terminal-rename', 'terminal-input'})


class Views:
    def __init__(self):
        self.clients = {}
        self.pending = {}

    def remove(self, client_id):
        self.clients.pop(client_id, None)
        for command_id, (owner, future) in list(self.pending.items()):
            if owner == client_id and not future.done():
                future.set_exception(HTTPException(503, 'Lab view disconnected; inspect before retrying.'))

    async def command(self, action, params, client_id, timeout):
        if client_id is None:
            if len(self.clients) != 1:
                raise HTTPException(409 if self.clients else 503,
                    'Choose --client ID using lab ui clients.' if self.clients else 'No connected Lab view. Open Lab and reload it.')
            client_id = next(iter(self.clients))
        client = self.clients.get(client_id)
        if client is None:
            raise HTTPException(404, 'Lab view not found. Run lab ui clients.')
        command_id = secrets.token_urlsafe(16)
        future = asyncio.get_running_loop().create_future()
        self.pending[command_id] = (client_id, future)
        try:
            await client['socket'].send_json({'type': 'command', 'id': command_id, 'action': action, 'params': params})
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            raise HTTPException(504, 'Lab view timed out; the action may have run. Inspect before retrying.') from exc
        except (OSError, RuntimeError) as exc:
            raise HTTPException(503, 'Lab view disconnected; inspect before retrying.') from exc
        finally:
            self.pending.pop(command_id, None)


@router.get('/api/commands')
def command_catalogue(request: Request):
    """Discover every HTTP UI operation with its parameters and body schema."""
    auth.require_admin(request)
    schema = request.app.openapi()
    return {'paths': {path: value for path, value in schema['paths'].items() if path.startswith('/api/')},
            'components': schema.get('components', {}), 'ui_actions': sorted(ACTIONS)}


@router.get('/api/ui/clients')
def clients(request: Request):
    auth.require_admin(request)
    return [{'id': client_id, **client['info']} for client_id, client in request.app.state.ui_views.clients.items()]


class Command(BaseModel):
    action: str
    params: dict = Field(default_factory=dict)
    client_id: str | None = None
    timeout: float = Field(default=15, ge=1, le=60)


@router.post('/api/ui/command')
async def command(body: Command, request: Request):
    auth.require_admin(request)
    if body.action not in ACTIONS:
        raise HTTPException(400, 'Unknown UI action. Run lab ui --help.')
    return await request.app.state.ui_views.command(body.action, body.params, body.client_id, body.timeout)


@router.websocket('/ws/ui-control')
async def connect(socket: WebSocket):
    if not auth.is_admin(auth.user_from_connection(socket)):
        await socket.close(code=4403)
        return
    origin = socket.headers.get('origin')
    expected = str(socket.url).split('/ws/', 1)[0].replace('ws:', 'http:', 1).replace('wss:', 'https:', 1)
    if origin and origin != expected:
        await socket.close(code=4403)
        return
    views = socket.app.state.ui_views
    await socket.accept()
    client_id = secrets.token_urlsafe(12)
    views.clients[client_id] = {'socket': socket, 'info': {}}
    try:
        await socket.send_json({'type': 'connected', 'id': client_id})
        while True:
            message = await socket.receive_json()
            if not isinstance(message, dict):
                continue
            if message.get('type') == 'state':
                info = message.get('info') or {}
                if isinstance(info, dict):
                    views.clients[client_id]['info'] = {key: str(info.get(key, ''))[:2048] for key in ('title', 'url', 'workspace', 'vault', 'visibility')}
            elif message.get('type') == 'result':
                pending = views.pending.get(message.get('id'))
                if pending and pending[0] == client_id and not pending[1].done():
                    if message.get('error'):
                        pending[1].set_exception(HTTPException(422, str(message['error'])[:2048]))
                    else:
                        pending[1].set_result(message.get('result'))
    except (WebSocketDisconnect, ValueError):
        pass
    finally:
        views.remove(client_id)
