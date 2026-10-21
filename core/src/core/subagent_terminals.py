"""Explicit delegated agents, owned by an exact Lab terminal incarnation."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core import auth
from core.routes import term
from lab import paths, agent_work
from lab.workspace_identity import operation_lease

router = APIRouter()
_lock = threading.RLock()


class Identity(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    tmux_socket: str = Field(min_length=1, max_length=4096)
    tmux_id: str = Field(pattern=r'^\$\d+$')
    created: int = Field(gt=0)


class Parent(BaseModel):
    parent: Identity


class Launch(Parent):
    request_id: uuid.UUID
    label: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=64000)
    agent: str | None = Field(default=None, pattern=r'^(copilot|codex|claude)$')
    context: str = Field(default='', max_length=64000)
    context_files: list[str] = Field(default_factory=list, max_length=16)


class Read(Parent):
    child_id: uuid.UUID
    lines: int = Field(default=200, ge=1, le=2000)


def _tmux(row, *args):
    try:
        result = subprocess.run(term._tmux_command(row['tmux_socket'], *args),
            capture_output=True, text=True, timeout=5, env=term._tmux_child_env())
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(503, 'Could not inspect this terminal; retry with the same launch request ID') from exc
    if result.returncode:
        raise HTTPException(409, 'This terminal is no longer available')
    return result.stdout


def _identity(row):
    return {key:row[key] for key in ('name', 'tmux_socket', 'tmux_id', 'created')}


def _parent(body, request):
    auth.require_admin(request)
    active = auth.request_root(request)
    vaults = term._known_vaults(active)
    rows = term._tmux_list(term._tmux_discovery_prefixes_all(vaults), prune_draining=False)
    if rows is None:
        raise HTTPException(503, 'Terminal discovery is unavailable; retry with the same launch request ID')
    row = next((row for row in rows if row['name'] == body.name
        and row['tmux_id'] == body.tmux_id and row['created'] == body.created), None)
    if not row:
        raise HTTPException(409, 'The calling parent terminal is no longer running')
    # Query only a discovered Lab socket, never an arbitrary caller-supplied path.
    socket_path = _tmux(row, 'display-message', '-p', '-t', row['tmux_id'] + ':', '#{socket_path}').strip()
    if body.tmux_socket != row['tmux_socket'] and Path(body.tmux_socket).resolve() != Path(socket_path).resolve():
        raise HTTPException(409, 'The calling terminal socket has changed')
    root = term._resolve_session_vault_root(body.name, active, vaults)
    info = term._sync_meta(root, rows).get(body.name)
    if not info or not info.get('workspace_id') or not info.get('logical_name'):
        raise HTTPException(404, 'Parent terminal ownership is unavailable')
    term._require_workspace_access(request, active, root, info['workspace_id'])
    return root, {**info, **row}, rows


def _children(root, parent, rows):
    identity = _identity(parent)
    meta = term._load_meta(root)
    # Saved rows survive backend restarts; a dead child is never restarted here.
    saved = term._workspace_session_by_name(root, parent['workspace_id'])
    children = []
    live = {row['name']:row for row in rows}
    for logical, saved_info in saved.items():
        record = saved_info.get('subagent')
        if not record or record.get('parent') != identity:
            continue
        name = record['terminal']['name']
        info = {**meta.get(name, {}), **saved_info}
        current = live.get(name)
        # A manually recreated terminal must not inherit a former child identity.
        expected = record.get('terminal')
        available = bool(current and expected == _identity(current))
        running = available and not current.get('pane_dead')
        children.append({'id':record['id'], 'name':name, 'logical_name':logical,
            'label':info.get('label') or record.get('label'), 'agent':info.get('agent'),
            'running':running, 'available':available, 'terminal_status':current.get('terminal_status') if available else None,
            'terminal':expected, 'parent':identity})
    return children


@router.post('/api/term/subagents/list')
def list_children(body: Parent, request: Request):
    """Read the calling terminal's child agents without reviewing their status."""
    root, parent, rows = _parent(body.parent, request)
    return {'parent':_identity(parent), 'children':_children(root, parent, rows)}


