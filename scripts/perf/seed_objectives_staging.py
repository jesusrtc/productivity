"""Seed owned Objective fixtures through Lab without editing workspace metadata.

Run against the explicitly selected staging vault. Existing terminals and
Assistant documents are never edited. Re-running reuses this named fixture.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import date, timedelta
from lab import paths, storage

CHECKOUT = Path(__file__).resolve().parents[2]
CLI = CHECKOUT / 'core/cli/.venv/bin/lab'
WORKSPACE = 'large-projects'


def cli(*args):
    return json.loads(subprocess.check_output([str(CLI), *args], env=os.environ, text=True))


def apply(action):
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
        json.dump(action, file); file.flush()
        return cli('objective', 'apply', '--workspace', WORKSPACE, '--file', file.name)


def seed():
    root = paths.find_vault_root()
    folder = paths.workspace_dir(root, WORKSPACE)
    metadata = storage.read_json(paths.workspace_file(root, WORKSPACE))
    worktrees = metadata.get('worktrees', [])
    repo_names = ['linux', 'llvm-project', 'kubernetes', 'cpython', 'rust', 'git']
    registered = {}
    for tree in worktrees:
        repo = Path(tree.get('repo', ''))
        path = tree.get('dir') or tree.get('path')
        if repo.name in repo_names and path:
            registered[repo.name] = {**tree, 'path':str((folder / path).resolve())}
    if any(repo not in registered for repo in repo_names):
        raise SystemExit('The large-projects staging workspace needs its six registered repository worktrees')
    state = cli('objective', 'ls', '--workspace', WORKSPACE)
    if any(o['name'] == 'Staging · phone recovery' for o in state['objectives']):
        print(json.dumps({'fixture': 'existing', 'objectives': len(state['objectives'])}))
        return
    names = ['phone recovery', 'repository navigation', 'release verification', 'parked investigation']
    repos = repo_names
    ids = []
    for i, name in enumerate(names):
        state = apply({'type': 'create', 'name': 'Staging · ' + name,
                       'purpose': 'Simulated UI data for objectives, documents, tasks and terminals.',
                       'replace': ids[0] if i == 3 else None})
        o = state['objectives'][-1]; ids.append(o['id'])
        for repo in repos[i*2:i*2+2]:
            tree = registered[repo]
            state = apply({'type': 'worktree', 'objective_id': o['id'],
                'path': tree['path'], 'repo': tree['repo'],
                'label': repo + '/' + tree.get('branch', 'lab-large-projects'),
                'branch': tree.get('branch', 'lab-large-projects')})
        state = apply({'type':'resource', 'objective_id':o['id'], 'kind':'document', 'title':'Incident notes',
                      'body':'# Incident notes\n\nThis is simulated staging content.\n\n- Goal: verify project navigation\n- Evidence: UI tests and click measurements\n'})
        r = state['objectives'][-1]['resources'][-1]
        state = apply({'type':'subtab','objective_id':o['id'],'resource_id':r['id'],
                      'title':'Validate phone parsing','body':'# Validate phone parsing\n\nCheck malformed input and recovery.'})
        parent = state['objectives'][-1]['resources'][-1]['content']['tabs'][0]['id']
        apply({'type':'subtab','objective_id':o['id'],'resource_id':r['id'],'parent_id':parent,
               'title':'Malformed number cases','body':'# Malformed number cases\n\nPreserve country code and invalid-input evidence.'})
        apply({'type':'subtab','objective_id':o['id'],'resource_id':r['id'],
               'title':'Verification results','body':'# Verification results\n\nRecord successful checks here.'})
        apply({'type':'resource','objective_id':o['id'],'kind':'notebook','title':'Volume analysis'})
        apply({'type':'resource','objective_id':o['id'],'kind':'link','title':'PRs for this objective','url':'https://github.com/jesusrtc/productivity/pulls'})
        due = date.today() + timedelta(days=[7,2,-1,10][i])
        for title in ['Reproduce the issue','Verify the fix','Record the evidence']:
            state = apply({'type':'task','objective_id':o['id'],'title':title,'due':due.isoformat()})
        task = state['objectives'][-1]['tasks'][0]
        apply({'type':'task','objective_id':o['id'],'parent_id':task['id'],'title':'Inspect malformed input'})
        state = apply({'type':'task','objective_id':o['id'],'parent_id':task['id'],'title':'Compare the happy path'})
        apply({'type':'task-update','objective_id':o['id'],'task_id':task['id'],'done':True})
    state = apply({'type':'focus','objective_id':ids[0],'replace':ids[3]})
    print(json.dumps({'fixture':'created','objectives':len(state['objectives']),
                      'focused':len(state['focused']),'worktrees':sum(len(o['worktrees']) for o in state['objectives'])}))


if __name__ == '__main__':
    seed()
