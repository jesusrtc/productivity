"""Exercise the real document renderer and navigation in Chrome, without client data."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / 'core/src/core/static'


def test_independent_record_tree_browser(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant as db, assistant_records as records, assistant_migration as migration, assistant_documents as documents
    from .test_assistant_routes import _seed
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    data_root, task = _seed(monkeypatch, tmp_path, monorepo)
    migration.migrate(data_root, dry_run=False)
    child = db.create_subtask(data_root, 'Child task', parent=task.stem)
    thread = records.create(data_root, 'note', 'Discussion', note_type='thread', parent={'type':'task','id':child.stem}, body='# Decision\n\nKeep nested notes.')
    project = records.create(data_root, 'project', 'Launch', status='active')
    standalone=records.create(data_root,'note','Independent note',body='# Personal note\n\nOnly this tab.')
    documents.migrate(data_root,dry_run=False)
    paths = [str(records.resolve(data_root,p.stem)[0].relative_to(data_root)) for p in (task,child,thread)]
    details = {path:client.get('/api/assistant/'+ ('note' if path.endswith(thread.stem) else 'task'),params={'path':path}).json() for path in paths}
    standalone_path=str(standalone.relative_to(data_root))
    details[standalone_path]=client.get('/api/assistant/note',params={'path':standalone_path}).json()
    fixtures = {'standalone':standalone_path, 'index':client.get('/api/assistant').json(), 'details':details, 'paths':paths, 'project':project.stem}
    fixtures['creates']=[]
    for title,parent,top_level in [('Peer tab',{'type':'task','id':task.stem},True),
                                   ('Nested in peer',None,False)]:
        if parent is None:
            parent={'type':'note','id':created['metadata']['id']}
        created_response=client.post('/api/assistant/record',json={'type':'subtab','title':title,'parent':parent,'top_level':top_level})
        assert created_response.status_code==200,created_response.text
        created=created_response.json()
        detail_paths=[*details,*(stage['detail']['path'] for stage in fixtures['creates']),created['path']]
        fixtures['creates'].append({'detail':created,'parent':parent,'top_level':top_level,
            'index':client.get('/api/assistant').json(),
            'details':{path:client.get('/api/assistant/'+('task' if path in paths[:2] else 'note'),params={'path':path}).json() for path in detail_paths}})
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
let gate=null, creates=0;
window.prompt=()=>FIX.creates[creates].detail.metadata.title;
window.fetch=async (url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(options.method==='POST'){
  const request=JSON.parse(options.body), stage=FIX.creates[creates++];
  assert(request.type==='subtab'&&request.top_level===stage.top_level,'root plus and Add subtab have distinct placement');
  assert(JSON.stringify(request.parent)===JSON.stringify(stage.parent),'creation uses intended parent regardless of active tab');
  FIX.index=stage.index;FIX.details=stage.details;
  return {ok:true,json:async()=>structuredClone(stage.detail)};
 }
 if(options.method==='PATCH'){
  const change=JSON.parse(options.body), record=FIX.details[change.path];
  assert((record.metadata[change.field]??null)===change.expected,'expected metadata');
  record.metadata[change.field]=change.value;
  return {ok:true,json:async()=>structuredClone(record)};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 if(u.pathname==='/api/workspace-files')return {ok:true,json:async()=>[]};
 if(gate)await gate;
 const record=FIX.details[u.searchParams.get('path')];
 return {ok:!!record,json:async()=>record?structuredClone(record):{detail:'Missing'}};
};
(async()=>{
 AssistantView.init({task:FIX.paths[1]});
 await until(()=>document.querySelectorAll('[data-record-path]').length===3);
 const nav=document.getElementById('assistantDocumentNav');
 assert(nav.querySelector('ul ul ul'),'nested tabs reflect two parent levels');
 const field=name=>document.querySelector(`[data-metadata-field="${name}"]`);
 const host=()=>document.getElementById('assistantModalDocument');
 assert(document.getElementById('assistantModalTitle').textContent==='Child task','child opens with own properties');

 assert(field('status') && field('priority') && field('owner'),'subtabs have lifecycle, priority and POC');
 assert(!field('project')&&!field('workspace'),'subtabs inherit document relationships');
 assert(nav.querySelector('[data-record-index]'),'multiple tabs have Index');
 const previous=host().firstElementChild;
 const contentRow=document.querySelector('[data-assistant-document][data-document-kind="task"]');
 await AssistantView.refresh();
 assert(document.querySelector('[data-assistant-document][data-document-kind="task"]')===contentRow,'identical poll keeps list DOM');
 let release;gate=new Promise(r=>release=r);
 nav.querySelector(`[data-record-path="${FIX.paths[2]}"]`).click();
 await new Promise(r=>setTimeout(r,25));
 assert(host().firstElementChild===previous&&!host().textContent.includes('Loading'),'outgoing tab remains visible while fetching');
 gate=null;release();
 await until(()=>host().textContent.includes('Keep nested notes.'));
 const notePane=host().firstElementChild;
 assert(field('priority')&&field('status'),'discussion is the same subtab concept');
 assert(!host().textContent.includes('Workspace'),'note body contains only content');
 document.querySelector('.assistant-copy-menu').open=true;
 assert(document.getElementById('assistantCopyRich').getBoundingClientRect().height>=36,'comfortable copy target');
 nav.querySelector('[data-record-index]').click();
 await until(()=>host().querySelector('.assistant-index'));
 assert(host().querySelectorAll('[data-index-path]').length===3,'index contains complete nested tree');
 FIX.index.documents.find(row=>row.path===FIX.paths[0]).mtime += 1;
 FIX.details[FIX.paths[0]].tree.mtime = FIX.index.documents.find(row=>row.path===FIX.paths[0]).mtime;
 FIX.details[FIX.paths[0]].tree.children[0].owner='Updated POC';
 FIX.details[FIX.paths[1]].tree=FIX.details[FIX.paths[0]].tree;
 FIX.details[FIX.paths[2]].tree=FIX.details[FIX.paths[0]].tree;
 // Polling a changed file updates the open Index without a navigation reset.
 document.activeElement?.blur();
 await AssistantView.refresh();
 assert(host().textContent.includes('Updated POC'),'Index picks up external metadata updates');
 assert(host().textContent.includes('POC')&&host().textContent.includes('Due'),'index fields');
 host().querySelector(`[data-index-path="${FIX.paths[2]}"] button`).click();
 await until(()=>host().firstElementChild===notePane);
 assert(host().firstElementChild===notePane,'return reuses subtab DOM');
 nav.querySelector(`[data-record-path="${FIX.paths[0]}"]`).click();
 await until(()=>field('project'));
 const project=field('project');project.value=FIX.project;project.dispatchEvent(new Event('change'));
 await until(()=>document.getElementById('assistantModalMetadata').textContent.includes('Saved'));
 assert(FIX.details[FIX.paths[0]].metadata.project===FIX.project,'project is editable on containing task');
 assert(FIX.details[FIX.paths[0]].metadata.workspace==='demo','project change keeps workspace');
 // A later click wins even if an older fetch completes afterward.
 gate=new Promise(r=>release=r);
 nav.querySelector(`[data-record-path="${FIX.paths[2]}"]`).click();
 nav.querySelector('[data-record-index]').click();
 gate=null;release();
 await new Promise(r=>setTimeout(r,25));
 assert(host().querySelector('.assistant-index'),'late fetch cannot replace selected index');
 // + creates a peer of the first tab even while viewing a deep child.
 nav.querySelector(`[data-record-path="${FIX.paths[2]}"]`).click();
 await until(()=>host().textContent.includes('Keep nested notes.'));
 nav.querySelector('[data-record-root-tab]').click();
 await until(()=>document.getElementById('assistantModalTitle').textContent==='Peer tab');
 const peerPath=FIX.creates[0].detail.path;
 const firstTab=nav.querySelector(`[data-record-path="${FIX.paths[0]}"]`);
 const peerTab=nav.querySelector(`[data-record-path="${peerPath}"]`);
 assert(peerTab.closest('li').parentElement===firstTab.closest('li').parentElement,'+ tab is a root peer');
 assert(nav.querySelector(`[data-record-path="${FIX.paths[1]}"]`).closest('li').parentElement!==firstTab.closest('li').parentElement,'existing nested child stays nested');
 nav.querySelector(`[data-record-subtab="${peerPath}"]`).click();
 await until(()=>document.getElementById('assistantModalTitle').textContent==='Nested in peer');
 const nestedPath=FIX.creates[1].detail.path;
 const nestedTab=nav.querySelector(`[data-record-path="${nestedPath}"]`);
 assert(nestedTab.closest('li').parentElement.parentElement===nav.querySelector(`[data-record-path="${peerPath}"]`).closest('li'),'Add subtab nests within chosen peer');
 nav.querySelector('[data-record-index]').click();
 await until(()=>host().querySelector('.assistant-index'));
 assert(host().querySelectorAll('[data-index-path]').length===5,'index includes both root-level and nested tabs');
 const indent=path=>host().querySelector(`[data-index-path="${path}"] button`).style.paddingInlineStart;
 assert(indent(peerPath)===indent(FIX.paths[0]),'Index root peers share indentation');
 assert(indent(nestedPath)==='20px','Index child is one level under its peer');
 host().querySelector(`[data-index-path="${peerPath}"] button`).click();
 await until(()=>document.getElementById('assistantModalTitle').textContent==='Peer tab');
 assert(creates===2,'both creation actions completed');
 AssistantView.closeDocument();AssistantView.setSection('notes');
 await AssistantView.refresh();
 document.querySelector('[data-assistant-view="documents"]').click();
 assert(document.querySelectorAll('[data-assistant-document]').length===1,'only independent notes appear in the list');
 document.querySelector('[data-assistant-document]').click();
 await until(()=>host().textContent.includes('Only this tab.'));
 assert(!nav.querySelector('[data-record-index]'),'single document has no Index');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+ (STATIC / path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','js/views/assistant.js'])
    page=tmp_path/'meetings.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+
                    '</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+
                    '<script>const FIX='+json.dumps(fixtures).replace('</','<\\/')+';\n'+checks+'</script>')
    profile=tmp_path/'chrome-profile'
    process=subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run',
                              '--no-default-browser-check','--allow-file-access-from-files',
                              '--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline=time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline, 'Chrome did not start'
            time.sleep(.05)
        result=subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html')],
                              capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1]=='PASS',result[1] if result else html[-1000:]
