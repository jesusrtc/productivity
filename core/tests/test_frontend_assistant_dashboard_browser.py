"""Browser coverage for dashboard editing and collapsed series history."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

import pytest
from lab import assistant_records as records, assistant_query as query
from .test_assistant_documents_unified import library

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT/'core/src/core/static'


def test_dashboard_and_history_browser(client, library, tmp_path):
    chrome = os.environ.get('CHROME_BIN') or shutil.which('chromium') or '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    node = shutil.which('node')
    if not Path(chrome).is_file() or not node:
        pytest.skip('Chrome and Node are required')
    root, _, note, content, work, series, meeting = library
    records.update(root,str(meeting.relative_to(root)),'date','2026-01-01')
    records.update(root,str(meeting.relative_to(root)),'title','Previous meeting')
    records.update(root,str(meeting.relative_to(root)),'starred',True)
    follow_up=records.create_subtab(root,'Follow up',parent={'type':'note','id':meeting.stem},track_task=True)
    records.update(root,str(follow_up.relative_to(root)),'priority','P1')
    latest=records.create(root,'note','Current meeting',note_type='meeting',series=series.stem,date='2026-01-08')
    standalone=records.create(root,'note','Planning session',note_type='meeting',date='2026-01-09')
    paths={name:str(path.relative_to(root)) for name,path in [('latest',latest),('older',meeting),('series',series)]}
    details={path:client.get('/api/assistant/note',params={'path':path}).json() for path in paths.values()}
    fixtures={'paths':paths,'series_id':series.stem,'details':details,'index':client.get('/api/assistant').json()}
    fixtures['queries'] = {row['where']:query.parse(row['where']) for row in fixtures['index']['dashboard']['sections']}
    fixtures['queries'].update({text:query.parse(text) for text in ["kind = 'recurring'", "kind = 'recurring' AND search CONTAINS 'not-a-matching-title'", "source = 'active' AND starred = false"]})
    checks = r'''
const assert=(value,message)=>{if(!value)throw new Error(message)};
const until=async fn=>{for(let i=0;i<180;i++){if(fn())return;await new Promise(r=>setTimeout(r,10));}throw new Error('Timed out: '+fn)};
const list=()=>document.getElementById('content');
const rows=()=>[...list().querySelectorAll('[data-assistant-document]')];
const seriesRows=()=>[...list().querySelectorAll(`[data-document-key="series:${FIX.series_id}"]`)];
const view=name=>list().querySelector(`[data-assistant-view="${name}"]`).click();
const editor=()=>document.getElementById('assistantSectionEditor');
const edit=id=>list().querySelector(`[data-dashboard-edit="${id}"]`).click();
const field=()=>editor().querySelector('textarea');
const change=values=>{field().value=JSON.stringify({...JSON.parse(field().value),...values},null,2)};
const save=async()=>{editor().querySelector('form').requestSubmit();await until(()=>!editor())};
let saves=0;
window.alert=message=>{throw new Error(message)};
window.fetch=async(url,options={})=>{
 const u=new URL(url,'https://lab.example');
 if(u.pathname==='/api/assistant/dashboard'&&options.method==='PUT') {
  const request=JSON.parse(options.body);
  if(request.expected!==FIX.index.dashboard.revision)return {ok:false,json:async()=>({detail:'Dashboard changed elsewhere. Reopen the section editor to load the latest layout.'})};
  if(request.sections.some(row=>row.where==="source = 'invalid'"))return {ok:false,json:async()=>({detail:'Invalid filter source'})};
  FIX.index.dashboard={...FIX.index.dashboard,compiled_filters:Object.fromEntries(request.sections.map(row=>[row.id,FIX.queries[row.where]])),sections:request.sections.sort((a,b)=>a.position-b.position||a.id.localeCompare(b.id)),revision:'saved-'+ ++saves};
  return {ok:true,json:async()=>structuredClone(FIX.index.dashboard)};
 }
 if(u.pathname==='/api/assistant')return {ok:true,json:async()=>structuredClone(FIX.index)};
 const detail=FIX.details[u.searchParams.get('path')];
 return {ok:!!detail,json:async()=>structuredClone(detail||{detail:'Missing record'})};
};
(async()=>{
 AssistantView.init({section:'documents'});
 await until(()=>list().querySelectorAll('[data-dashboard-section]').length===3);
 assert(seriesRows().length===3&&new Set(seriesRows().map(row=>row.closest('[data-dashboard-section]').dataset.dashboardSection)).size===3,'series appears once in each matching section');
 assert(list().querySelector('.assistant-filter-count').textContent===new Set(rows().map(row=>row.dataset.assistantDocument)).size+' items','dashboard count does not double-count copies');
 assert(seriesRows()[0].querySelector('[data-assistant-document]').dataset.assistantDocument===FIX.paths.latest,'series opens latest even when older work matches Priority');
 assert(seriesRows()[0].closest('[data-dashboard-section]').dataset.dashboardSection==='priority','old pending action surfaces series in priority');
 assert(list().querySelector('[data-document-icon="note"]')&&list().querySelector('[data-document-icon="meeting"]')&&list().querySelector('[data-document-icon="recurring"]'),'distinct note, meeting and recurring icons');
 const groupStars=seriesRows().map(row=>row.querySelector('[data-series-stars]'));
 assert(new Set(groupStars.map(button=>button.getAttribute('popovertarget'))).size===3,'each series copy has its own star menu');
 for(const button of groupStars){
  button.click();const menu=document.getElementById(button.getAttribute('popovertarget'));
  assert(menu.matches(':popover-open')&&menu.closest('[data-dashboard-section]')===button.closest('[data-dashboard-section]'),'star menu belongs to the clicked section');
  assert(button.getAttribute('aria-expanded')==='true'&&groupStars.filter(other=>other!==button).every(other=>other.getAttribute('aria-expanded')==='false'),'only clicked star control expands');
  menu.hidePopover();
 }
 const groupStar=groupStars.at(-1);
 assert(groupStar.classList.contains('is-starred')&&groupStar.dataset.groupStarred==='true','older starred note fills collapsed row star');
 groupStar.click();const starMenu=document.getElementById(groupStar.getAttribute('popovertarget'));
 assert(starMenu.matches(':popover-open'),'group star opens explicit controls');
 assert(starMenu.querySelector(`[data-star-path="${FIX.paths.series}"]`).getAttribute('aria-pressed')==='false','series remains independently unstarred');
 assert(starMenu.querySelector(`[data-star-path="${FIX.paths.latest}"]`).getAttribute('aria-pressed')==='false','latest note remains independently unstarred');
 starMenu.querySelector('[data-starred-notes]').click();
 await until(()=>document.getElementById('assistantSeriesMenu')?.matches(':popover-open'));
 assert(document.getElementById('assistantSeriesFilter').value==='starred','find starred notes through existing history filter');
 assert(document.querySelectorAll('#assistantSeriesMenu li:not([hidden]) [data-series-document]').length===1,'only actually starred older note appears');
 AssistantView.closeDocument();
 const original=rows()[0];await AssistantView.refresh();assert(rows()[0]===original,'unchanged polling preserves rows');
 assert(!list().querySelector('[data-dashboard-move]')&&[...list().querySelectorAll('[data-dashboard-edit]')].every(button=>button.textContent==='Show filter'),'Show filter is the only section header action');
 edit('priority');assert(!editor().querySelector('input,select'),'JSON replaces form fields');
 assert(Object.keys(JSON.parse(field().value)).length===Object.keys(FIX.index.dashboard.section_template).length,'complete section configuration shown');
 change({title:'My draft'});const draft=field().value;field().focus();field().setSelectionRange(2,4);
 await AssistantView.refresh();assert(field().value===draft&&document.activeElement===field()&&field().selectionStart===2,'poll leaves editor draft and selection intact');
 editor().querySelector('[data-section-cancel]').click();await until(()=>!editor());assert(saves===0,'cancel does not save');
 edit('priority');const valid=field().value;field().value='{ invalid';editor().querySelector('form').requestSubmit();
 assert(editor().querySelector('[role="alert"]').textContent.includes('Invalid JSON')&&saves===0,'invalid syntax cannot save');
 field().value=valid;change({where:"source = 'invalid'"});editor().querySelector('form').requestSubmit();
 await until(()=>editor().querySelector('[role="alert"]').textContent.includes('Invalid filter source'));
 assert(JSON.parse(field().value).where==="source = 'invalid'"&&saves===0,'server validation preserves JSON draft');
 field().value=valid;change({title:'Focus'});await save();
 assert(list().querySelector('[data-dashboard-section="priority"] h2').textContent.includes('Focus'),'renamed section');
 list().querySelector('[data-dashboard-add]').click();change({title:'Team meetings',where:"kind = 'recurring'"});await save();
 const added=FIX.index.dashboard.sections.at(-1).id;
 assert(FIX.index.dashboard.sections.length===4&&FIX.index.dashboard.sections.at(-1).where==="kind = 'recurring'",'custom filters persisted');
 edit(added);change({position:-10});await save();
 assert(list().querySelector('[data-dashboard-section]').dataset.dashboardSection===added,'reorder persists');
 assert(seriesRows().length===4&&seriesRows()[0].closest('[data-dashboard-section]').dataset.dashboardSection===added,'reordering changes position while all matching sections retain the series');
 AssistantView.init({section:'documents'});await AssistantView.refresh();assert(list().querySelector('[data-dashboard-section]').dataset.dashboardSection===added,'re-entry restores saved layout');
 edit(added);change({where:"kind = 'recurring' AND search CONTAINS 'not-a-matching-title'"});await save();
 assert(list().querySelector(`[data-dashboard-section="${added}"] .assistant-empty`),'edit changes results');
 edit(added);editor().querySelector('[data-section-remove]').click();await until(()=>!editor());assert(FIX.index.dashboard.sections.length===3,'remove section');
 edit('documents');change({where:"source = 'active' AND starred = false"});await save();
 assert(seriesRows().length===2&&seriesRows().every(row=>row.closest('[data-dashboard-section]').dataset.dashboardSection!=='documents'),'only an explicit exclusion removes the starred series from Documents');
 edit('documents');change({where:"source = 'active'"});await save();
 assert(seriesRows().length===3,'removing exclusion restores independent Documents membership');
 edit('priority');change({title:'Unsaved conflict'});FIX.index.dashboard.revision='external';editor().querySelector('form').requestSubmit();
 await until(()=>editor().querySelector('[role="alert"]').textContent.includes('changed elsewhere'));
 assert(JSON.parse(field().value).title==='Unsaved conflict','conflict retains draft');editor().querySelector('[data-section-cancel]').click();await until(()=>!editor());await AssistantView.refresh();
 for(const name of ['all','meetings','meeting_series','starred','all_open']){view(name);assert(seriesRows().length===1,'one series in '+name);assert(seriesRows()[0].querySelector('[data-assistant-document]').dataset.assistantDocument===FIX.paths.latest,'latest in '+name);}
 seriesRows()[0].querySelector('[data-assistant-document]').click();await until(()=>document.getElementById('assistantModalTitle').textContent==='Current meeting'&&!document.getElementById('assistantDocumentModal').hasAttribute('aria-busy'));
 const nav=()=>document.getElementById('assistantDocumentNav');
 const menu=()=>document.getElementById('assistantSeriesMenu');
 const visible=()=>[...menu().querySelectorAll('li:not([hidden]) [data-series-document]')];
 const search=()=>document.getElementById('assistantSeriesSearch');
 nav().querySelector('[data-series-toggle]').click();search().value='2026-01-01';search().dispatchEvent(new Event('input'));search().focus();search().setSelectionRange(0,4);
 assert(visible().length===1&&visible()[0].dataset.seriesDocument===FIX.paths.older,'date search finds previous meeting');
 FIX.index.documents.find(row=>row.path===FIX.paths.older).title='Previous renamed';await AssistantView.refresh();
 assert(search().value==='2026-01-01'&&document.activeElement===search()&&search().selectionStart===0,'sibling update keeps search and focus: '+JSON.stringify({query:search().value,focus:document.activeElement.id,start:search().selectionStart,open:menu().matches(':popover-open')}));
 search().value='nothing';search().dispatchEvent(new Event('input'));assert(visible().length===0&&!menu().querySelector('[data-series-empty]').hidden,'empty filter state');
 search().value='';search().dispatchEvent(new Event('input'));
 const filter=document.getElementById('assistantSeriesFilter');filter.value='starred';filter.dispatchEvent(new Event('change'));
 assert(visible().length===1&&visible()[0].dataset.seriesDocument===FIX.paths.older,'star filter finds independently starred older note');
 filter.value='open';filter.dispatchEvent(new Event('change'));assert(visible().length===1,'open work filter');
 visible()[0].click();await until(()=>document.getElementById('assistantModalTitle').textContent==='Previous meeting');
 assert(!menu().matches(':popover-open'),'date selection returns to document');
 AssistantView.closeDocument();view('dashboard');
 assert(seriesRows().length===3&&new Set(seriesRows().map(row=>row.closest('[data-dashboard-section]').dataset.dashboardSection)).size===3,'old selection does not duplicate a series within a section');
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
        result=subprocess.run([node,str(ROOT/'scripts/chrome-dump-auth.mjs'),str(profile),page.as_uri(),str(tmp_path/'dom.html'),str(tmp_path/'dashboard.png')],
                              capture_output=True,text=True,timeout=25,env={**os.environ,'LAB_UI_AUTH_COOKIE':''})
        assert result.returncode==0,result.stderr
        html=(tmp_path/'dom.html').read_text()
    finally:
        process.terminate()
        process.wait(timeout=5)
    result=re.search(r'<pre id="result">(.*?)</pre>',html,re.S)
    assert result and result[1]=='PASS',result[1] if result else html[-1000:]
