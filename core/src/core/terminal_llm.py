"""Recognize manually launched agents on their own terminal's process tree."""
from pathlib import Path
import subprocess

import psutil

from lab import terminal_status, tmux_sockets
from core.terminal_automation_lifecycle import processes

AGENTS = {'claude', 'codex', 'copilot'}


def provider(pid: int, command: str) -> str | None:
    name = Path(command).name.removesuffix('.exe')
    if name in AGENTS:
        return name
    if name not in {'node', 'bun'}:
        return None
    try:
        argv = psutil.Process(pid).cmdline()
    except (psutil.Error, OSError):
        return None
    # Inspect the executed script, never prompt text or arbitrary arguments.
    script = argv[1] if len(argv) > 1 and not argv[1].startswith('-') else ''
    if script.startswith('/'):
        try:
            script = str(Path(script).resolve())
        except OSError:
            return None
    for package, agent in (('@openai/codex/', 'codex'),
                           ('@anthropic-ai/claude-code/', 'claude'),
                           ('@github/copilot/', 'copilot')):
        if '/node_modules/' + package in script:
            return agent
    return None


def enrich(rows: list[dict]) -> None:
    candidates = [row for row in rows if row.get('llm_controlled') is None]
    snapshot = processes(candidates) if candidates else None
    for row in candidates:
        descendants = {row.get('pane_pid')}
        while snapshot:
            children = {pid for pid, p in snapshot.items()
                        if p['ppid'] in descendants and not p['stat'].startswith('Z')}
            if children <= descendants:
                break
            descendants |= children
        agent = next((value for pid in sorted(descendants) if pid in (snapshot or {})
                      if not snapshot[pid]['stat'].startswith('Z')
                      if (value := provider(pid, snapshot[pid]['comm']))), None)
        row['llm_controlled'] = bool(agent)
        if not agent:
            continue
        row['agent'] = agent
        # Persist once per detected session. No registry or workspace rewrites.
        if not row.get('tmux_id'):
            continue
        try:
            subprocess.run(tmux_sockets.command(row['tmux_socket'], 'set-option',
                '-t', row['tmux_id'], terminal_status.LLM_OPTION, agent),
                capture_output=True, timeout=2, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass  # This observation remains useful; the next read can retry.
