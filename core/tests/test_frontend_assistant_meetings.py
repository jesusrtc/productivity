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


def test_meeting_document_browser(tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required for DOM coverage')
    raw = '  Original\r\n# Summary\r\n</pre><img src=x onerror="window.RAW_EXECUTED=true">  \r\n\r\n'
    row = {'id':'meeting','path':'meeting','title':'Review','date':'2026-09-14','workspace':'demo','series_title':'Weekly','series_path':'series'}
    older = {**row,'id':'older','path':'older','date':'2026-09-07'}
    series = {'id':'weekly','path':'series','title':'Weekly','workspace':'demo','latest_date':'2026-09-14','meeting_count':2}
    meeting = {'path':'meeting','metadata':{'title':'Review','date':'2026-09-14'},'workspace':{'name':'Demo'},
               'tldr':'Decision agreed.','overview':'# Summary\n\nDecision agreed.\n# Action items\n\n- [ ] Real action',
               'notes':'# Notes\n\nSupporting context.', 'raw':{'path':'raw'},
               'contents':[{'path':'answer','title':'Why?','kind':'question'},{'path':'document','title':'Brief','kind':'document'}],
               'series':{**series,'meetings':[older,row]}}
    fixtures = {'raw':raw,'index':{'configured':True,'exists':True,'root':'/fixture','workspaces':[{'id':'demo','name':'Demo'}],
                                  'tasks':[{'path':'task','title':'Prepare review','workspace':'demo','status':'ready','created':'2026-09-14'}],
                                  'meetings':[older,row],'meeting_series':[series],'statuses':[],'priorities':[]},
                'details':{'meeting':meeting,'older':{**meeting,'path':'older','metadata':{'title':'Earlier','date':'2026-09-07'},'tldr':'Earlier decision.','overview':'# Summary\n\nEarlier decision.'},
                           'series':{'path':'series','metadata':{'title':'Weekly'},'body':'# Summary\n\nWeekly purpose.','meetings':[older,row]},
                           'raw':{'path':'raw','format':'text','body':raw},
                           'answer':{'path':'answer','metadata':{'title':'Why?'},'body':'# Answer\n\nBecause.'},
                           'document':{'path':'document','metadata':{'title':'Brief'},'body':'# Brief\n\nDraft text.'},
                           'task':{'path':'task','metadata':{'title':'Prepare review','status':'ready'},'body':'# Context\n\nReview task context.',
                                   'subtasks':[{'path':'child','title':'Prepare brief','status':'ready_to_review'}]},
                           'child':{'path':'child','metadata':{'title':'Prepare brief','status':'ready_to_review'},'body':'# Result\n\nChild deliverable.'}}}
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const host=()=>document.getElementById('assistantModalDocument');
const nav=()=>document.getElementById('assistantDocumentNav');
const part=id=>nav().querySelector(`[data-meeting-part="${id}"]`).click();
let copied='', delayed;
Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{copied=text}}});
window.fetch=async url=>{
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>FIX.index};
 if(u.pathname==='/api/workspace-files')return {ok:true,json:async()=>[]};
 const path=u.searchParams.get('path');
 if(path==='delayed')return new Promise(resolve=>{delayed=resolve});
 return {ok:!!FIX.details[path],json:async()=>FIX.details[path]||{detail:'Missing content'}};
};
(async()=>{
 AssistantView.init({section:'meetings'});
 await until(()=>document.querySelectorAll('[data-testid="assistant-meeting-row"]').length===2);
 const groups=[...document.querySelectorAll('[data-assistant-meeting-date]')];
 assert(groups[0].dataset.assistantMeetingDate==='2026-09-14','newest date first');
 assert(groups[0].querySelector('button').textContent.trim()==='Weekly','series name on row');
 groups[0].querySelector('button').click();
 await until(()=>host()?.textContent.includes('Decision agreed.'));
 assert(!host().textContent.includes('Supporting context.'),'summary first');
 assert(nav().textContent.includes('Questions')&&nav().textContent.includes('Documents'),'distinct related content');
 part('raw');await until(()=>host().querySelector('pre'));
 assert(host().querySelector('pre').textContent===FIX.raw,'raw bytes represented verbatim');
 assert(!host().querySelector('img')&&!window.RAW_EXECUTED,'raw inert text');
 assert(document.getElementById('assistantCopyRich').disabled,'no rich conversion of originals');
 document.getElementById('assistantCopyPlain').click();await until(()=>copied===FIX.raw);
 part('answer');await until(()=>host().textContent.includes('Because.'));
 assert(!document.getElementById('assistantCopyRich').disabled,'rich copy restored');
 part('document');await until(()=>host().textContent.includes('Draft text.'));
 part('notes');await until(()=>host().textContent.includes('Supporting context.'));
 nav().querySelector('[data-assistant-series]').click();
 await until(()=>host().querySelector('.assistant-series-history'));
 assert(host().querySelectorAll('[data-assistant-meeting]').length===2,'complete history');
 host().querySelector('[data-assistant-meeting="older"]').click();
 await until(()=>host().textContent.includes('Earlier decision.'));
 AssistantView.closeDocument();
 assert(!new URL(location).searchParams.has('meeting'),'close clears deep link');
 AssistantView.init({section:'meetings',series:'series'});
 await until(()=>host().querySelector('.assistant-series-history'));
 assert(document.getElementById('assistantDocumentModal').classList.contains('active'),'series deep link');
 const pending=AssistantView.openDocument('meeting','delayed');await until(()=>delayed);
 AssistantView.closeDocument();delayed({ok:true,json:async()=>FIX.details.meeting});await pending;
 assert(!document.getElementById('assistantDocumentModal').classList.contains('active'),'late result cannot reopen modal');
 await AssistantView.openDocument('meeting','missing');
 assert(host().textContent.includes('Missing content'),'errors visible');
 assert(document.getElementById('assistantCopyPlain').disabled,'errors cannot copy stale content');
 AssistantView.init({section:'tasks',workspace:'demo',task:'task'});
 await until(()=>host().textContent.includes('Review task context.'));
 assert(document.querySelector('[data-assistant-task-date="2026-09-14"]'),'task list uses recorded creation day');
 nav().querySelector('[data-assistant-modal-document="child"]').click();
 await until(()=>host().textContent.includes('Child deliverable.'));
 nav().querySelector('[data-assistant-modal-document="task"]').click();
 await until(()=>host().textContent.includes('Review task context.'));
 AssistantView.closeDocument();
 AssistantView.setSection('meetings');
 assert(document.getElementById('content').querySelectorAll('[data-assistant-meeting]').length===2,'tasks do not hide meetings');
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
