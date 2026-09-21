"""Browser coverage for dashboard editing and collapsed series history."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from lab import assistant_records as records
from .test_assistant_documents_unified import library

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT/'core/src/core/static'


def test_external_documents_browser(client, library, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    from lab import assistant_storage as storage
    root, _, note, content, work, series, meeting = library
    records.update(root,str(meeting.relative_to(root)),'date','2026-01-01')
    latest = records.create(root,'note','Current meeting',note_type='meeting',series=series.stem,date='2026-01-08')
    paths = {name:str(path.relative_to(root)) for name,path in [('note',note),('tab',content),('series',series),('older',meeting),('latest',latest)]}
    urls = {name:'https://example.com/'+name for name in paths}
    for name,path in paths.items():
        records.update(root,path,'external_url',urls[name])
    records.update(root,note.stem,'starred',True)
    storage.migrate(root,dry_run=False)
    paths = {name:records.resolve(root,path)[0].relative_to(root).as_posix() for name,path in paths.items()}
    details = {path:client.get('/api/assistant/note',params={'path':path}).json() for path in paths.values()}
    fixtures = {'paths':paths,'urls':urls,'details':details,'index':client.get('/api/assistant').json()}
    checks = r'''
const assert=(ok,message)=>{if(!ok)throw new Error(message)};
const until=async fn=>{for(let i=0;i<180;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const list=()=>document.getElementById('content');
const view=name=>list().querySelector(`[data-assistant-view="${name}"]`).click();
const links=host=>[...host.querySelectorAll('a.assistant-external-doc')];
const openPath=async path=>{list().querySelector(`[data-assistant-document="${path}"]`).click();await until(()=>document.querySelector('#assistantDocumentModal.active')&&document.getElementById('assistantModalTitle').textContent===FIX.details[path].metadata.title)};
const opened=[];let saves=0;
window.LAB_EXTERNAL_BROWSER=true; // An SSH client can appear as loopback to the server.
window.open=(...args)=>opened.push(args);
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/ui/open-external')throw new Error('Must never open on server');
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 if(u.pathname==='/api/assistant/metadata'){
  const patch=JSON.parse(options.body),detail=FIX.details[patch.path];
  assert(patch.field==='external_url'&&patch.expected===detail.metadata.external_url,'optimistic external URL save');
  detail.metadata.external_url=patch.value;detail.tree.external_url=patch.value;
  FIX.index.documents.find(row=>row.path===patch.path).external_url=patch.value;
  ++saves;return {ok:true,json:async()=>structuredClone(detail)};
 }
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>list().querySelector('[data-assistant-document]'));
 for(const mode of ['dashboard','all','documents','starred','all_open']){
  view(mode);
  const row=list().querySelector(`[data-assistant-document="${FIX.paths.note}"]`).closest('article');
  const link=links(row)[0];assert(link?.href===FIX.urls.note,'external button in '+mode);
  link.click();assert(opened.at(-1)[0]===FIX.urls.note&&opened.at(-1)[1]==='_blank','client opens link');
  assert(!document.querySelector('#assistantDocumentModal.active'),'link does not open note');
 }
 view('all');
 await openPath(FIX.paths.note);
 const header=()=>document.getElementById('assistantModalMetadata');
 assert(links(header())[0].href===FIX.urls.note,'header button');
 assert(links(document.getElementById('assistantDocumentNav')).some(a=>a.href===FIX.urls.tab),'subtab button');
 assert(links(document.querySelector('.assistant-index')).some(a=>a.href===FIX.urls.tab),'generated Index button');
 const pane=document.getElementById('assistantModalTitle').textContent;
 document.querySelector('.assistant-index a.assistant-external-doc').click();
 assert(document.getElementById('assistantModalTitle').textContent===pane,'Index external click does not select tab');
 const field=()=>header().querySelector('[data-metadata-field="external_url"]');
 field().value='https://example.com/updated';field().dispatchEvent(new Event('change'));
 await until(()=>saves===1&&links(header())[0]?.href==='https://example.com/updated');
 assert(field().value==='https://example.com/updated','edited property reflected');
 field().value='';field().dispatchEvent(new Event('change'));
 await until(()=>saves===2&&!links(header()).length);
 AssistantView.closeDocument();await AssistantView.refresh();
 assert(!links(list().querySelector(`[data-assistant-document="${FIX.paths.note}"]`).closest('article')).length,'clear removes row link');
 const seriesRow=list().querySelector(`[data-assistant-document="${FIX.paths.latest}"]`).closest('article');
 assert(links(seriesRow)[0].href===FIX.urls.latest,'collapsed series links latest note');
 await openPath(FIX.paths.latest);
 const history=document.getElementById('assistantSeriesMenu');
 assert(links(history).some(a=>a.href===FIX.urls.older),'previous meeting retains own link');
 assert(links(document.querySelector('.assistant-series-header')).some(a=>a.href===FIX.urls.series),'series has separate link');
 links(history).find(a=>a.href===FIX.urls.older).click();
 assert(opened.at(-1)[0]===FIX.urls.older,'history opens correct external document');
 AssistantView.closeDocument();view('dashboard');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+ (STATIC / path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/external-links.js','js/lib/markdown-content.js','js/views/assistant.js'])
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
        result=subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'external-documents.png')],
                              capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1]=='PASS',result[1] if result else html[-1000:]
