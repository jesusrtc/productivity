"""Edit real API snapshots and see custom dashboard sections react in Chrome."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from lab import assistant_records as records, assistant_dashboard as dashboard
from .test_assistant_documents_unified import library
from .test_frontend_assistant_unified import ROOT, STATIC


def test_custom_attributes_browser(client, library, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root, task, note, content, work, *_ = library
    paths = {name:str(source.relative_to(root)) for name,source in [('note',note),('content',content),('work',work),('task',task)]}
    config = dashboard.read(root)
    template = config['section_template']
    dashboard.write(root,[
        {**template,'id':'rfc','title':'RFCs','position':0,'where':"source = 'active' AND is_RFC = true"},
        {**template,'id':'investigation','title':'Investigations','position':1,'where':'any_tab.is_investigation = true'},
        {**template,'id':'documents','title':'Documents','position':2,'where':"source = 'active'"},
    ],expected=config['revision'])
    def snapshot():
        details = {}
        for path in paths.values():
            response = client.get('/api/assistant/note',params={'path':path})
            assert response.status_code == 200,response.text
            details[path] = response.json()
        return {'index':client.get('/api/assistant').json(),'details':details}
    fixtures = {'paths':paths,**snapshot(),'stages':[]}
    for name,value in [('note',{'is_RFC':True,'is_investigation':False}),
                       ('content',{'is_investigation':True}),('task',{'is_RFC':True}),('note',{})]:
        path = paths[name]
        expected = records.resolve(root,path)[1].get('attributes')
        request = {'path':path,'field':'attributes','value':value,'expected':expected}
        response = client.patch('/api/assistant/metadata',json=request)
        assert response.status_code == 200,response.text
        fixtures['stages'].append({'request':request,'saved':response.json(),**snapshot()})
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<180;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const editor=()=>document.getElementById('assistantAttributesEditor');
const text=()=>document.getElementById('assistantAttributesJson');
const sections=path=>[...document.querySelectorAll(`[data-assistant-document="${path}"]`)].map(row=>row.closest('[data-dashboard-section]').dataset.dashboardSection).sort().join(',');
const openEditor=()=>document.querySelector('[data-edit-attributes]').click();
const set=value=>{text().value=JSON.stringify(value,null,2);text().dispatchEvent(new Event('input'))};
const submit=()=>editor().querySelector('form').requestSubmit();
let mutations=0,conflicts=0;
window.alert=message=>{throw new Error(message)};
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(options.method==='PATCH') {
  if(mutations===FIX.stages.length){conflicts++;return {ok:false,json:async()=>({detail:'This property changed elsewhere. Reload the document.'})};}
  const request=JSON.parse(options.body),stage=FIX.stages[mutations];
  assert(JSON.stringify(request)===JSON.stringify(stage.request),'correct attribute update: '+JSON.stringify(request));
  FIX.index=stage.index;FIX.details=stage.details;mutations++;
  return {ok:true,json:async()=>structuredClone(stage.saved)};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
const save=async(value,count)=>{set(value);submit();await until(()=>mutations===count&&!editor());await AssistantView.refresh()};
const open=async name=>{
 await AssistantView.openDocument(name==='task'?'task':'note',FIX.paths[name]);
 await until(()=>!document.getElementById('assistantDocumentModal').hasAttribute('aria-busy'));
 openEditor();assert(editor().open,'attribute editor opens');
};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>sections(FIX.paths.note)==='documents');
 await open('note');
 assert(Object.keys(JSON.parse(text().value)).length===0,'new attributes start empty');
 set(['bad']);submit();assert(text().getAttribute('aria-invalid')==='true'&&mutations===0,'invalid JSON shape cannot save');
 set({is_RFC:true,is_investigation:false});
 text().focus();text().setSelectionRange(4,4);await AssistantView.refresh();
 assert(document.activeElement===text()&&text().selectionStart===4,'polling preserves editor draft and caret');
 await save({is_RFC:true,is_investigation:false},1);
 assert(sections(FIX.paths.note)==='documents,rfc','note appears in RFCs and Documents');
 assert(document.querySelector('[data-edit-attributes]').textContent.includes('(2)'),'saved attribute count visible');
 openEditor();assert(JSON.parse(text().value).is_RFC===true,'values reopen');
 editor().querySelector('[data-attributes-cancel]').click();await until(()=>!editor());
 document.querySelector(`[data-record-path="${FIX.paths.content}"]`).click();
 await until(()=>document.getElementById('assistantModalTitle').textContent==='Reference');
 openEditor();assert(Object.keys(JSON.parse(text().value)).length===0,'subtab has its own attributes');
 await save({is_investigation:true},2);
 assert(sections(FIX.paths.note)==='documents,investigation,rfc','all matching custom sections include the same note');
 AssistantView.closeDocument();await open('task');
 editor().querySelector('[data-attributes-cancel]').click();await until(()=>!editor());
 document.getElementById('assistantEditNote').click();
 await until(()=>document.querySelector('.assistant-note-editor textarea'));
 const bodyDraft=document.querySelector('.assistant-note-editor textarea');
 bodyDraft.value='My unsaved document draft';bodyDraft.dispatchEvent(new Event('input'));
 openEditor();
 await save({is_RFC:true},3);
 assert(sections(FIX.paths.task)==='documents,rfc','task matches custom condition and remains in Documents');
 assert(document.querySelector('.assistant-note-editor textarea')===bodyDraft&&bodyDraft.value==='My unsaved document draft','saving attributes preserves unsaved document content');
 AssistantView.closeDocument();await open('note');
 await save({},4);
 assert(sections(FIX.paths.note)==='documents,investigation','cleared root leaves RFCs and matches attribute on subtab');
 openEditor();set({is_RFC:true});submit();
 await until(()=>conflicts===1&&document.getElementById('assistantAttributesError').textContent.includes('changed elsewhere'));
 assert(JSON.parse(text().value).is_RFC===true&&!text().disabled,'conflict preserves editable draft');
 assert(mutations===FIX.stages.length,'all intended mutations complete');
 document.getElementById('result').textContent='PASS';
})().catch(error=>document.getElementById('result').textContent='FAIL: '+error.stack);
'''
    scripts = '\n'.join('<script>'+ (STATIC / path).read_text()+'</script>' for path in [
        'vendor/marked@12.0.1/marked.min.js','vendor/dompurify@3.4.15/purify.min.js',
        'js/lib/markdown-content.js','js/views/assistant.js'])
    page = tmp_path/'attributes.html'
    page.write_text('<!doctype html><meta charset="utf-8"><style>'+ (STATIC/'css/lab-shell.css').read_text()+
                    '</style><body class="assistant-active"><div id="repoTabs"></div><div id="content"></div><pre id="result">PENDING</pre>'+scripts+
                    '<script>const FIX='+json.dumps(fixtures).replace('</','<\\/')+';\n'+checks+'</script>')
    profile = tmp_path/'chrome-profile'
    process = subprocess.Popen([chrome,'--headless','--disable-gpu','--no-sandbox','--no-first-run',
                                '--no-default-browser-check','--allow-file-access-from-files',
                                '--user-data-dir='+str(profile),'--remote-debugging-port=0','about:blank'],
                               stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+10
        while not (profile/'DevToolsActivePort').exists():
            assert process.poll() is None and time.monotonic()<deadline,'Chrome did not start'
            time.sleep(.05)
        result = subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'attributes.png')],
                                capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode == 0,result.stderr
        html = (tmp_path/'dom.html').read_text()
    finally:
        process.terminate();process.wait(timeout=5)
    result = re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1] == 'PASS',result[1] if result else html[-1000:]
