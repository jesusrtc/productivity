"""Series stays visible while navigating an embedded note's tabs."""
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


def test_series_with_document_tabs_browser(client, monkeypatch, tmp_path, monorepo):
    from lab import assistant_records as records, assistant_migration as migration, assistant_documents as documents
    from .test_assistant_routes import _seed
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root,_ = _seed(monkeypatch,tmp_path,monorepo)
    migration.migrate(root,dry_run=False)
    documents.migrate(root,dry_run=False)
    records.add_workspace(root,'other',name='Other')
    series=records.create(root,'note','Weekly 1:1',note_type='series',workspace='demo',body='# Purpose\n\nSeries overview.')
    another=records.create(root,'note','Other series',note_type='series')
    latest=records.create(root,'note','Current meeting',note_type='meeting',workspace='demo',series=series.stem,date='2026-09-14',body='# Summary\n\nCurrent decisions.')
    older=records.create(root,'note','Previous meeting',note_type='meeting',workspace='other',series=series.stem,date='2026-09-07',body='# Summary\n\nEarlier decisions.')
    unrelated=records.create(root,'note','Unrelated meeting',note_type='meeting',series=another.stem,date='2026-09-15')
    standalone=records.create(root,'note','Standalone',note_type='meeting',workspace='demo',date='2026-09-16',body='# Summary\n\nStandalone decisions.')
    child=records.create_subtab(root,'Discussion',parent={'type':'note','id':latest.stem})
    nested=records.create_subtab(root,'Action detail',parent={'type':'note','id':records.resolve(root,str(child.relative_to(root)))[1]['id']})
    peer=records.create_subtab(root,'Preparation',parent={'type':'note','id':latest.stem},top_level=True)
    paths={name:str(path.relative_to(root)) for name,path in [('series',series),('latest',latest),('older',older),('standalone',standalone),('child',child),('nested',nested),('peer',peer)]}
    def get(path,kind):
        response=client.get('/api/assistant/'+kind,params={'path':path})
        assert response.status_code==200,response.text
        return response.json()
    details={path:get(path,'meeting-series' if name=='series' else 'meeting' if name in {'latest','older','standalone'} else 'note') for name,path in paths.items()}
    fixtures={'paths':paths,'details':details,'index':client.get('/api/assistant').json()}
    # Precompute a real metadata-save response without changing the browser's initial snapshot.
    saved=client.patch('/api/assistant/metadata',json={'path':paths['latest'],'field':'series','expected':series.stem,'value':None})
    assert saved.status_code==200,saved.text
    fixtures['detached']=saved.json()
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const nav=()=>document.getElementById('assistantDocumentNav');
const host=()=>document.getElementById('assistantModalDocument');
const rows=()=>[...nav().querySelectorAll('[data-series-document]')];
let gate=null;
window.fetch=async (url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(options.method==='PATCH'){
  const request=JSON.parse(options.body);
  assert(request.field==='series'&&request.value===null,'detach series');
  FIX.details[request.path]=FIX.detached;
  FIX.index.meetings.find(row=>row.path===request.path).series=null;
  FIX.index.meetings.find(row=>row.path===request.path).series_path=null;
  return {ok:true,json:async()=>structuredClone(FIX.detached)};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 if(gate)await gate;
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing'})};
};
(async()=>{
 AssistantView.init({section:'notes'});
 await until(()=>document.querySelector('[data-assistant-meeting]'));
 await AssistantView.openDocument('note',FIX.paths.nested);
 assert(rows().length===2,'full series shown from subtab deep link');
 assert(rows()[0].dataset.seriesDocument===FIX.paths.latest,'newest meeting first');
 assert(rows()[1].dataset.seriesDocument===FIX.paths.older,'series includes notes from another workspace');
 assert(nav().querySelectorAll('.assistant-series-document').length===1,'only active note expands document tabs');
 const active=nav().querySelector('.assistant-series-document');
 assert(active.querySelectorAll('[data-record-path]').length===4,'all current note tabs available');
 assert(active.querySelector('[data-record-index]'),'Index remains available');
 assert(active.querySelector('[data-record-root-tab]'),'plus remains scoped to this document');
 assert(nav().querySelector('[data-record-path].active').dataset.recordPath===FIX.paths.nested,'deep linked subtab selected');
 assert(nav().querySelector('[data-assistant-series]').textContent.includes('Weekly 1:1'),'series title stays visible');
 const rail=nav().firstElementChild;
 const tab=nav().querySelector(`[data-record-path="${FIX.paths.peer}"]`);
 tab.click();await until(()=>tab.classList.contains('active'));
 assert(nav().firstElementChild===rail,'subtab switches preserve series rail DOM');
 const pane=host().firstElementChild;
 await AssistantView.refresh();
 assert(nav().firstElementChild===rail&&host().firstElementChild===pane,'unchanged polls preserve rail and pane');
 // A sibling's metadata can change without touching the current Markdown file.
 FIX.index.meetings.find(row=>row.path===FIX.paths.older).title='Previous meeting renamed';
 await AssistantView.refresh();
 assert(rows()[1].textContent.includes('renamed'),'poll picks up sibling edits');
 assert(host().firstElementChild===pane,'sibling edit keeps current tab content');
 let release;gate=new Promise(r=>release=r);
 rows()[1].click();
 await new Promise(r=>setTimeout(r,25));
 assert(host().firstElementChild===pane,'cross-meeting navigation retains outgoing pane during fetch');
 gate=null;release();
 await until(()=>host().textContent.includes('Earlier decisions.'));
 assert(rows().length===2&&nav().querySelectorAll('[data-record-path]').length===1,'single-tab meeting keeps series and only its own tab');
 assert(!nav().querySelector('[data-record-index]'),'single-tab note has no Index');
 assert(new URL(location).searchParams.get('meeting')===FIX.paths.older,'meeting URL updated');
 nav().querySelector('[data-assistant-series]').click();
 await until(()=>host().textContent.includes('Series overview.'));
 assert(rows().length===2&&!nav().querySelector('.assistant-series-document'),'overview keeps history without expanding a meeting');
 assert(!host().querySelector('[data-series-document],.assistant-series-history'),'history not duplicated in body');
 rows()[0].click();
 await until(()=>host().querySelector('.assistant-index'));
 assert(nav().querySelectorAll('[data-record-path]').length===4,'return to meeting restores document tree');
 const field=document.querySelector('[data-metadata-field="series"]');
 field.value='';field.dispatchEvent(new Event('change'));
 await until(()=>document.getElementById('assistantModalMetadata').textContent.includes('Saved'));
 assert(!nav().querySelector('.assistant-series-overview'),'clearing series removes enclosing rail immediately');
 assert(nav().querySelectorAll('[data-record-path]').length===4,'detaching keeps every document tab');
 await AssistantView.openDocument('meeting',FIX.paths.standalone);
 assert(!nav().querySelector('.assistant-series-overview'),'standalone notes have no series rail');
 assert(host().textContent.includes('Standalone decisions.'),'standalone content intact');
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
