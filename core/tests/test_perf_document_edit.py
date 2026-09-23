"""The save/cancel probe must preserve exact data and fixture ownership."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

from .test_frontend_logging import _run_node

ROOT = Path(__file__).resolve().parents[2]


def test_document_edit_rejects_nonfixture_scope_before_reading_or_input():
    result = _run_node("""
(async()=>{
  const {documentEditActions}=await import('./scripts/perf/document_edit_workload.mjs');
  const errors=[];
  for(const root of ['/vault/workspaces','/tmp/user/vault/workspaces','/tmp/lab-navigation-owned/workspaces','/tmp/lab-navigation-owned/vault/workspaces/../workspaces']) {
    try{await documentEditActions(root,2);}catch(error){errors.push(error.message);}
  }
  process.stdout.write(JSON.stringify(errors));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    assert result == ['Document editing requires the disposable fixture'] * 4


def test_document_edit_checks_all_files_and_freezes_each_step_expectation():
    result = _run_node("""
(async()=>{
  const {mkdtemp,mkdir,writeFile,readFile,rm}=require('node:fs/promises');
  const {tmpdir}=require('node:os'),{join}=require('node:path');
  const {documentEditActions,verifyEditedDocuments}=await import('./scripts/perf/document_edit_workload.mjs');
  const dir=await mkdtemp(join(tmpdir(),'lab-navigation-'));
  try {
    const root=join(dir,'vault/workspaces'),original=new Map();
    for(const workspace of ['alpha','beta']) {
      await mkdir(join(root,workspace,'docs'),{recursive:true});
      for(const number of [1,2]) {
        const file=join(root,workspace,'docs',`review-${number}.md`),text=`# ${workspace} ${number}\\n\\nLiteral café <tag> & \\"quotes\\"\\n`;
        await writeFile(file,text);original.set(file,text);
      }
    }
    const actions=await documentEditActions(root,4),saves=actions.filter(action=>action.kind==='edit-save');
    const append=await documentEditActions(root,4,{inputMode:'append'}),composed=new Map(original);
    let appendMatches=true;
    for(const action of append.filter(action=>action.input)) {
      const file=join(root,action.target,'docs/review-1.md');
      const text=composed.get(file)+action.input;
      if(action.kind==='edit-save') {
        appendMatches&&=action.inputAppend && text===action.expectedDocuments.find(([path])=>path===file)[1];
        composed.set(file,text);
      } else appendMatches&&=action.inputAppend && action.expectedDocuments.find(([path])=>path===file)[1]===composed.get(file);
    }
    const untouched=[...original].every(([file,text])=>saves[0].expectedDocuments.find(([path])=>path===file)[1]===text || file===join(root,'alpha/docs/review-1.md'));
    // A later Alpha save must not mutate the first expected snapshot.
    const first=saves[0].expectedDocuments.find(([path])=>path===join(root,'alpha/docs/review-1.md'))[1];
    const later=saves[2].expectedDocuments.find(([path])=>path===join(root,'alpha/docs/review-1.md'))[1];
    const before=await verifyEditedDocuments([...original]);
    for(const [file,text] of saves[0].expectedDocuments)await writeFile(file,text);
    const saved=await verifyEditedDocuments(saves[0].expectedDocuments);
    const failures=[];
    for(const file of [join(root,'beta/docs/review-1.md'),join(root,'alpha/docs/review-2.md')]) {
      const originalText=await readFile(file,'utf8');await writeFile(file,originalText+'UNSAVED');
      try{await verifyEditedDocuments(saves[0].expectedDocuments);}catch(error){failures.push(error.message.includes(file));}
      await writeFile(file,originalText);
    }
    process.stdout.write(JSON.stringify({untouched,appendMatches,firstRevision:first.includes('revision 1')&&!first.includes('revision 3'),laterRevision:later.startsWith(first)&&later.includes('revision 3'),before,saved,failures,
      scopes:saves.map(action=>action.target),cancelNeverSaved:actions.filter(action=>action.kind==='edit-cancel').every(action=>action.input.includes('UNSAVED')&&action.expectedDocuments.every(([,text])=>!text.includes('UNSAVED')))}));
  } finally {await rm(dir,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    assert result['untouched'] and result['firstRevision'] and result['laterRevision']
    assert result['appendMatches']
    assert result['before']['files'] == result['saved']['files'] == 4
    assert result['saved']['bytes'] > result['before']['bytes']
    assert result['failures'] == [True, True]
    assert result['scopes'] == ['alpha', 'beta', 'alpha', 'beta']
    assert result['cancelNeverSaved']


@pytest.mark.parametrize('other', ['--typing', '--resize', '--create', '--settings', '--pins', '--terminal-tabs', '--quick-files'])
def test_document_edit_refuses_combined_workflows_before_starting_server(other):
    env = {key: value for key, value in os.environ.items() if key not in ('LAB_VAULT', 'LAB_WORKSPACE')}
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--document-edit', other], env=env, capture_output=True, text=True)
    assert result.returncode == 2
    assert '--document-edit measures a separate workflow' in result.stderr


def test_document_edit_refuses_empty_document_fixture():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--document-edit', '--document-sections', '0'], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--document-sections must be positive' in result.stderr


def test_document_append_requires_its_owned_edit_workflow():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
                             '--document-edit-input', 'append'], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--document-edit-input requires --document-edit' in result.stderr
