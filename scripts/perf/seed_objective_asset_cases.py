"""Add named, repeatable Objective UI cases to the authorized staging workspace.

LAB_VAULT must explicitly select the staging vault. All metadata mutations use
the Lab CLI. Existing fixture content, focus order and terminal sessions stay
intact. Optional notebook runs use Lab's live executor, never a raw kernel.
"""
import argparse
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

from lab import paths

CHECKOUT = Path(__file__).resolve().parents[2]
CLI = CHECKOUT / 'core/cli/.venv/bin/lab'


class Cases:
    def __init__(self, workspace):
        self.workspace = workspace
        self.root = paths.find_vault_root()
        self.folder = paths.workspace_dir(self.root, workspace)
        self.state = self.cli('objective', 'ls', '--workspace', workspace)
        self.added = []

    def cli(self, *args):
        return json.loads(subprocess.check_output([str(CLI), *args], text=True))

    def apply(self, oid, operation, **fields):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as file:
            json.dump({'type':operation, 'objective_id':oid, **fields}, file)
            file.flush()
            self.state = self.cli('objective', 'apply', '--workspace', self.workspace, '--file', file.name)

    def owner(self, oid):
        return next(o for o in self.state['objectives'] if o['id'] == oid)

    def resource(self, oid, kind, title, **fields):
        display = title + ('.md' if kind == 'document' else '.ipynb' if kind == 'notebook' else '')
        found = next((r for r in self.owner(oid)['resources'] if r['title'] == display), None)
        if not found:
            self.apply(oid, 'resource', kind=kind, title=title, **fields)
            found = self.owner(oid)['resources'][-1]
            self.added.append(display)
        return found

    def task(self, oid, title, due=7, parent=None, done=False):
        rows = next(t for t in self.owner(oid)['tasks'] if t['id'] == parent)['children'] if parent else self.owner(oid)['tasks']
        found = next((t for t in rows if t['title'] == title), None)
        if found:
            return found
        self.apply(oid, 'task', title=title, parent_id=parent, due=(date.today()+timedelta(days=due)).isoformat())
        rows = next(t for t in self.owner(oid)['tasks'] if t['id'] == parent)['children'] if parent else self.owner(oid)['tasks']
        found = rows[-1]
        self.added.append(title)
        doc = next(r for r in self.owner(oid)['resources'] if r['id'] == found['document_id'])
        self.apply(oid, 'document', resource_id=doc['id'], tab_id=found['tab_id'], document_revision=doc['content']['revision'],
                   body=f'# {title}\n\nThis is a simulated staging task.\n\n## Outcome\nVerify the associated evidence and record the result.\n\n## Evidence\nUse this task’s attached sources; they retain their original ownership.\n\n## Next steps\n- Inspect each source.\n- Record an observation.\n- Mark complete after verification.\n')
        if done:
            self.apply(oid, 'task-update', task_id=found['id'], done=True)
        return found

    def attach(self, oid, task, **target):
        self.apply(oid, 'task-asset', task_id=task['id'], **target)

    def notebook(self, oid, title, execute):
        r = self.resource(oid, 'notebook', title)
        if execute:
            marker = '# Objective staging fixture: asset evidence'
            cells = json.loads((self.folder/r['path']).read_text())['cells']
            saved = next((c for c in cells if marker in ''.join(c.get('source', []))), None)
            code = marker + '''
from IPython.display import HTML, display
entry_points = [('SMS', 96.1), ('Recovery', 98.4), ('Settings', 99.0)]
display(HTML('<h3>Simulated verification evidence</h3><table style="border-collapse:collapse;min-width:320px"><tr><th style="text-align:left;padding:6px 16px 6px 0">Entry point</th><th style="text-align:right;padding:6px">Success</th></tr>' + ''.join(f'<tr><td style="padding:6px 16px 6px 0">{name}</td><td style="text-align:right;padding:6px">{rate:.1f}%</td></tr>' for name, rate in entry_points) + '</table>'))
display(HTML('<div style="max-width:400px">' + ''.join(f'<div>{name}<div style="background:#58a6ff;width:{rate}%;height:12px;margin:4px 0 12px"></div></div>' for name, rate in entry_points) + '</div>'))
print('Staging only: three synthetic entry points; all evidence stays in this notebook.')
'''
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py') as file:
                file.write(code); file.flush()
                command = [str(CLI), 'notebook', 'exec', str(self.folder/r['path']), '--file', file.name,
                           '--timeout', '45', '--base-url', subprocess.check_output([str(CHECKOUT/'scripts/lab-url.sh')], text=True).strip()]
                if saved:
                    command += ['--cell-id', saved['id']]
                result = subprocess.run(command, text=True, capture_output=True, check=True)
                output = json.loads(result.stdout)
                if output.get('status') == 'error' or output.get('error'):
                    raise RuntimeError('Staging notebook execution failed')
        return r


