"""Validate retained input and rendered scrolling load in the owned TUI probe."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import subprocess
import sys
import termios
import time
import fcntl

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_output_readers_require_exact_suffixes_and_independent_render_continuity():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    script = r'''
import assert from 'node:assert/strict';
import {echoInput,echoTextThroughCursor,createOutputEchoReader,readRenderedOutput} from HELPER;
const expected=echoInput(5000),marker='ready-marker';
const frame=(end,start=Math.max(0,end-64))=>marker+':'+String(start).padStart(6,'0')+':'+expected.slice(start,end)+'|';
const parse=createOutputEchoReader(expected,marker),render=createOutputEchoReader(expected,marker);
for(let end=0;end<=5000;end+=5) {
  const text='load 00000001 BBB\n'+frame(end);
  assert.equal(parse(text,end),end);assert.equal(render(text,end),end);
}
for(const reader of [parse,render]) {
  assert.equal(reader.snapshot().verified,5000);assert.ok(reader.snapshot().suffixReads>0);
}
const anchored=()=>{const read=createOutputEchoReader(expected,marker);read(frame(60),60);return read;};
assert.throws(()=>createOutputEchoReader(expected,marker)(frame(100),100),/Unverified/);
assert.throws(()=>anchored()(frame(130),130),/Unverified/);
assert.throws(()=>anchored()(frame(100),90),/ahead of observed/);
assert.throws(()=>anchored()(frame(100).replace(/.\|$/,'!|'),100),/Malformed/);
assert.throws(()=>anchored()(marker+':000036:'+expected.slice(36,99)+'z|',100),/does not match/);
assert.throws(()=>anchored()(frame(70,20),70),/invalid length/);
assert.throws(()=>anchored()(frame(65,0),65),/invalid length/);
assert.throws(()=>anchored()(marker+':bad:abc|',60),/Malformed/);
for(const limit of [-1,Infinity,undefined,5001,.5])assert.throws(()=>anchored()(frame(60),limit),/Invalid/);
const incomplete=anchored();
for(const text of ['load 00000099 ABC',frame(100).slice(0,-1),marker+':000036:'])assert.equal(incomplete(text,100),null);
assert.equal(incomplete.snapshot().verified,60);assert.equal(incomplete.snapshot().pendingReads,3);
assert.equal(incomplete(frame(100),100),100);
assert.equal(incomplete(frame(60),100),60);assert.equal(incomplete.snapshot().verified,100);
assert.equal(incomplete(frame(160),160),160);
const parsed=anchored(),rendered=anchored();
parsed(frame(100),100);parsed(frame(150),150);
assert.throws(()=>rendered(frame(150),150),/Unverified/);

// A full rightmost cell is visible even if tmux leaves its cursor on it.
// Only the footer's exact terminator protocol authorizes including that cell.
const marginMarker='ready-'+('a'.repeat(32)),marginReader=createOutputEchoReader(expected,marginMarker);
for(let end=0;end<=200;end++) {
  const offset=Math.max(0,end-64),text=marginMarker+':'+String(offset).padStart(6,'0')+':'+expected.slice(offset,end)+'|';
  const lines=text.match(/.{1,49}/g),tail=lines.at(-1);
  const buffer={baseY:0,cursorY:lines.length-1,cursorX:tail.length===49?48:tail.length,
    getLine(row){return {translateToString(trim,start=0,end){return (lines[row]||'').padEnd(49,' ').slice(start,end).trimEnd();}};}};
  assert.equal(marginReader(echoTextThroughCursor(buffer,49,true),end),end);
  if(tail.length===49) {
    assert.equal(createOutputEchoReader(expected,marginMarker)(echoTextThroughCursor(buffer,49),end),null);
    assert.throws(()=>marginReader(echoTextThroughCursor(buffer,49,true),end-1),/ahead of observed/);
    // No terminator means incomplete, even when the last cell was included.
    lines[lines.length-1]=tail.slice(0,-1)+' ';
    assert.equal(marginReader(echoTextThroughCursor(buffer,49,true),end),null);
  }
}

const cols=49,rows=20,viewportY=100,lines=new Map(),asked=[];
const line=n=>'load '+String(n).padStart(8,'0')+' '+String.fromCharCode(65+n%26).repeat(cols-15);
const buffer={viewportY,getLine(index){asked.push(index);return {translateToString(trim){assert.equal(trim,true);return lines.get(index)||'';}};}};
lines.set(102,line(20));lines.set(108,line(21));lines.set(114,line(999)); // Footer excluded.
assert.deepEqual(readRenderedOutput(buffer,{start:2,end:5},cols,rows),{maximum:20,observed:1});
assert.deepEqual(asked,[102,103,104,105]);asked.length=0;
assert.deepEqual(readRenderedOutput(buffer,{start:-1,end:200},cols,rows),{maximum:21,observed:2});
assert.ok(asked.every(n=>n>=100 && n<=113));
lines.set(102,line(20).slice(0,-1)); // A partial transport line is pending.
assert.deepEqual(readRenderedOutput(buffer,{start:2,end:5},cols,rows),{maximum:0,observed:0});
lines.set(102,line(20).slice(0,-1)+'A');
assert.throws(()=>readRenderedOutput(buffer,{start:2,end:5},cols,rows),/Corrupted/);
lines.set(102,line(20).replace('00000020','bad-seq!'));
assert.throws(()=>readRenderedOutput(buffer,{start:2,end:5},cols,rows),/Malformed/);
console.log('PASS');
'''.replace('HELPER', json.dumps((ROOT / 'scripts/perf/terminal_echo_reader.mjs').as_uri()))
    result = subprocess.run([node, '--input-type=module', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'


def _program(path, traced=False):
    spec = importlib.util.spec_from_file_location('output_fixture', ROOT / 'scripts/perf/terminal_output_fixture.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.output_echo_program('READY', path, trace_input=traced)


@pytest.mark.parametrize('traced', [False, True])
def test_output_fixture_retains_input_across_resize_and_exports_output_proof(tmp_path, traced):
    path = tmp_path / 'output.json'
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 20, 49, 0, 0))
    child = subprocess.Popen([sys.executable, '-u', '-c', _program(path, traced)],
                             stdin=slave, stdout=slave, stderr=subprocess.PIPE)
    os.close(slave)
    output = bytearray()

    def drain_until(predicate):
        deadline = time.monotonic() + 3
        while not predicate():
            assert time.monotonic() < deadline and child.poll() is None
            if select.select([master], [], [], .02)[0]:
                output.extend(os.read(master, 65536))

    try:
        drain_until(lambda: b'READY:000000:|' in output)
        typed = b'abcdefghijklmnopqrstuvwxyz' * 5
        for start in range(0, len(typed), 13):
            chunk = typed[start:start + 13]
            os.write(master, chunk)
            end = start + len(chunk)
            offset = max(0, end - 64)
            expected = b'READY:' + str(offset).zfill(6).encode() + b':' + typed[offset:end] + b'|'
            drain_until(lambda: expected in output)
        fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 60, 0, 0))
        drain_until(lambda: b'\x1b[19;1H\x1b[J' + expected in output and b'load 00000080 ' in output)
        assert int(path.with_suffix('.pid').read_text()) == child.pid
        child.send_signal(signal.SIGUSR1)
        report = None

        def dumped():
            nonlocal report
            try:
                report = json.loads(path.read_text())
                return True
            except (FileNotFoundError, json.JSONDecodeError):
                return False

        drain_until(dumped)
        assert report['inputBytes'] == len(typed)
        assert report['inputSha256'] == hashlib.sha256(typed).hexdigest()
        assert report['geometry'] == [60, 24]
        assert report['outputLines'] >= 80
        assert report['outputLines'] == len(report['batches']) * 40
        assert report['outputBytes'] >= sum(row['bytes'] for row in report['batches'])
        for index, row in enumerate(report['batches']):
            assert (row['first'], row['last']) == (index * 40 + 1, index * 40 + 40)
            assert row['finishEpoch'] >= row['startEpoch'] and row['bytes'] > 40 * 48
        if traced:
            assert sum(row['bytes'] for row in report['inputs']) == len(typed)
            assert report['inputs'][-1]['end'] == len(typed)
            assert all(row['writeEpoch'] >= row['readEpoch'] for row in report['inputs'])
            assert all(set(row) == {'end', 'bytes', 'readEpoch', 'writeEpoch'} for row in report['inputs'])
        else:
            assert report['inputs'] is None
        assert child.poll() is None, 'Export leaves the owned fixture alive for normal terminal cleanup'
    finally:
        child.terminate()
        child.wait(timeout=3)
        child.stderr.close()
        os.close(master)


@pytest.mark.parametrize('geometry', [(31, 20), (49, 11)])
def test_output_fixture_rejects_unusable_geometry(tmp_path, geometry):
    master, slave = pty.openpty()
    cols, rows = geometry
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
    try:
        result = subprocess.run([sys.executable, '-u', '-c', _program(tmp_path / 'output.json')],
                                stdin=slave, stdout=slave, stderr=subprocess.PIPE, timeout=3)
        assert result.returncode != 0
        assert b'requires at least 32 columns and 12 rows' in result.stderr
    finally:
        os.close(master)
        os.close(slave)


@pytest.mark.parametrize('flags', [[], ['--typing'], ['--server-timings', '/tmp/not-created-output-test.json']])
def test_output_mode_requires_native_typing_and_a_sidecar_before_starting(flags):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--typing-output', *flags], capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert '--typing-output requires --typing and --server-timings' in result.stderr


def test_output_browser_rejects_a_non_fixture_workspace_before_opening_chrome():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    result = subprocess.run([node, str(ROOT / 'scripts/perf/lab_terminal_interactive_latency.mjs'),
                             'http://127.0.0.1:1', 'owned', 'READY', '20', '/tmp/user-workspace', '.025'],
                            env={**os.environ, 'LAB_PROBE_COOKIE': 'test', 'LAB_PERF_OUTPUT_REPORT': '/tmp/test-output.json'},
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'Output load requires the disposable navigation fixture' in result.stderr
