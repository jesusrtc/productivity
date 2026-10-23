"""One independently recoverable local CLI execution with a durable transcript."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import sys
import time

import psutil

from lab import agent_context
from lab.agentic_store import Store


def redact(value):
    """Avoid persisting common bearer/key material in provider/tool events."""
    if isinstance(value, dict):
        return {key: '[redacted]' if re.search(r'(?i)(api.?key|access.?token|refresh.?token|authorization|password|secret)', key)
                else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    value = re.sub(r'(?i)(Bearer\s+)[A-Za-z0-9._~+/-]+=*', r'\1[redacted]', value)
    value = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,})', '[redacted]', value)
    value = re.sub(r'(?i)([?&](?:access_token|refresh_token|client_secret|code)=)[^&\s"<>]+', r'\1[redacted]', value)
    return value


def parse_result(value):
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        raise ValueError('No final structured result was received')
    candidate = value.strip()
    if candidate.startswith('```'):
        candidate = re.sub(r'^```(?:json)?\s*', '', candidate)
        candidate = re.sub(r'\s*```$', '', candidate)
    result = json.loads(candidate)
    if not isinstance(result, dict):
        raise ValueError('Final result must be a JSON object')
    return result


def transcript_event(event):
    """Audit assignments, tools and results without private reasoning streams."""
    if isinstance(event, dict):
        if event.get('type') == 'acp' and event.get('data', {}).get('params', {}).get('update', {}).get('sessionUpdate') == 'agent_thought_chunk':
            return None
        if isinstance(event.get('item'), dict) and event['item'].get('type') == 'reasoning':
            return None
        message = event.get('message')
        if isinstance(message, dict) and isinstance(message.get('content'), list):
            event = {**event, 'message': {**message, 'content': [part for part in message['content']
                      if not isinstance(part, dict) or part.get('type') not in ('thinking', 'redacted_thinking')]}}
    return redact(event)


def result_text(provider, event):
    """Normalize the documented structured streams without scraping terminals."""
    if not isinstance(event, dict):
        return None
    kind = event.get('type')
    if provider == 'codex' and kind == 'item.completed':
        item = event.get('item') or {}
        if item.get('type') == 'agent_message':
            return item.get('text')
    if provider == 'claude':
        if kind == 'result':
            if event.get('is_error'):
                raise ValueError(event.get('result') or str(event.get('errors') or 'Claude execution failed'))
            return event.get('structured_output') or event.get('result')
        if kind == 'assistant':
            return '\n'.join(part.get('text', '') for part in event.get('message', {}).get('content', []) if part.get('type') == 'text') or None
    if provider == 'copilot':
        if kind == 'assistant.message':
            return (event.get('data') or {}).get('content')
        if kind == 'result':
            return event.get('result') or event.get('text')
    return None


def execute(workspace, run_id):
    from lab.workspace_identity import operation_lease
    store = Store(workspace)
    run = store.run(run_id)
    if not run:
        return
    context = run.get('context') or {}
    try:
        lease = operation_lease(Path(context['vault']), context['workspace_id'])
    except (ValueError, KeyError, OSError) as exc:
        store.finish(run_id, error=f'Cannot hold workspace during execution: {exc}')
        return
    with lease:
        _execute(workspace, run_id)


def _execute(workspace, run_id):
    store = Store(workspace)
    folder = store.directory / 'runs' / run_id
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (folder / 'runner.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        run = store.run(run_id)
        if not run or run['status'] not in ('starting', 'running'):
            return
        store.register_process(run_id, os.getpid(), psutil.Process().create_time())
        child = None
        try:
            environment = dict(os.environ)
            environment['LAB_AGENTIC_RUN'] = run_id
            environment['LAB_AGENTIC_WORKSPACE'] = str(workspace)
            argv, environment = agent_context.prepare_launch(run['provider'], run['argv'][1:],
                                                             cwd=Path(workspace), env=environment)
            store.append_event('provider-launch', {'argv': redact(argv)}, run_id=run_id, task_id=run['task_id'])
            if run['provider'] == 'copilot':
                argv = [sys.executable, '-m', 'core.agentic_copilot', '--workspace', str(workspace), '--run-id', run_id, '--', *argv]
            # The CLI cannot start until its exact process identity is durable.
            # If this runner dies during launch, EOF closes the gate instead.
            gate_read, gate_write = os.pipe()
            try:
                with (folder / 'prompt.txt').open('r', encoding='utf-8') as prompt:
                    child = subprocess.Popen([sys.executable, '-m', 'core.agentic_runner', '--gate-fd', str(gate_read), '--', *argv],
                                             stdin=prompt, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                             cwd=workspace, env=environment, start_new_session=True, pass_fds=(gate_read,))
                os.close(gate_read)
                gate_read = None
                store.register_child(run_id, child.pid, psutil.Process(child.pid).create_time())
                os.write(gate_write, b'1')
            finally:
                if gate_read is not None:
                    os.close(gate_read)
                os.close(gate_write)
            def signal_child(sig):
                try:
                    os.killpg(child.pid, sig)
                except ProcessLookupError:
                    pass
            final, error, stop, stop_at = None, None, None, None
            began = time.monotonic()
            buffers = {'stdout': b'', 'stderr': b''}
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ, 'stdout')
                selector.register(child.stderr, selectors.EVENT_READ, 'stderr')
                while selector.get_map():
                    current = store.run(run_id)
                    requested = current.get('stop_requested') if current else 'cancel'
                    if requested and not stop:
                        stop, stop_at = requested, time.monotonic()
                        signal_child(signal.SIGINT)
                        store.append_event('stop-requested', {'action': stop}, run_id=run_id, task_id=run['task_id'])
                    if stop_at and time.monotonic() - stop_at > 10 and child.poll() is None:
                        signal_child(signal.SIGTERM)
                    if stop_at and time.monotonic() - stop_at > 20 and child.poll() is None:
                        signal_child(signal.SIGKILL)
                    # The coordinator never runs long delegated work. A timeout
                    # stops this owned process; it does not silently replay it.
                    if run['role'] == 'coordinator' and time.monotonic() - began > 180 and not stop:
                        stop, stop_at = 'pause', time.monotonic()
                        error = 'Coordinator exceeded its response window. Your request is retained; retry from the chat.'
                        signal_child(signal.SIGINT)
                    for key, _ in selector.select(timeout=.5):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        stream = key.data
                        if not chunk:
                            selector.unregister(key.fileobj)
                        buffers[stream] += chunk
                        lines = buffers[stream].split(b'\n')
                        buffers[stream] = lines.pop()
                        if len(buffers[stream]) > 4_000_000:
                            raise ValueError('Provider emitted a stream record larger than 4 MB; inspect the provider session')
                        if not chunk and buffers[stream]:
                            lines.append(buffers[stream])
                            buffers[stream] = b''
                        for line in lines:
                            value = line.decode('utf-8', errors='replace')
                            if not value.strip():
                                continue
                            try:
                                event = json.loads(value) if stream == 'stdout' else {'text': value}
                            except ValueError:
                                event = {'text': value}
                            safe = transcript_event(event)
                            if safe is not None:
                                with (folder / (stream + '.jsonl')).open('a', encoding='utf-8') as output:
                                    output.write(json.dumps(safe, ensure_ascii=False) + '\n')
                                store.append_event('provider-' + stream, safe, run_id=run_id, task_id=run['task_id'])
                            if stream == 'stdout':
                                try:
                                    message = result_text(run['provider'], event)
                                    if message:
                                        final = message
                                except ValueError as exc:
                                    error = str(redact(str(exc)))
            code = child.wait(timeout=5)
            if stop:
                store.finish(run_id, stopped=stop, error=error)
            elif code != 0 or error:
                store.finish(run_id, error=error or f'{run["provider"]} exited with code {code}. Inspect Activity for login or permission instructions.')
            else:
                try:
                    store.finish(run_id, result=redact(parse_result(final)))
                except (ValueError, KeyError, TypeError) as exc:
                    if run['role'] != 'coordinator':
                        raise
                    store.coordinator_error(run_id, str(redact(str(exc))))
        except Exception as exc:
            if child and child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)
            store.finish(run_id, error=str(redact(str(exc))))
        finally:
            if child:
                if child.stdout:
                    child.stdout.close()
                if child.stderr:
                    child.stderr.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--run-id')
    parser.add_argument('--gate-fd', type=int)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.gate_fd is not None:
        admitted = os.read(args.gate_fd, 1) == b'1'
        os.close(args.gate_fd)
        if admitted:
            command = args.command[1:] if args.command[:1] == ['--'] else args.command
            os.execvpe(command[0], command, os.environ)
    elif args.workspace and args.run_id:
        execute(args.workspace, args.run_id)
    else:
        parser.error('workspace and run-id are required for a task runner')
