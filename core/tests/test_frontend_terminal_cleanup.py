import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "core/src/core/static/js/lib/terminal-cleanup.js"


@pytest.mark.parametrize("action", ["cancel", "group", "all", "error"])
def test_cleanup_modal_reviews_names_and_sends_only_confirmed_snapshot(action):
    node = shutil.which("node")
    if not node:
        pytest.skip("node required")
    harness = r'''
class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.events = {}; this.isConnected = true; }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this[name] = value; }
  addEventListener(name, fn) { this.events[name] = fn; }
  focus() { document.activeElement = this; }
  showModal() { this.open = true; }
  close() { this.open = false; this.events.close?.(); }
  click() { if (this.disabled) throw Error('Clicked disabled button'); return this.events.click(); }
}
globalThis.document = {createElement: tag => new Element(tag), body: new Element('body'), activeElement: new Element('button')};
let requests = [], confirmations = [], stopped = [];
const session = (id, workspace) => ({id, workspace_id: workspace, workspace_name: workspace, vault:'v',
  name:'lab-'+id, label:'Name <'+id+'>', last_used:Date.now()/1000-9*86400});
const a = session('one', 'demo'), b = session('two', 'elsewhere');
const data = {groups:[{id:'a', name:'Demo', workspace_id:'demo', vault:'v', sessions:[a]},
  {id:'b', name:'Elsewhere', workspace_id:'elsewhere', vault:'v', sessions:[b]}], warnings:[]};
globalThis.window = {confirm: message => { confirmations.push(message); return ACTION !== 'cancel'; },
  LabTerminalCleanupBridge: {scope:()=>({workspace_id:'demo',vault:'v'}), stopped:async rows=>{stopped.push(...rows);}}};
globalThis.fetch = async (url, options) => {
  requests.push({url,...options});
  if (!options) return {ok:true,json:async()=>data};
  if (ACTION === 'error') return {ok:false,json:async()=>({detail:'Server unavailable'})};
  const ids = JSON.parse(options.body).candidates;
  return {ok:true,json:async()=>({killed:[a,b].filter(s=>ids.includes(s.id)), skipped:[],errors:[],warnings:[]})};
};
function walk(node) { return [node,...node.children.flatMap(walk)]; }
'''
    assertions = r'''
(async () => {
  await window.LabTerminalCleanup.open();
  const dialog = document.body.children[0];
  const visible = walk(dialog).map(n=>n.textContent).filter(Boolean);
  if (!visible.includes('lab-one') || !visible.includes('lab-two')) throw Error('Missing exact session names');
  if (!visible.includes('Name <one>')) throw Error('Label not rendered safely as text');
  const buttons = walk(dialog).filter(n=>n.tag==='button');
  const target = ACTION === 'all' ? buttons.find(b=>b.textContent==='Kill all 2 inactive') : buttons.find(b=>b.textContent==='Kill 1 inactive');
  await target.click();
  console.log(JSON.stringify({requests,confirmations,stopped,visible:walk(dialog).map(n=>n.textContent).filter(Boolean)}));
})().catch(e=>{console.error(e);process.exit(1);});
'''
    result = subprocess.run([node, "-e", "const ACTION=" + json.dumps(action) + ";\n" + harness + SCRIPT.read_text() + assertions],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "lab-one" in data["confirmations"][0]
    posts = [r for r in data["requests"] if r.get("method") == "POST"]
    if action == "cancel":
        assert posts == []
        assert data["stopped"] == []
    else:
        assert len(posts) == 1
        assert json.loads(posts[0]["body"]) == {"candidates": ["one", "two"] if action == "all" else ["one"]}
        if action == "error":
            assert not data["stopped"]
            assert any("Server unavailable" in text for text in data["visible"])
        else:
            assert len(data["stopped"]) == (2 if action == "all" else 1)


def test_cleanup_button_is_next_to_logs_in_home_and_other_scopes():
    source = (ROOT / "core/src/core/static/js/lab-app.js").read_text()
    lines = source.splitlines()
    buttons = [i for i, line in enumerate(lines) if 'class="repo-tab terminal-cleanup-tab"' in line]
    assert len(buttons) == 2
    for index in buttons:
        assert 'home-logs-tab' in lines[index - 1]
    html = (ROOT / "core/src/core/templates/index.html").read_text()
    assert '/static/js/lib/terminal-cleanup.js?v=' in html
    assert '/static/css/terminal-cleanup.css?v=' in html
