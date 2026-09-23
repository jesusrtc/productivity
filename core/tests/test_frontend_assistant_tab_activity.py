"""Exercise recent tab markers, dismissal, reload, change isolation, and expiry."""
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT/'core/src/core/static'


def test_task_and_note_tab_activity_browser(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant_documents as documents, assistant_migration as migration, assistant_records as records
    from .test_assistant_routes import _seed
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)
    now = datetime.now(timezone.utc)
    iso = lambda age: (now-timedelta(days=age)).isoformat()
    fixtures = {'now':now.timestamp()*1000, 'cases':{}, 'details':{}, 'changed':{}}
    for kind in ['task', 'note']:
        parent = records.create(root, kind, 'Planning' if kind=='task' else 'Meeting notes', body='Main content')
        children = {}
        for name, created, updated in [('New research',.25,.25), ('Recent decisions',10,1), ('Older context',10,4)]:
            child = records.create_subtab(root, name, parent={'type':kind, 'id':parent.stem})
            meta, _ = documents.read(child)
            meta.update(created=iso(created), updated=iso(updated))
            documents.write(child, meta, 'Content for '+name)
            children[name] = str(child.relative_to(root))
        meta, body = documents.read(parent)
        meta.update(created=iso(10), updated=iso(4))
        documents.write(parent, meta, body)
        reference = str(parent.relative_to(root))
        fixtures['cases'][kind] = {'root':reference, 'new':children['New research'], 'updated':children['Recent decisions'], 'old':children['Older context']}
        for path in [reference, *children.values()]:
            endpoint = kind if path==reference else 'note'
            response = client.get('/api/assistant/'+endpoint, params={'path':path})
            assert response.status_code==200, response.text
            fixtures['details'][path] = response.json()
    fixtures['index'] = client.get('/api/assistant').json()
    for kind, case in fixtures['cases'].items():
        records.update_body(root, case['new'], 'New revision after dismissal', expected='Content for New research')
        for path in case.values():
            fixtures['changed'][path] = client.get('/api/assistant/'+(kind if path==case['root'] else 'note'), params={'path':path}).json()
    checks = r'''
const assert=(condition,message)=>{if(!condition)throw new Error(message)};
const until=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
let now=FIX.now;
Date.now=()=>now;
const nav=()=>document.getElementById('assistantDocumentNav');
const tab=path=>[...nav().querySelectorAll('[data-record-path]')].find(row=>row.dataset.recordPath===path);
const badge=path=>tab(path).querySelector('[data-tab-activity]');
const label=path=>badge(path).hidden?'':badge(path).dataset.activityKind;
const dismiss=path=>{
 const menu=tab(path).closest('.assistant-record-tab-row').querySelector('details');
 menu.open=true;
 menu.querySelector('[data-dismiss-tab-activity]').click();
};
window.fetch=async (url,options={})=>{
 assert(!options.method,'Activity must not write user documents');
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing'})};
};
(async()=>{
 AssistantView.init({section:'tasks'});
 await until(()=>document.querySelector('[data-assistant-document][data-document-kind="task"]'));
 const task=FIX.cases.task;
 await AssistantView.openDocument('task',task.root);
 if(!sessionStorage.getItem('activity-reloaded')){
  assert(label(task.new)==='New'&&label(task.updated)==='Updated','tasks distinguish new and updated tabs');
  assert(label(task.root)===''&&label(task.old)==='','older tabs stay quiet');
  assert(badge(task.new).textContent===''&&badge(task.updated).textContent==='','activity dots never consume title width with text');
  assert(badge(task.new).getAttribute('aria-label')==='New'&&badge(task.updated).title.startsWith('Updated'),'dots retain accessible descriptions');
  assert(badge(task.new).getBoundingClientRect().width===6&&badge(task.updated).getBoundingClientRect().width===6,'both markers are small dots');
  assert(getComputedStyle(badge(task.new)).backgroundColor!==getComputedStyle(badge(task.updated)).backgroundColor,'new and updated dots have distinct colors');
  tab(task.new).click();
  await until(()=>tab(task.new).classList.contains('active'));
  assert(label(task.new)==='New','opening a tab does not clear highlight');
  dismiss(task.new);
  assert(label(task.new)===''&&label(task.updated)==='Updated','dismiss only chosen tab');
  assert(tab(task.new).classList.contains('active'),'dismiss does not navigate');
  sessionStorage.setItem('activity-reloaded','yes');
  location.reload();return;
 }
 assert(label(task.new)==='','dismissal survives real page reload');
 assert(label(task.updated)==='Updated','undismissed tab survives reload');
 assert(tab(task.new).classList.contains('active'),'last opened tab survives real reload');
 const original=nav().querySelector('.assistant-record-tree');
 await AssistantView.refresh();
 assert(nav().querySelector('.assistant-record-tree')===original,'highlight polling keeps existing tabs');
 Object.assign(FIX.details,FIX.changed);
 // Reload just this document from the API, simulating a later external edit.
 await AssistantView.openDocument('task',task.root);
 assert(label(task.new)==='Updated','later revision highlights dismissed tab again');
 assert(label(task.root)===''&&label(task.old)==='','child edit does not highlight parent or siblings');
 nav().querySelector('[data-record-index]').click();
 assert([...document.querySelectorAll('.assistant-index [data-tab-activity]')].some(row=>row.dataset.tabActivity===task.new&&row.dataset.activityKind==='Updated'&&!row.hidden),'Index mirrors tab markers');
 dismiss(task.new);
 assert([...document.querySelectorAll('.assistant-index [data-tab-activity]')].find(row=>row.dataset.tabActivity===task.new).hidden,'dismiss clears Index marker');
 // A different window may already have dismissed a still newer revision.
 const storageKey='lab.assistant.tab-activity.v1:'+FIX.index.root;
 const stored=JSON.parse(localStorage.getItem(storageKey));
 const freshRow=FIX.changed[task.new].tree.children.find(row=>row.path===task.new);
 const key=JSON.stringify([freshRow.type,freshRow.id]);
 stored[key]={...stored[key],revision:'newer-window-revision',dismissed:true};
 localStorage.setItem(storageKey,JSON.stringify(stored));
 window.dispatchEvent(new StorageEvent('storage',{key:storageKey}));
 assert(label(task.new)===''&&JSON.parse(localStorage.getItem(storageKey))[key].revision==='newer-window-revision','stale window preserves newer dismissal');
 const note=FIX.cases.note;
 // Start Notes from its original data so its own creation marker is visible.
 const originalNote=structuredClone(FIX.originalNote);
 Object.assign(FIX.details,originalNote);
 await AssistantView.openDocument('note',note.root);
 assert(label(note.new)==='New'&&label(note.updated)==='Updated','notes use the same markers');
 dismiss(note.updated);
 assert(label(note.updated)===''&&label(note.new)==='New','note dismiss is independent');
 const noteTree=nav().querySelector('.assistant-record-tree');
 now += 3*86400000;
 document.dispatchEvent(new Event('visibilitychange'));
 assert(label(note.new)===''&&label(note.updated)==='','markers expire after three days without navigation');
 assert(nav().querySelector('.assistant-record-tree')===noteTree,'expiry does not rebuild tabs or lose focus');
 await AssistantView.openDocument('task',task.root);
 assert(label(task.updated)==='','older update expires too');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    fixtures['originalNote'] = {path:fixtures['details'][path] for path in fixtures['cases']['note'].values()}
    scripts='\n'.join('<script>'+(STATIC/path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js','js/lib/markdown-content.js','js/views/assistant.js'])
    page=tmp_path/'activity.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+(STATIC/'css/lab-shell.css').read_text()+'</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+'<script>const FIX='+json.dumps(fixtures).replace('</','<\\/')+';\n'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run','--no-default-browser-check','--allow-file-access-from-files','--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline,'Chrome did not start'
            time.sleep(.05)
        result=subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'activity.png')],capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1]=='PASS',result[1] if result else html[-1000:]
