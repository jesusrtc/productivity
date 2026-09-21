"""Exercise shared library views, task completion, labels, and independent stars."""
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


def test_unified_library_browser(client, library, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root, _, note, content, work, series, meeting = library
    task = records.create(root,'task','Call manager')
    paths = {name:str(source.relative_to(root)) for name,source in [('note',note),('content',content),('work',work),('series',series),('meeting',meeting),('task',task)]}
    def snapshot():
        index = client.get('/api/assistant').json()
        details = {}
        for path in paths.values():
            meta = records.resolve(root,path)[1]
            kind = {'series':'meeting-series','meeting':'meeting'}.get(meta.get('note_type'),'note')
            response = client.get('/api/assistant/'+kind,params={'path':path})
            assert response.status_code==200,response.text
            details[path]=response.json()
        return {'index':index,'details':details}
    fixtures={'paths':paths,**snapshot(),'stages':[]}
    for name,field,value in [('note','starred',True),('note','starred',False),('series','starred',True),('meeting','starred',True),('series','starred',False),
                              ('note','note_type','meeting'),('content','track_task',True),('content','track_task',False),
                              ('work','status','done'),('task','status','done'),('task','keep_in_documents',True),('task','track_task',False)]:
        path=paths[name]
        expected=records.resolve(root,path)[1].get(field)
        request={'path':path,'field':field,'value':value,'expected':expected}
        response=client.patch('/api/assistant/metadata',json=request)
        assert response.status_code==200,response.text
        fixtures['stages'].append({'request':request,'saved':response.json(),**snapshot()})
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<180;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const field=name=>document.querySelector(`[data-metadata-field="${name}"]`);
const title=()=>document.getElementById('assistantModalTitle').textContent;
const list=()=>document.getElementById('content');
const rows=()=>[...list().querySelectorAll('[data-assistant-document]')];
const paths=()=>rows().map(row=>row.dataset.assistantDocument);
const view=name=>list().querySelector(`[data-assistant-view="${name}"]`).click();
const nav=()=>document.getElementById('assistantDocumentNav');
const tab=path=>nav().querySelector(`[data-record-path="${path}"]`);
let mutations=0;
window.alert=message=>{throw new Error(message)};
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(options.method==='PATCH') {
  const request=JSON.parse(options.body),stage=FIX.stages[mutations];
  assert(stage&&JSON.stringify(request)===JSON.stringify(stage.request),'correct independent property update: '+JSON.stringify(request));
  FIX.index=stage.index; FIX.details=stage.details; mutations++;
  return {ok:true,json:async()=>structuredClone(stage.saved)};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
const change=async(name,value,number)=>{
 const control=field(name);
 if(control.type==='checkbox')control.checked=value;else control.value=value;
 control.dispatchEvent(new Event('change'));
 await until(()=>mutations===number&&document.getElementById('assistantModalMetadata').textContent.includes('Saved'));
 await AssistantView.refresh();
};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>new Set(paths()).size===4);
 const sectionsFor=path=>[...list().querySelectorAll(`[data-assistant-document="${path}"]`)].map(row=>row.closest('[data-dashboard-section]').dataset.dashboardSection).sort();
 assert(JSON.stringify(sectionsFor(FIX.paths.note))==='["documents"]','ordinary note starts in Documents');
 list().querySelector(`[data-star-path="${FIX.paths.note}"]`).click();
 await until(()=>mutations===1);await AssistantView.refresh();
 assert(JSON.stringify(sectionsFor(FIX.paths.note))==='["documents","starred"]','starring adds Starred while retaining Documents');
 assert([...list().querySelectorAll(`[data-star-path="${FIX.paths.note}"]`)].every(button=>button.getAttribute('aria-pressed')==='true'),'every copy reflects the saved star');
 list().querySelector(`[data-dashboard-section="documents"] [data-star-path="${FIX.paths.note}"]`).click();
 await until(()=>mutations===2);await AssistantView.refresh();
 assert(JSON.stringify(sectionsFor(FIX.paths.note))==='["documents"]','unstar removes only the Starred copy');
 view('all');
 assert(paths().includes(FIX.paths.task)&&paths().includes(FIX.paths.note)&&paths().includes(FIX.paths.meeting),'existing tasks and notes in one list');
 const original=rows()[0];await AssistantView.refresh();assert(rows()[0]===original,'unchanged polling preserves rows');
 list().querySelector(`[data-star-path="${FIX.paths.series}"]`).click();
 await until(()=>mutations===3);await AssistantView.refresh();view('starred');
 assert(paths().length===1&&paths()[0]===FIX.paths.meeting,'series star adds one series, not every meeting');
 await AssistantView.openDocument('meeting',FIX.paths.meeting);
 document.querySelector('#assistantModalMetadata [data-star-path]').click();
 await until(()=>mutations===4);await AssistantView.refresh();
 nav().querySelector('[data-star-path]').click();
 await until(()=>mutations===5);await AssistantView.refresh();AssistantView.closeDocument();
 assert(paths().length===1&&paths()[0]===FIX.paths.meeting,'unstar series retains independently starred note');
 view('documents');assert(!paths().includes(FIX.paths.task),'transient task is not in document library');
 await AssistantView.openDocument('note',FIX.paths.note);
 assert(field('status')&&field('status').value==='not_started','work is reflected on containing document');
 await change('note_type','meeting',6);
 assert(nav().querySelectorAll('[data-record-path]').length===3,'label change preserves all tabs');
 tab(FIX.paths.content).click();await until(()=>title()==='Reference');
 assert(!field('status')&&!field('track_task').checked,'reference tab has no status');
 await change('track_task',true,7);assert(field('status'),'tab can become a task');
 await change('track_task',false,8);assert(!field('status'),'tab can return to content without erasing it');
 tab(FIX.paths.work).click();await until(()=>title()==='Review guide');
 await change('status','done',9);AssistantView.closeDocument();view('all_open');
 assert(!paths().includes(FIX.paths.note),'finished document leaves open tasks');
 view('documents');assert(paths().includes(FIX.paths.note),'finished guide stays in library');
 view('meetings');assert(paths().includes(FIX.paths.note)&&paths().includes(FIX.paths.meeting),'meeting label filters document roots');
 await AssistantView.openDocument('task',FIX.paths.task);
 assert(!document.getElementById('assistantEditNote').hidden,'task can hold an editable resulting document');
 await change('status','done',10);AssistantView.closeDocument();view('all');
 assert(!paths().includes(FIX.paths.task),'completed transient task leaves active collection');
 view('recent');assert(paths().includes(FIX.paths.task),'completed transient task remains in history');
 await AssistantView.openDocument('task',FIX.paths.task);
 await change('keep_in_documents',true,11);
 await change('track_task',false,12);AssistantView.closeDocument();view('documents');
 assert(paths().includes(FIX.paths.task),'keep toggle converts task content into retained document in place');
 assert(FIX.details[FIX.paths.task].metadata.status==='done','conversion retains completed task history');
 assert(mutations===FIX.stages.length,'all actions completed');
 view('starred');
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
        result=subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'unified.png')],
                              capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1]=='PASS',result[1] if result else html[-1000:]
