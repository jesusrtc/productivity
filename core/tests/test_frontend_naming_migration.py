import json
from pathlib import Path
import subprocess


def test_preferences_migrate_once_without_changing_user_text_or_paths():
    script = Path(__file__).resolve().parents[1] / 'src/core/static/js/lib/naming-migration.js'
    js = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const originalGroups = {tabGroups: [{id:'g1', name:'workspace project', color:'#123456'}], tabMembership: {codex:'g1'}};
const data = new Map([
 ['labOpenWorkspaces-v1','["local","ssd"]'],
 ['labTermShown:workspace','0'],
 ['labTermShown:project:demo','1'],
 ['labTermGroups-v1',JSON.stringify({'local::__workspace__':originalGroups})],
 ['labLastDoc-v1',JSON.stringify({'/data/projects/demo':'notes/workspace.md'})],
 ['unrelated-workspace', 'leave this alone'],
]);
const context = {localStorage:{get length(){return data.size}, key:i=>[...data.keys()][i], getItem:k=>data.get(k)??null, setItem:(k,v)=>data.set(k,String(v))}};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
assert.equal(data.get('labOpenVaults-v1'),'["local","ssd"]');
assert.equal(data.get('labTermShown:vault'),'0');
assert.equal(data.get('labTermShown:workspace:demo'),'1');
assert.deepEqual(JSON.parse(data.get('labTermGroups-v1'))['local::__vault__'], originalGroups);
assert.equal(data.get('labLastDoc-v1'),JSON.stringify({'/data/projects/demo':'notes/workspace.md'}));
assert.equal(data.get('unrelated-workspace'), 'leave this alone');
const once = JSON.stringify([...data]);
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),context);
assert.equal(JSON.stringify([...data]),once);
'''
    result = subprocess.run(['node', '-e', js, str(script)], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
