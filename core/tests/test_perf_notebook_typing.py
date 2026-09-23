"""Notebook input latency includes its visible overlay and durable browser draft."""
import subprocess
import sys

import pytest

from .test_frontend_logging import _run_node
from .test_perf_document_edit import ROOT


@pytest.mark.parametrize('args,message', [
    (['--notebook-typing'], '--notebook-typing requires --notebook-view'),
    (['--notebook-code-lines', '1'], '--notebook-code-lines requires --notebook-view'),
    (['--notebook-view', '--notebook-code-lines', '-1'], '--notebook-code-lines must be between'),
    (['--notebook-view', '--notebook-code-lines', '2001'], '--notebook-code-lines must be between'),
])
def test_notebook_typing_options_fail_before_starting_server(args, message):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             *args], capture_output=True, text=True)
    assert result.returncode == 2
    assert message in result.stderr


def test_notebook_draft_requires_visible_overlay_editable_cell_and_saved_value():
    result = _run_node(r'''
(async()=>{
  const {notebookDraftReady}=await import('./scripts/perf/notebook_typing_probe.mjs');
  const editor={isConnected:true,readOnly:false},highlight={isConnected:true,textContent:'draft'};
  let saved='draft';global.localStorage={getItem:key=>key==='owned-draft'?saved:null};
  const check=()=>!!notebookDraftReady(editor,highlight,'owned-draft','draft');
  const good=check(),rejected=[];
  for(const [object,key,value] of [[editor,'isConnected',false],[editor,'readOnly',true],
    [highlight,'isConnected',false],[highlight,'textContent','old']]) {
    const old=object[key];object[key]=value;rejected.push(!check());object[key]=old;
  }
  saved='old';rejected.push(!check());saved='draft';
  rejected.push(!notebookDraftReady(editor,highlight,'foreign','draft'));
  console.log(JSON.stringify({good,rejected}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result['good'] and all(result['rejected'])


def test_notebook_typing_refuses_foreign_scope_wrong_cadence_and_tab():
    result = _run_node(r'''
(async()=>{
  const {runNotebookTyping}=await import('./scripts/perf/notebook_typing_probe.mjs');
  const root='/tmp/lab-navigation-owned/vault/workspaces';let calls=0;const errors=[];
  for(const options of [{workspaceRoot:'/vault/workspaces'}, {workspaceRoot:root+'/../workspaces'},
    {target:'foreign'}, {cadenceMs:50}, {text:'x\t'}]) {
    const {target='alpha',text='x',...rest}=options;
    try{await runNotebookTyping({send:()=>calls++},()=>calls++,[],{
      workspaceRoot:root,action:{target,notebookTyping:{before:'original',text}},sample:1,...rest});}
    catch(error){errors.push(error.message);}
  }
  console.log(JSON.stringify({calls,errors}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result['calls'] == 0
    assert result['errors'][:3] == ['Notebook typing requires the disposable fixture'] * 3
    assert 'fixed 25 ms cadence' in result['errors'][3]
    assert 'native Tab' in result['errors'][4]


def test_notebook_typing_keeps_queued_input_and_reports_invalid_clocks():
    result = _run_node(r'''
(async()=>{
  const {runNotebookTyping}=await import('./scripts/perf/notebook_typing_probe.mjs');
  async function run(badClock) {
    const sent=[],pending=[],rows=[];let disposed=false,error=null,updated=false;
    const client={send(method,event){sent.push(event);return new Promise(resolve=>{
      pending.push(resolve);if(sent.length===6)pending.forEach(done=>done({}));
    });}};
    const evaluate=async expression=>{
      if(expression==='__notebookTyping.snapshot()')return {complete:true,valueVerified:true,error:null,
        rows:sent.filter(event=>event.type==='keyDown').map((event,index)=>{
          const epoch=event.timestamp*1000,source=index*25;
          return {index,key:event.key,done:true,ms:20,clock:{source,sourceEpoch:epoch,handlerAt:source+2,
            wallEpoch:epoch+2+(badClock?50:0),wallSampleEnd:source+2}};
        })};
      if(expression.includes('expected.cells[1].source='))updated=true;
      if(expression.includes('.dispose()'))disposed=true;
    };
    let timer;
    try {
      await Promise.race([runNotebookTyping(client,evaluate,rows,{
        workspaceRoot:'/tmp/lab-navigation-owned/vault/workspaces',
        action:{target:'alpha',notebookTyping:{text:'x\ny',before:'original'}},sample:4}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Dispatch waited for acknowledgments')),2000);})]);
    } catch(failure){error=failure.message;} finally{clearTimeout(timer);}
    return {error,disposed,updated,rows,sent:sent.length};
  }
  console.log(JSON.stringify({good:await run(false),bad:await run(true)}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    good, bad = result['good'], result['bad']
    assert good['error'] is None and good['disposed'] and good['updated']
    assert good['sent'] == 6 and len(good['rows']) == 3
    assert all(row['clockCheck']['valid'] for row in good['rows'])
    assert bad['error'] and bad['disposed'] and not bad['updated']
    assert len(bad['rows']) == 3 and all(not row['clockCheck']['valid'] for row in bad['rows'])


def test_notebook_typing_restores_both_final_drafts_and_keeps_disk_expectations():
    result = _run_node(r'''
(async()=>{
  const {mkdtemp,mkdir,writeFile,rm}=await import('node:fs/promises');
  const {tmpdir}=await import('node:os');const {join}=await import('node:path');
  const {notebookViewActions}=await import('./scripts/perf/notebook_view_workload.mjs');
  const dir=await mkdtemp(join(tmpdir(),'lab-navigation-'));const root=join(dir,'vault/workspaces');
  try {
    for(const name of ['alpha','beta']) {
      await mkdir(join(root,name,'notebooks'),{recursive:true});
      const cells=[{id:name+'-cell-0',cell_type:'markdown',source:'heading'},
        {id:name+'-cell-1',cell_type:'code',source:name+' source',outputs:[{text:'output'}]}];
      await writeFile(join(root,name,'notebooks/review.ipynb'),JSON.stringify({cells}));
    }
    const actions=await notebookViewActions(()=>{},root,4,{typing:true});
    const edits=actions.filter(a=>a.notebookTyping),restores=actions.slice(-2);
    const plain=await notebookViewActions(()=>{},root,4);
    console.log(JSON.stringify({count:actions.length,edits:edits.map(a=>({target:a.target,...a.notebookTyping})),
      restores:restores.map(a=>({kind:a.kind,target:a.target,ready:a.ready})),
      unchanged:actions.filter(a=>a.expectedDocuments).every(a=>a.expectedDocuments.length===2
        && a.expectedDocuments.every(([path,raw])=>!raw.includes('fixture draft'))),
      plain:plain.length,plainEdits:plain.some(a=>a.notebookTyping)}));
  } finally {await rm(dir,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result['count'] == 26 and result['plain'] == 24 and not result['plainEdits']
    assert result['unchanged']
    assert [edit['target'] for edit in result['edits']] == ['alpha', 'beta', 'alpha', 'beta']
    for index in [0, 1]:
        assert result['edits'][index + 2]['before'] == (
            result['edits'][index]['before'] + result['edits'][index]['text'])
    assert [row['target'] for row in result['restores']] == ['alpha', 'beta']
    assert all(row['kind'] == 'notebook-draft-restore' and '__notebookViewReady' in row['ready']
               for row in result['restores'])
