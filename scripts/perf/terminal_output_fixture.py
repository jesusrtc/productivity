"""Owned TUI-style output load: scrolling log plus a verifiable input footer."""
from __future__ import annotations

import inspect


def _output_loop(marker, report_path, trace_input=False):
    import hashlib
    import json
    import os
    from pathlib import Path
    import select
    import signal
    import time
    import tty

    tty.setraw(0)
    report_path = Path(report_path)
    report_path.with_suffix('.pid').write_text(str(os.getpid()))
    typed = bytearray()
    batches = []
    inputs = []
    sequence = 0
    written_bytes = 0
    geometry = None
    footer_rows = 6
    window = 64
    running = True
    dump_requested = False

    def write(data):
        nonlocal written_bytes
        view = memoryview(data)
        while view:
            count = os.write(1, view)
            if count <= 0:
                raise RuntimeError('Output fixture failed to write')
            written_bytes += count
            view = view[count:]

    def footer():
        start = max(0, len(typed) - window)
        text = marker + ':' + str(start).zfill(6) + ':' + typed[start:].decode('ascii') + '|'
        return f'\x1b[{geometry.lines-footer_rows+1};1H\x1b[J{text}'.encode()

    def request_dump(signum, frame):
        nonlocal running, dump_requested
        running = False
        dump_requested = True

    def dump():
        report_path.write_text(json.dumps({
            'mode': 'scrolling-output-footer', 'inputBytes': len(typed),
            'inputSha256': hashlib.sha256(typed).hexdigest(),
            'outputLines': sequence, 'outputBytes': written_bytes, 'batches': batches,
            'periodMs': 50, 'linesPerBatch': 40, 'footerRows': footer_rows,
            'window': window, 'geometry': list(geometry) if geometry else None,
            'inputs': inputs if trace_input else None,
        }))
    signal.signal(signal.SIGUSR1, request_dump)
    next_output = time.monotonic()
    while True:
        # Snapshot between operations, never halfway through a batch or footer.
        if dump_requested:
            dump()
            dump_requested = False
        size = os.get_terminal_size(0)
        if size.columns < 32 or size.lines < 12:
            raise RuntimeError('Output fixture requires at least 32 columns and 12 rows')
        if size != geometry:
            geometry = size
            write(b'\x1b[r\x1b[2J\x1b[H' + footer())
        timeout = max(0, next_output - time.monotonic()) if running else 1
        ready, _, _ = select.select([0], [], [], timeout)
        if ready:
            data = os.read(0, 4096)
            received = time.time() * 1000 if trace_input else None
            if not data:
                break
            if any(value < 97 or value > 122 for value in data):
                raise RuntimeError('Unexpected input in owned output fixture')
            typed.extend(data)
            write(footer())
            if trace_input:
                inputs.append({'end': len(typed), 'bytes': len(data),
                               'readEpoch': received, 'writeEpoch': time.time() * 1000})
        if running and time.monotonic() >= next_output:
            # Keep the log in a scrolling region. Input stays in the footer;
            # cursor restoration makes its row the final output of each batch.
            top_rows = geometry.lines - footer_rows
            text = f'\x1b7\x1b[1;{top_rows}r\x1b[{top_rows};1H'
            first = sequence + 1
            for _ in range(40):
                sequence += 1
                fill = chr(65 + sequence % 26) * (geometry.columns - 15)
                text += f'\r\n\x1b[{31+sequence%6}mload {sequence:08d} {fill}\x1b[0m'
            text += '\x1b[r\x1b8'
            start = time.time() * 1000
            payload = text.encode()
            write(payload)
            batches.append({'first': first, 'last': sequence, 'bytes': len(payload),
                            'startEpoch': start, 'finishEpoch': time.time() * 1000})
            next_output += .05
            if next_output < time.monotonic() - .05:
                next_output = time.monotonic() + .05


def output_echo_program(marker: str, report_path, *, trace_input=False) -> str:
    return inspect.getsource(_output_loop) + f'\n_output_loop({marker!r}, {str(report_path)!r}, {trace_input!r})\n'