def seed(workspace, execute=False):
    if not os.environ.get('LAB_VAULT'):
        raise SystemExit('Set LAB_VAULT explicitly to the authorized staging vault')
    cases = Cases(workspace)
    names = ['phone recovery', 'repository navigation', 'release verification', 'documentation review']
    owners = {name:next((o for o in cases.state['objectives'] if o['name'] == 'Staging · '+name), None) for name in names}
    if any(o is None for o in owners.values()):
        raise SystemExit('Run seed_objectives_staging.py to create the named staging objectives first')
    original = json.loads(json.dumps(cases.state))
    untouched = [paths.workspace_file(cases.root, workspace), cases.folder/'tasks.json', cases.folder/'.lab/document-links.json']
    hashes = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in untouched if p.is_file()}
    for name in names:
        o = owners[name]; oid = o['id']
        note = cases.resource(oid, 'document', 'Sample · '+name+' evidence', body=f'# {name.title()} evidence\n\nSimulated context for exercising Objective navigation.\n\n## Review\nOpen subtabs, attach sources to tasks, and compare the native file types.\n\n<details><summary>Supporting context</summary>\n\nUse `/` in the inline editor to add blocks. These notes remain staging-owned.\n\n</details>\n')
        if not note['content']['tabs']:
            cases.apply(oid, 'subtab', resource_id=note['id'], title='Baseline', body='# Baseline\n\nRecord the starting evidence here.')
            parent = next(r for r in cases.owner(oid)['resources'] if r['id'] == note['id'])['content']['tabs'][-1]['id']
            cases.apply(oid, 'subtab', resource_id=note['id'], parent_id=parent, title='Edge cases', body='# Edge cases\n\nCheck empty input, malformed values and retries.')
            cases.apply(oid, 'subtab', resource_id=note['id'], title='Results', body='# Results\n\nRecord the observed behavior separately from the baseline.')
        note = next(r for r in cases.owner(oid)['resources'] if r['id'] == note['id'])
        nb = cases.notebook(oid, 'Sample · '+name+' notebook', execute)
        linked_nb = cases.resource(oid, 'file', 'Sample · linked existing notebook.ipynb', path=nb['path'])
        links = []
        for title, url in [
            ('Incident document', 'https://docs.google.com/document/d/staging-'+name.replace(' ', '-')+'/edit'),
            ('Recovery discussion', 'https://app.slack.com/client/staging/recovery'),
            ('Issue and acceptance criteria', 'https://staging.atlassian.net/browse/LAB-101'),
            ('Metrics dashboard', 'https://play.grafana.org/d/staging/recovery'),
            ('Repository pull requests', 'https://github.com/jesusrtc/productivity/pulls'),
            ('External reference', 'https://example.com/staging/'+name.replace(' ', '-'))]:
            children = [{'title':'Investigation tab','url':url+'?tab=investigation','tldr':'Simulated investigation destination.',
                         'sublinks':[{'title':'Malformed values','url':url+'?tab=malformed'}]},
                        {'title':'Recovery tab','url':url+'?tab=recovery'}] if title == 'Incident document' else []
            links.append(cases.resource(oid, 'link', 'Sample · '+title, url=url, tldr='Simulated '+name+' source for Objective UI verification.', metadata={'Fixture':'staging','Owner':'UI review','Related':name}, sublinks=children))
        source = cases.folder/'objectives'/oid/'sample-volume.sql'
        if not source.exists():
            source.write_text('-- Simulated staging query; no live database is contacted.\nSELECT entry_point, COUNT(*) AS attempts FROM verification_events GROUP BY entry_point;\n')
        query = cases.resource(oid, 'file', 'Sample · volume.sql', path=source.relative_to(cases.folder).as_posix())
        completed = name == 'documentation review'
        due = 2 if name == 'repository navigation' else -1 if name == 'release verification' else 7
        parent = cases.task(oid, 'Sample · Review '+name+' evidence', due=due)
        child = cases.task(oid, 'Sample · Inspect edge cases', due=due, parent=parent['id'], done=completed)
        cases.task(oid, 'Sample · Record the result', due=due, parent=parent['id'], done=completed)
        task = cases.task(oid, 'Sample · Confirm '+name+' outcome', due=due, done=completed)
        for r in [note, nb, linked_nb, query, links[0], links[1]]:
            cases.attach(oid, parent, resource_id=r['id'])
        cases.attach(oid, child, resource_id=note['id'], tab_id=note['content']['tabs'][1]['id'])
        cases.attach(oid, child, resource_id=links[0]['id'], sub_link_id=links[0]['sublinks'][0]['id'])
        cases.attach(oid, task, resource_id=links[2]['id'])
        cases.attach(oid, task, resource_id=links[3]['id'])
        if o['worktrees']:
            cases.attach(oid, parent, folder={'root':o['worktrees'][0]['path'],'path':'.'})
        assets = next(t for t in cases.owner(oid)['tasks'] if t['id'] == parent['id'])['assets']
        icon = next(a for a in assets if a.get('resource_id') == nb['id'])
        # Only initialize the chosen icon; reruns preserve manual changes.
        if not next(t for t in cases.owner(oid)['tasks'] if t['id'] == parent['id']).get('icon_asset_id'):
            cases.apply(oid, 'task-update', task_id=parent['id'], icon_asset_id=icon['id'])
    assert cases.state['focused'] == original['focused'], 'Staging examples must keep focus order'
    assert cases.state['terminal_links'] == original['terminal_links'], 'Staging examples must keep terminal associations'
    assert hashes == {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in untouched if p.is_file()}, 'Workspace/task/session metadata changed'
    for o in original['objectives']:
        current = cases.owner(o['id'])
        for r in o['resources']:
            found = next(row for row in current['resources'] if row['id'] == r['id'])
            assert {k:v for k,v in found.items() if k != 'content'} == {k:v for k,v in r.items() if k != 'content'}
            if r.get('content', {}).get('body') is not None:
                assert found['content']['body'] == r['content']['body']
                for tab in r['content']['tabs']:
                    assert next(t for t in found['content']['tabs'] if t['id'] == tab['id']) == tab, 'Existing subtab changed'
    print(json.dumps({'workspace':workspace,'added':cases.added,'objectives':[
        {'name':cases.owner(o['id'])['name'],'resources':len(cases.owner(o['id'])['resources']),
         'tasks':len(cases.owner(o['id'])['tasks']),'subtasks':sum(len(t['children']) for t in cases.owner(o['id'])['tasks']),
         'task_assets':sum(len(t.get('assets', [])) for p in cases.owner(o['id'])['tasks'] for t in [p,*p['children']])}
        for o in owners.values()], 'preserved_workspace_metadata':True,'preserved_existing_content':True,
        'preserved_terminal_associations':True,'executed_notebooks':execute}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', default='large-projects')
    parser.add_argument('--execute-notebooks', action='store_true')
    args = parser.parse_args()
    seed(args.workspace, args.execute_notebooks)