@router.post('/api/term/subagents')
def launch(body: Launch, request: Request):
    """Start a visible child agent; repeat request_id to recover a timed-out launch."""
    if not body.prompt.strip() or '\x00' in body.prompt or not body.label.strip():
        raise HTTPException(422, 'A non-empty name and task without NUL bytes are required')
    root, parent, _ = _parent(body.parent, request)
    folder = paths.vault_state_dir(root) / 'subagents'
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    fingerprint = hashlib.sha256(json.dumps([body.agent, body.label.strip(), body.prompt, body.context, body.context_files], ensure_ascii=False).encode()).hexdigest()
    try:
        lease = operation_lease(root, parent['workspace_id'])
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    # Serialize spawn + registration across workers, in addition to workspace moves.
    with lease, _lock, (folder / '.lock').open('a+') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        root, parent, rows = _parent(body.parent, request)
        ident = str(body.request_id)
        logical = 'subagent-' + body.request_id.hex
        saved = term._workspace_session_by_name(root, parent['workspace_id'])
        previous = saved.get(logical, {}).get('subagent')
        if previous:
            if previous['parent'] != _identity(parent):
                raise HTTPException(409, 'This launch request belongs to another parent terminal')
            if previous.get('fingerprint') != fingerprint:
                raise HTTPException(409, 'This launch request already has a different task or provider')
            child = next((row for row in _children(root, parent, rows) if row['id'] == ident), None)
            return {'request_id':ident, 'already_launched':True, 'child':child,
                    'detail':None if child and child['running'] else 'The child stopped; use a new request ID to launch another agent'}
        # A partial launch cannot be adopted or replayed without its original task.
        if logical in saved:
            raise HTTPException(409, 'This launch is incomplete; inspect the saved terminal before retrying')
        agent = body.agent or parent.get('llm_provider') or parent.get('agent')
        if agent not in {'claude', 'codex', 'copilot'}:
            raise HTTPException(400, 'Parent provider is unknown; choose --agent copilot, codex or claude')
        if not shutil.which(agent):
            raise HTTPException(400, f'{agent} CLI not found on PATH')
        if agent not in term.vault_config.supported_agents(root):
            raise HTTPException(400, f'{agent} is not enabled for this vault')
        parent_saved = saved.get(parent['logical_name'], {})
        from core.agent_work_history import canonical
        parent_identity = canonical(parent)
        parent_assignment = agent_work.current(parent_identity)
        create_parent = not parent_assignment or parent_assignment['status'] == 'finished'
        if create_parent:
            parent_assignment = {'id':str(uuid.uuid4()), 'title':'Delegation: ' + body.label.strip(), 'context':''}
        context = []
        if parent_assignment:
            context.append('Parent request: ' + parent_assignment['title'] + '\n'
                + 'Parent assignment ID: ' + parent_assignment['id'] + '\n' + parent_assignment['context'])
        if body.context and body.context != parent_assignment['context']:
            context.append('Parent briefing:\n' + body.context)
        for file in body.context_files:
            path = Path(parent['cwd']) / Path(file).expanduser()
            path = path.resolve()
            if not path.is_file():
                raise HTTPException(422, f'Context file not found: {path}')
            if path.stat().st_size > 32000:
                raise HTTPException(422, f'Context file exceeds 32000 bytes: {path}')
            try:
                text = path.read_text(encoding='utf-8')
            except UnicodeError:
                raise HTTPException(422, f'Context file must be UTF-8: {path}')
            context.append('Reference file: ' + str(path) + '\n' + text)
        context = '\n\n'.join(context)
        if len(context) > 64000:
            raise HTTPException(422, 'Parent context exceeds 64000 characters; provide a focused brief')
        task = ('You are a delegated subagent named ' + body.label.strip() + '.\n'
                'Your parent Lab terminal is ' + parent['name'] + '.\n'
                'Run lab context llm before working. Work only on the assignment below.\n'
                'Report working, attention or finished from your own terminal as instructed.\n'
                'Return concrete results and validation for your parent to inspect.\n'
                'Your request/assignment ID is ' + ident + '. Continue it with '
                'lab agents work start --id ' + ident + ' --title ' + term._shell_quote(body.label.strip()) + '.\n'
                'Record the exact files you change with lab agents files record.\n\n'
                + ('Context from parent:\n' + context + '\n\n' if context else '')
                + 'Assignment:\n' + body.prompt)
        if '\x00' in task or len(task.encode('utf-8')) > 120000:
            raise HTTPException(422, 'The combined assignment and context must fit within 120000 UTF-8 bytes without NUL bytes')
        if create_parent:
            parent_assignment = agent_work.start(parent_identity, parent_assignment['title'],
                request=body.prompt, context=body.context, assignment_id=parent_assignment['id'])
        prompt_file = folder / (body.request_id.hex + '.txt')
        # No prompt text in persisted launch commands, workspace metadata or logs.
        try:
            fd = os.open(prompt_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, 'w') as output:
                output.write(task)
        except FileExistsError:
            if prompt_file.read_text() != task:
                raise HTTPException(409, 'This request ID already has a different task')
        vault = term._vault_id_for_root(auth.request_root(request), root)
        created = term.create_session(term.NewSession(workspace_id=parent['workspace_id'],
            vault=vault, kind='claude', agent=agent, name=logical, label=body.label.strip(),
            cwd=parent['cwd'], objective_id=parent_saved.get('context_objective_id'),
            initial_prompt_file=str(prompt_file)), request)
        root, fresh_parent, rows = _parent(body.parent, request)
        current = next((row for row in rows if row['name'] == created['name']), None)
        if not current:
            raise HTTPException(502, 'The child exited during launch; inspect its provider configuration')
        record = {'id':ident, 'label':body.label.strip(), 'fingerprint':fingerprint,
                  'parent':_identity(fresh_parent), 'terminal':_identity(current)}
        entry = {'name':logical, 'parent_terminal':parent['logical_name'], 'subagent':record}
        with term._SESSION_METADATA_LOCK:
            term._upsert_workspace_session(root, parent['workspace_id'], entry)
            meta = term._load_meta(root)
            meta[created['name']].update(parent_terminal=parent['logical_name'], subagent=record)
            term._save_meta(root, meta)
        agent_work.start(canonical(current), body.label.strip(), request=body.prompt, context=context,
            parent_id=parent_assignment['id'] if parent_assignment else None, assignment_id=ident, register=True)
        term._invalidate_workspace_term_caches()
        return {'request_id':ident, 'already_launched':False,
                'child':next(row for row in _children(root, parent, rows) if row['id'] == ident)}


@router.post('/api/term/subagents/read')
def read_child(body: Read, request: Request):
    """Capture bounded child output without selecting a tab or acknowledging green."""
    root, parent, rows = _parent(body.parent, request)
    child = next((child for child in _children(root, parent, rows) if child['id'] == str(body.child_id)), None)
    if not child:
        raise HTTPException(404, 'This agent does not belong to the calling terminal')
    if not child['available']:
        raise HTTPException(409, 'This child stopped; its replacement cannot be read as the old agent')
    target = child['terminal']
    condition = f'#{{&&:#{{==:#{{session_id}},{target["tmux_id"]}}},#{{==:#{{session_created}},{target["created"]}}}}}'
    command = 'capture-pane -p -J -t ' + term._shell_quote(target['tmux_id'] + ':') + ' -S -' + str(body.lines)
    output = _tmux(target, 'if-shell', '-F', '-t', '=' + target['name'] + ':',
        condition, command, 'display-message -p lab-subagent-changed')
    if output.strip() == 'lab-subagent-changed':
        raise HTTPException(409, 'This child terminal changed before reading')
    return {**child, 'output':output}
