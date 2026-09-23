"""Verify every echoed key even when tmux scrolls its initial marker away."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_echo_reader_checks_continuity_and_rejects_bad_scrolled_text():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node required')
    script = r'''
import assert from 'node:assert/strict';
import {echoInput,createEchoReader} from HELPER;
const expected=echoInput(5000),marker='ready-marker';
assert.match(expected,/^[a-z]{5000}$/);
assert.equal(echoInput(5000),expected,'fixture stream must be reproducible');
assert.notEqual(echoInput(5000,818),expected);
const parse=createEchoReader(expected,marker),render=createEchoReader(expected,marker);
for(let end=0;end<=5000;end+=5) {
  const text=end<=96?'shell text '+marker+expected.slice(0,end):expected.slice(end-96,end);
  assert.equal(parse(text,end),end);
  assert.equal(render(text,end),end);
}
assert.equal(parse.snapshot().verified,5000);
assert.equal(render.snapshot().verified,5000);
assert.ok(parse.snapshot().scrolledReads>0 && render.snapshot().scrolledReads>0,'record actual scroll coverage');
const anchored=()=>{const read=createEchoReader(expected,marker);assert.equal(read(marker+expected.slice(0,100),100),100);return read};
assert.throws(()=>createEchoReader(expected,marker)(expected.slice(40,120),120),/before verification/);
assert.equal(anchored()(expected.slice(40,120),120),120);
assert.throws(()=>anchored()(expected.slice(110,200),200),/Unverified/);
assert.throws(()=>anchored()(expected.slice(80,110),110),/Insufficient/);
assert.throws(()=>anchored()(expected.slice(40,120),110),/ahead of observed/);
assert.throws(()=>anchored()(expected.slice(40,70)+'!'+expected.slice(70,120),121),/does not match/);
assert.throws(()=>anchored()(expected.slice(40,70)+expected.slice(71,120),120),/does not match/);
assert.throws(()=>anchored()(marker+expected.slice(0,100)+'!',101),/does not match/);
for(const limit of [-1,Infinity,undefined,5001,0.5])assert.throws(()=>anchored()(expected.slice(40,120),limit),/Invalid/);
const redraw=anchored();
assert.equal(redraw(expected.slice(40,120),120),120);
assert.equal(redraw(expected.slice(20,100),120),100,'an older redraw does not forget verified progress');
assert.equal(redraw(expected.slice(110,200),200),200);
const repeating=createEchoReader('a'.repeat(300),marker);
repeating(marker+'a'.repeat(100),100);
assert.throws(()=>repeating('a'.repeat(64),150),/ambiguous/);
// Parsing cannot authorize text that scrolled away before any render observed it.
const parsed=anchored(),rendered=anchored();
parsed(expected.slice(40,120),120);parsed(expected.slice(110,200),200);
assert.throws(()=>rendered(expected.slice(110,200),200),/Unverified/);
console.log('PASS');
'''.replace('HELPER', json.dumps((ROOT / 'scripts/perf/terminal_echo_reader.mjs').as_uri()))
    result = subprocess.run([node, '--input-type=module', '-e', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'PASS'
