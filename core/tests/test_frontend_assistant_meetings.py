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
    meeting = {'path':'meeting','metadata':{'title':'Review','date':'2026-09-14','workspace':'demo','series':'weekly','tldr':'Decision agreed.'},'workspace':{'name':'Demo'},
               'tldr':'Decision agreed.','overview':'# Summary\n\nDecision agreed.\n# Action items\n\n- [ ] Real action',
               'notes':'# Notes\n\nSupporting context.', 'raw':{'path':'raw'},
               'contents':[{'path':'answer','title':'Why?','kind':'question'},{'path':'document','title':'Brief','kind':'document'}],
               'series':{**series,'meetings':[older,row]}}
    fixtures = {'raw':raw,'index':{'configured':True,'exists':True,'root':'/fixture','workspaces':[{'id':'demo','name':'Demo'},{'id':'pikaboo','name':'Pikaboo'}],
                                  'tasks':[{'path':'task','title':'Prepare review','workspace':'demo','status':'ready','priority':'P2','recurrence':'monthly','created':'2026-09-14'},
                                           {'path':'other','title':'Build prototype','workspace':'pikaboo','status':'ready','priority':'P1','created':'2026-09-14'}],
                                  'meetings':[older,row],'meeting_series':[series],'statuses':['inbox','ready','done'],'priorities':['P0','P1','P2','P3']},
                'details':{'meeting':meeting,'older':{**meeting,'path':'older','metadata':{'title':'Earlier','date':'2026-09-07'},'tldr':'Earlier decision.','overview':'# Summary\n\nEarlier decision.'},
                           'series':{'path':'series','metadata':{'title':'Weekly'},'body':'# Summary\n\nWeekly purpose.','meetings':[older,row]},
                           'raw':{'path':'raw','format':'text','body':raw},
                           'answer':{'path':'answer','metadata':{'title':'Why?'},'body':'# Answer\n\nBecause.'},
                           'document':{'path':'document','metadata':{'title':'Brief'},'body':'# Brief\n\nDraft text.'},
                           'task':{'path':'task','metadata':{'title':'Prepare review','status':'ready'},'body':'# Context\n\nReview task context. **Formatted text.**\n\n## Detail\n\nNested text.\n\n<details><summary>Hidden details</summary>\n\nPrivate folded text.\n\n</details>\n\n#### Small heading\n\nSmall section.\n\n# Generate content\n\nSend **this**.\n\n# Next section\n\nUnrelated text.',
                                   'subtasks':[{'path':'child','title':'Prepare brief','status':'ready_to_review'}]},
                           'child':{'path':'child','metadata':{'title':'Prepare brief','status':'ready_to_review'},'body':'# Result\n\nChild deliverable.'}}}
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<150;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const host=()=>document.getElementById('assistantModalDocument');
const nav=()=>document.getElementById('assistantDocumentNav');
const part=id=>nav().querySelector(`[data-meeting-part="${id}"]`).click();
let copied='', copiedHtml='', copiedPlain='', copyCount=0, delayed, openedNote;
window.openWorkspaceDocModal=(path,options)=>{openedNote={path,...options}};
Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{copied=text},write:async items=>{
 assert(items[0].types.includes('text/html')&&items[0].types.includes('text/plain'),'rich copy supplies both formats');
 copiedHtml=await (await items[0].getType('text/html')).text();
 copiedPlain=await (await items[0].getType('text/plain')).text();copyCount++;
}}});
let rejectSave=false;
window.fetch=async (url, options={})=>{
 if(options.method==='PATCH'){
   const change=JSON.parse(options.body);
   if(rejectSave)return {ok:false,json:async()=>({detail:'Change rejected'})};
   const record=FIX.details[change.path];
   assert((record.metadata[change.field]??null)===change.expected,'save uses original metadata');
   record.metadata[change.field]=change.value;
   return {ok:true,json:async()=>record};
 }

 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>FIX.index};
 if(u.pathname==='/api/workspace-files')return {ok:true,json:async()=>[
  {path:'notes/Ideas & plans.md',mtime:2}, {path:'journal.txt',mtime:1},
  {path:'projects/demo/tasks/task.md'}, {path:'workspaces/demo/subtasks/child.md'},
  {path:'projects/demo/meetings/meeting.md'}, {path:'workspaces/demo/meeting-series/weekly.md'},
  {path:'AGENTS.md'}, {path:'README.md'}, {path:'.agents/memory/secret.md'},
  {path:'projects/demo/project.md'}, {path:'notes/folder.md',type:'dir'}
 ]};
 const path=u.searchParams.get('path');
 if(path==='delayed')return new Promise(resolve=>{delayed=resolve});
 return {ok:!!FIX.details[path],json:async()=>FIX.details[path]||{detail:'Missing content'}};
};
(async()=>{
 AssistantView.init({section:'tasks'});
 await until(()=>document.querySelector('[data-assistant-task]'));
 assert(AssistantView.section()==='tasks','Assistant opens to Tasks');
 const taskRows=()=>[...document.querySelectorAll('[data-testid="assistant-task-row"]')];
 const filter=(id,value)=>{const el=document.getElementById(id);el.value=value;el.dispatchEvent(new Event('change'))};
 assert(taskRows().length===2,'all workspaces share one task list by default');
 assert(taskRows().some(row=>row.textContent.includes('Pikaboo')),'workspace labels distinguish tasks');
 assert(!document.querySelector('.assistant-lab-workspaces'),'no separate workspace navigation');
 assert(!document.querySelector('.assistant-repeat')&&!taskRows().some(row=>row.textContent.includes('monthly')),'recurrence is absent from the main list');
 filter('assistantWorkspace','pikaboo');
 assert(taskRows().length===1&&taskRows()[0].dataset.assistantTask==='other','workspace filter narrows the same list');
 await AssistantView.refresh();
 assert(document.getElementById('assistantWorkspace').value==='pikaboo'&&taskRows().length===1,'refresh preserves an explicit workspace filter');
 filter('assistantPriority','P2');
 assert(taskRows().length===0,'priority and workspace filters compose');
 filter('assistantWorkspace','');
 assert(taskRows().length===1&&taskRows()[0].dataset.assistantTask==='task','all workspaces retains the other filters');
 filter('assistantPriority','');
 await AssistantView.refresh();
 assert(taskRows().length===2&&document.getElementById('assistantWorkspace').value==='','refresh keeps the combined list');
 assert(!new URL(location).searchParams.has('assistant_workspace'),'clearing the workspace clears its deep-link filter');
 AssistantView.init({task:'task'});
 await until(()=>host()?.textContent.includes('Review task context.'));
 assert(taskRows().length===2,'opening a task deep link does not scope the list to its workspace');
 document.querySelector('.assistant-copy-menu').open=true;
 assert(document.getElementById('assistantCopyRich').getBoundingClientRect().height>=36,'copy buttons have a comfortable target');
 assert(!host().querySelector('.assistant-copy-actions'),'headings have no inline copy controls');
 const heading=text=>[...host().querySelectorAll('h1,h2,h3,h4,h5,h6')].find(h=>h.textContent===text);
 const menu=()=>document.querySelector('.assistant-heading-menu');
 const openMenu=h=>h.dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:innerWidth-1,clientY:innerHeight-1}));
 const context=heading('Context');openMenu(context);
 assert(menu().querySelectorAll('button').length===1&&menu().textContent==='Copy content','one section-copy action');
 const box=menu().getBoundingClientRect();assert(box.right<=innerWidth&&box.bottom<=innerHeight,'menu stays in viewport');
 menu().querySelector('button').click();await until(()=>copyCount===1);
 assert(!menu(),'copy dismisses menu');
 assert(copiedHtml.includes('<strong')&&copiedHtml.includes('Formatted text.')&&copiedHtml.includes('font-family'),'uses Google Docs rich formatting');
 assert(copiedPlain.includes('Context')&&copiedPlain.includes('Nested text.')&&copiedPlain.includes('Small section.'),'copies the clicked heading and nested section');
 assert(!copiedPlain.includes('Unrelated text.')&&!copiedPlain.includes('Generate content')&&!copiedPlain.includes('Private folded text.'),'respects section boundary and closed disclosures');
 const generate=heading('Generate content');openMenu(generate);menu().querySelector('button').click();await until(()=>copyCount===2);
 assert(copiedPlain==='Send this.'&&!copiedHtml.includes('Generate content'),'prepared content keeps its wrapper out');
 const small=heading('Small heading');small.focus();small.dispatchEvent(new KeyboardEvent('keydown',{key:'F10',shiftKey:true,bubbles:true,cancelable:true}));
 assert(menu()&&document.activeElement===menu().querySelector('button'),'heading menu is keyboard accessible');
 menu().dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
 assert(!menu()&&document.activeElement===small&&document.getElementById('assistantDocumentModal').classList.contains('active'),'Escape restores heading focus without closing document');
 openMenu(context);document.body.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}));assert(!menu(),'outside press closes menu');
 openMenu(context);host().dispatchEvent(new Event('scroll'));assert(!menu(),'scroll closes menu');
 openMenu(context);
 AssistantView.closeDocument();
 assert(!menu(),'closing the document removes its menu');
 AssistantView.setSection('notes');
 await until(()=>document.querySelector('[data-assistant-view="other_notes"]'));
 document.querySelector('[data-assistant-view="other_notes"]').click();
 await until(()=>document.querySelectorAll('[data-assistant-note]').length===2);
 assert(document.querySelector('[data-assistant-note]').textContent.includes('Ideas & plans'),'notes safely render names');
 document.querySelector('[data-assistant-note]').click();
 assert(openedNote.path==='notes/Ideas & plans.md'&&openedNote.root==='/fixture','notes open from the Assistant folder');
 assert(!document.getElementById('content').querySelector('[data-assistant-meeting]'),'other notes do not duplicate meeting notes');
 AssistantView.init({section:'meetings'});
 assert(AssistantView.section()==='notes','legacy meeting navigation opens Notes');
 await until(()=>document.querySelectorAll('[data-testid="assistant-meeting-row"]').length===2);
 const groups=[...document.querySelectorAll('[data-assistant-meeting-date]')];
 assert(groups[0].dataset.assistantMeetingDate==='2026-09-14','newest date first');
 assert(groups[0].querySelector('button').textContent.trim()==='Weekly','series name on row');
 groups[0].querySelector('button').click();
 await until(()=>host()?.textContent.includes('Decision agreed.'));
 assert(!host().textContent.includes('Supporting context.'),'summary first');
 assert(!host().querySelector('.assistant-copy-actions'),'note headings also have no inline buttons');
 openMenu(heading('Summary'));menu().querySelector('button').click();await until(()=>copyCount===3);
 assert(copiedPlain.includes('Decision agreed.')&&!copiedPlain.includes('Real action'),'note heading copies only its section');
 assert(!host().querySelector('.assistant-meta,.assistant-document-title,.assistant-detail-badges'),'note body contains content only');
 const metadata=()=>document.getElementById('assistantModalMetadata');
 const field=name=>metadata().querySelector(`[data-metadata-field="${name}"]`);
 const change=async(name,value)=>{const input=field(name);input.value=value;input.dispatchEvent(new Event('change'));await until(()=>metadata().textContent.includes('Saved')&&!field(name).disabled)};
 assert(field('date').type==='date','note date has a native calendar');
 await change('date','2026-09-16');
 assert(FIX.details.meeting.metadata.date==='2026-09-16','note date saved');
 await change('series','');
 metadata().querySelector('details').open=true;
 await change('tldr','Updated summary');
 assert(FIX.details.meeting.metadata.tldr==='Updated summary','summary uses original field, not display fallback');
 metadata().querySelector('details').open=false;
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
 await until(()=>nav().querySelector('.assistant-series-overview.active'));
 assert(nav().querySelectorAll('[data-series-document]').length===2,'complete history stays in the series rail');
 assert(!host().querySelector('.assistant-series-history'),'history is not duplicated in the body');
 nav().querySelector('[data-series-document="older"]').click();
 await until(()=>host().textContent.includes('Earlier decision.'));
 AssistantView.closeDocument();
 assert(!new URL(location).searchParams.has('meeting'),'close clears deep link');
 AssistantView.init({section:'meetings',series:'series'});
 await until(()=>nav().querySelector('.assistant-series-overview.active'));
 assert(document.getElementById('assistantDocumentModal').classList.contains('active'),'series deep link');
 const pending=AssistantView.openDocument('meeting','delayed');await until(()=>delayed);
 AssistantView.closeDocument();delayed({ok:true,json:async()=>FIX.details.meeting});await pending;
 assert(!document.getElementById('assistantDocumentModal').classList.contains('active'),'late result cannot reopen modal');
 await AssistantView.openDocument('meeting','missing');
 assert(host().textContent.includes('Missing content'),'errors visible');
 assert(document.getElementById('assistantCopyPlain').disabled,'errors cannot copy stale content');
 AssistantView.init({section:'tasks',workspace:'demo',task:'task'});
 await until(()=>host().textContent.includes('Review task context.'));
 assert(!host().querySelector('.assistant-meta,.assistant-document-title,.assistant-path'),'task content has no metadata');
 assert(field('due').type==='date','task due has a calendar');
 await change('priority','P1');
 await change('due','2026-10-01');
 await change('recurrence','monthly');
 assert(field('recurrence').selectedOptions[0].textContent==='Monthly','recurrence remains visible in the header');
 await change('recurrence','');
 assert(FIX.details.task.metadata.recurrence===null&&field('recurrence').selectedOptions[0].textContent==='Once','Once clears recurrence');
 assert(FIX.details.task.metadata.priority==='P1'&&FIX.details.task.metadata.due==='2026-10-01','task edits persisted');
 rejectSave=true;
 field('priority').value='P0';field('priority').dispatchEvent(new Event('change'));
 await until(()=>metadata().textContent.includes('Change rejected'));
 assert(field('priority').value==='P1'&&!field('priority').disabled,'failed saves restore the prior value');
 rejectSave=false;
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
