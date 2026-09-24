"""A terminal process exiting must promptly close its browser connection."""
import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.routes import term


@pytest.mark.parametrize('output', [b'', 'CLI error: unsupported option\r\n'.encode()])
def test_pty_eof_closes_websocket_without_waiting_for_keyboard(monkeypatch, output):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, output)
    os.close(write_fd)
    monkeypatch.setattr(term, '_term_ws_context', lambda *_: (['lab-'], 'isolated'))
    monkeypatch.setattr(term, '_tmux_available', lambda: True)
    monkeypatch.setattr(term, '_tmux_find_session_socket', lambda *_: 'isolated')
    monkeypatch.setattr(term.pty, 'fork', lambda: (2**30, read_fd))
    monkeypatch.setattr(term, '_set_winsize', lambda *_: None)
    monkeypatch.setattr(term.os, 'kill', lambda *_: None)
    monkeypatch.setattr(term.os, 'waitpid', lambda *_: (0, 0))
    from core.routes import terminal_cleanup
    accesses = []
    monkeypatch.setattr(terminal_cleanup, 'mark_access', lambda *args: accesses.append(args))
    frames, cancelled = [], []
    async def receive():
        try:
            await asyncio.Future()
        finally:
            cancelled.append(True)
    async def send(message):
        frames.append(json.loads(message))
    ws=SimpleNamespace(query_params={},accept=AsyncMock(),close=AsyncMock(),
                       receive_text=receive,send_text=send)
    async def run():
        await asyncio.wait_for(term.term_ws(ws,'lab-document-exit'), timeout=2)
    asyncio.run(run())
    assert frames[-1]['type']=='exit'
    assert ''.join(frame.get('data','') for frame in frames)==output.decode()
    assert cancelled, 'The blocked keyboard reader must be cancelled'
    ws.close.assert_awaited_once()
    assert accesses == [('lab-document-exit', 'isolated')]
    with pytest.raises(OSError):
        os.fstat(read_fd)
