"""Keep notebook latency measurements scoped and fully rendered."""
import subprocess
import sys

import pytest

from .test_frontend_logging import _run_node
from .test_perf_document_edit import ROOT


def test_notebook_probe_rejects_foreign_scope_before_reading_or_evaluating():
    result = _run_node(r'''
(async()=>{
  const {notebookViewActions}=await import('./scripts/perf/notebook_view_workload.mjs');
  const errors=[];
  for(const root of ['/vault/workspaces','/tmp/user/vault/workspaces','/tmp/lab-navigation-owned/workspaces','/tmp/lab-navigation-owned/vault/workspaces/../workspaces']) {
    try{await notebookViewActions(()=>{throw Error('Unexpected browser access');},root,2);}
    catch(error){errors.push(error.message);}
  }
  console.log(JSON.stringify(errors));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result == ['Notebook viewing requires the disposable fixture'] * 4


def test_notebook_readiness_checks_every_cell_source_output_and_control():
    result = _run_node(r'''
(async()=>{
  const {notebookViewReady}=await import('./scripts/perf/notebook_view_workload.mjs');
  global.currentWorkspace={path:'/fixture/alpha'};global._workspaceDocRoot=currentWorkspace.path;
  global._workspaceDocPath='notebooks/review.ipynb';
  const expected={scope:currentWorkspace.path,cells:[
    {id:'md',cell_type:'markdown',heading:'Heading',paragraph:'Paragraph'},
    {id:'code',cell_type:'code',source:'print(1)',output:'1\n'},
    {id:'last',cell_type:'code',source:'print(2)',output:'2\n'},
  ]};
  let hidden=false,collapsed=false,pressed='false';
  const states=expected.cells.map((cell,index)=>({
    dataset:{cellId:cell.id,cellIndex:String(index),cellType:cell.cell_type},
    delete:{},editor:{value:cell.source,readOnly:false},run:{disabled:false},
    highlight:{textContent:cell.source},heading:{firstChild:{textContent:cell.heading}},
    paragraph:{textContent:cell.paragraph},body:{textContent:cell.output},
  }));
  const cells=states.map((s,index)=>({dataset:s.dataset,querySelector:selector=>({
    '.nb-cell-del':s.delete,'.nb-cell-edit-area':s.editor,'.nb-cell-run':s.run,
    '.nb-cell-edit-highlight code':s.highlight,'.nb-markdown h2':s.heading,'.nb-markdown p':s.paragraph,
    ':scope > .nb-outputs':{querySelector:()=>s.body,classList:{contains:()=>index===1&&collapsed}},
  })[selector]}));
  global.document={getElementById:()=>({querySelector:selector=>selector==='.nb-container'
    ?{classList:{contains:()=>hidden},querySelectorAll:()=>cells}
    :{getAttribute:()=>pressed}})};
  const valid=!!notebookViewReady(expected),failures=[];
  for(const [object,key,bad] of [
    [currentWorkspace,'path','/fixture/beta'],[states[2].dataset,'cellId','wrong'],
    [states[2].dataset,'cellIndex','1'],[states[2].dataset,'cellType','markdown'],
    [states[0].heading.firstChild,'textContent','wrong'],[states[0].paragraph,'textContent','wrong'],
    [states[2].editor,'value','wrong'],[states[2].editor,'readOnly',true],
    [states[2].run,'disabled',true],[states[2],'run',null],[states[2],'delete',null],
    [states[2].highlight,'textContent','wrong'],[states[2].body,'textContent','wrong'],
  ]) {
    const original=object[key];object[key]=bad;failures.push(!notebookViewReady(expected));object[key]=original;
  }
  hidden=true;pressed='true';const hiddenValid=!!notebookViewReady(expected,{codeHidden:true});
  const hiddenRejected=!notebookViewReady(expected);hidden=false;pressed='false';
  collapsed=true;const collapseValid=!!notebookViewReady(expected,{collapsed:true});
  const collapseRejected=!notebookViewReady(expected);
  console.log(JSON.stringify({valid,failures,hiddenValid,hiddenRejected,collapseValid,collapseRejected}));
})().catch(error=>{console.error(error);process.exitCode=1;});
''')
    assert result['valid'] and all(result['failures'])
    assert result['hiddenValid'] and result['hiddenRejected']
    assert result['collapseValid'] and result['collapseRejected']


@pytest.mark.parametrize('other', ['--typing', '--resize', '--create', '--settings', '--pins', '--terminal-tabs', '--quick-files', '--document-edit'])
def test_notebook_view_rejects_other_workflows_before_server_start(other):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--notebook-view', other], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--notebook-view measures a separate workflow' in result.stderr


@pytest.mark.parametrize('cells', ['0', '1', '2001'])
def test_notebook_view_requires_bounded_complete_fixture(cells):
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--notebook-view', '--notebook-cells', cells], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--notebook-cells must be between 2 and 2000' in result.stderr
