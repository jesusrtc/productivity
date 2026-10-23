"""Copilot CLI over local stdio ACP. No SDK, model endpoint or API credentials.

Permission requests are persisted and presented by Lab. Only a recorded user
decision can release a pending request; the CLI executes its own tools.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time

from lab.agentic_store import Store
from core.agentic_runner import redact


def emit(event):
    print(json.dumps(event, ensure_ascii=False), flush=True)


def is_startup_notice(update, parts):
    # Copilot currently sends this CLI-generated banner as an agent message,
    # even though it is not model output. Preserve it in Activity only.
    return not parts and update.get('content', {}).get('text') == 'Info: Disabled tools: task'


def execute(workspace, run_id, command, prompt):
    store = Store(workspace)
    # Inherit the runner's owned process group. Closing stdin also stops the
    # stdio server; there is no listening port or detached provider daemon.
    child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    pending, tools, parts, executing_tools = {}, {}, [], set()
    session, message_id, finished = None, None, False
    request_id, methods = 0, {}
    def send(payload):
        child.stdin.write((json.dumps(payload, ensure_ascii=False) + '\n').encode())
        child.stdin.flush()
    def call(method, params):
        nonlocal request_id
        request_id += 1
        methods[request_id] = method
        send({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params})
    def reply(ident, result):
        send({'jsonrpc': '2.0', 'id': ident, 'result': result})
    began = time.monotonic()
    call('initialize', {'protocolVersion': 1, 'clientCapabilities': {},
                        'clientInfo': {'name': 'lab', 'title': 'Lab agentic workspace', 'version': '1'}})
    buffers = {'stdout': b'', 'stderr': b''}
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ, 'stdout')
            selector.register(child.stderr, selectors.EVENT_READ, 'stderr')
            while selector.get_map() and not finished:
                run = store.run(run_id)
                if not run or run.get('stop_requested'):
                    if session:
                        send({'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': session}})
                    for ident in pending.values():
                        reply(ident, {'outcome': {'outcome': 'cancelled'}})
                    return 1
                if session is None and time.monotonic() - began > 60:
                    raise ValueError('Copilot initialization timed out; inspect CLI login and Activity')
                for permission_id, ident in list(pending.items()):
                    decision = store.take_permission(permission_id)
                    if decision:
                        reply(ident, {'outcome': {'outcome': 'selected', 'optionId': decision['option_id']}})
                        option = next(o for o in decision['request']['options'] if o['optionId'] == decision['option_id'])
                        if option['kind'] == 'allow_once':
                            executing_tools.add(decision['request'].get('toolCall', {}).get('toolCallId'))
                        del pending[permission_id]
                for key, _ in selector.select(timeout=.25):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    stream = key.data
                    if not chunk:
                        selector.unregister(key.fileobj)
                    buffers[stream] += chunk
                    lines = buffers[stream].split(b'\n')
                    buffers[stream] = lines.pop()
                    if len(buffers[stream]) > 4_000_000:
                        raise ValueError('Copilot protocol record exceeds 4 MB')
                    for line in lines:
                        if not line.strip():
                            continue
                        if stream == 'stderr':
                            print(redact(line.decode(errors='replace')), file=sys.stderr, flush=True)
                            continue
                        event = json.loads(line)
                        emit({'type': 'acp', 'data': redact(event)})
                        method, ident = event.get('method'), event.get('id')
                        if not method and ident in methods:
                            requested = methods.pop(ident)
                            if 'error' in event:
                                raise ValueError(f'Copilot {requested}: ' + str(redact(event['error'])) + '. If authentication is required, run copilot login in a terminal.')
                            result = event.get('result', {})
                            if requested == 'initialize':
                                if result.get('protocolVersion') != 1:
                                    raise ValueError('Installed Copilot uses an unsupported ACP version')
                                call('session/new', {'cwd': str(workspace), 'mcpServers': []})
                            elif requested == 'session/new':
                                session = result['sessionId']
                                store.append_event('provider-session', {'session_id': session}, run_id=run_id, task_id=run['task_id'])
                                call('session/prompt', {'sessionId': session, 'prompt': [{'type': 'text', 'text': prompt}]})
                            elif requested == 'session/prompt':
                                if result.get('stopReason') != 'end_turn':
                                    raise ValueError('Copilot ended the turn with ' + str(result.get('stopReason')))
                                emit({'type': 'assistant.message', 'data': {'content': ''.join(parts)}})
                                finished = True
                        elif method == 'session/update':
                            update = event.get('params', {}).get('update', {})
                            kind = update.get('sessionUpdate')
                            if kind in ('tool_call', 'tool_call_update'):
                                tool_id = update['toolCallId']
                                tools[tool_id] = {**tools.get(tool_id, {}), **update}
                                if update.get('status') == 'in_progress':
                                    executing_tools.add(tool_id)
                                if update.get('status') in ('completed', 'failed'):
                                    executing_tools.discard(tool_id)
                                    if not executing_tools:
                                        store.permission_idle(run_id)
                                if kind == 'tool_call':
                                    parts.clear()
                            elif kind == 'agent_message_chunk' and update.get('content', {}).get('type') == 'text':
                                if is_startup_notice(update, parts):
                                    continue
                                new_id = update.get('messageId')
                                if new_id and message_id and new_id != message_id:
                                    parts.clear()
                                message_id = new_id or message_id
                                parts.append(update['content']['text'])
                        elif method == 'session/request_permission':
                            params = event['params']
                            tool = params.get('toolCall', {})
                            params = {**params, 'toolCall': {**tools.get(tool.get('toolCallId'), {}), **tool}}
                            if run['role'] == 'coordinator':
                                # Coordinating is a short planning turn with a
                                # complete state snapshot, not delegated work.
                                reply(ident, {'outcome': {'outcome': 'cancelled'}})
                            else:
                                permission = store.permission(run_id, redact(params), executing_tools=bool(executing_tools))
                                pending[permission['id']] = ident
                        elif method and ident is not None:
                            send({'jsonrpc': '2.0', 'id': ident, 'error': {'code': -32601, 'message': 'Lab did not advertise this client capability'}})
        if not finished:
            raise ValueError('Copilot exited before returning the task result')
        return 0
    finally:
        child.stdin.close()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    try:
        raise SystemExit(execute(args.workspace, args.run_id, command, sys.stdin.read()))
    except Exception as exc:
        print(redact(str(exc)), file=sys.stderr)
        raise SystemExit(1)
