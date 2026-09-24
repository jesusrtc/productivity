"""Confirmed document writes must not repaint stale content or newer editors."""
import json
from pathlib import Path

from .test_frontend_logging import _run_node

APP = (Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js').read_text()
SAVE = APP[APP.index('  async function saveWorkspaceDoc('):APP.index('  async function resolveComment(')]
RENDER = APP[APP.index('  async function _renderDocInto('):APP.index('  // Command+K searches one captured sidebar scope.')]
KEY = APP[APP.index('  function _workspaceDocCacheKey('):APP.index('  // Sidebar payload cache keyed by')]


def _scenarios(*modes):
    return _run_node(r'''
(async()=>{
  const functions=FUNCTIONS;
  async function run(mode) {
    const filepath='docs/review-1.md',root=mode==='worktree'?'/fixture/worktree':'/fixture/alpha',other='/fixture/beta';
    let currentWorkspace={path:'/fixture/alpha'},_workspaceDocRoot=root,_workspaceDocPath=filepath;
    let _workspaceDocContent='Before',_workspaceDocEditing=true,_docModalFilesGeneration=1;
    const comments=[{id:1,file:filepath,text:'quoted',comment:'keep me'}];
    const artifact={file:filepath,url:'https://example.invalid/published'};
    let _workspaceComments=comments,_workspaceDocArtifact=artifact;
    const cached={content:'Before',comments,artifact},beta={content:'Beta',comments:[],artifact:null};
    const _workspaceDocCache=new Map([[root+'|'+filepath,cached],[other+'|'+filepath,beta]]);
    const textarea={value:'Submitted'};let activeEditor=textarea;
    const modal={id:'docModalBody',querySelector:()=>activeEditor};
    let _workspaceDocEditContainer=modal;
    const content={id:'content'};
    const document={getElementById:id=>({content,docModalTitle:{textContent:filepath},workspaceDocEditor:activeEditor}[id])};
    const calls=[],renders=[],alerts=[];
    const alert=message=>alerts.push(message);
    const ensureMarked=async()=>{},ensureHighlight=async()=>{};
    let finishWrite,freshContent='Submitted',freshComments=comments,freshArtifact=artifact;
    const fetch=async(url,options={})=>{
      calls.push({url,method:options.method||'GET',body:options.body&&JSON.parse(options.body)});
      if(options.method==='PUT')return new Promise((resolve,reject)=>{finishWrite=()=>mode==='network-failure'?reject(new Error('Connection lost')):resolve(mode==='failure'?{ok:false,json:async()=>({detail:'Write denied'})}:{ok:true});});
      return {ok:true,json:async()=>url.startsWith('/api/workspace-file?')?{content:freshContent}:url.startsWith('/api/workspace-comments?')?freshComments:{artifacts:freshArtifact?[freshArtifact]:[]}};
    };
    const renderWorkspaceDoc=(path,container)=>renders.push({container:container.id,content:_workspaceDocContent,comments:_workspaceComments,artifact:_workspaceDocArtifact,cache:_workspaceDocCache.get(root+'|'+filepath)?.content});
    const save=eval(functions+'\nsaveWorkspaceDoc');
    if(mode==='missing-cache')_workspaceDocCache.delete(root+'|'+filepath);
    const task=save(filepath);
    if(mode==='fresh-content')freshContent='External edit after save';
    if(mode==='fresh-comments')freshComments=[...comments,{id:2,file:filepath,comment:'New comment'}];
    if(mode==='fresh-artifact')freshArtifact={...artifact,url:'https://example.invalid/new'};
    if(mode==='newer-cache') {
      freshContent='Newer cached edit';
      _workspaceDocCache.set(root+'|'+filepath,{...cached,content:freshContent});
    }
    if(mode==='workspace-switch'){currentWorkspace={path:other};_workspaceDocRoot=other;_workspaceDocContent='Beta';}
    if(mode==='root-switch')_workspaceDocRoot='/fixture/worktree';
    if(mode==='file-switch'){_workspaceDocPath='docs/review-2.md';_workspaceDocContent='Other document';}
    if(mode==='new-draft')textarea.value='Still unsaved';
    if(mode==='closed'){_workspaceDocEditContainer=null;_workspaceDocEditing=false;activeEditor=null;}
    if(mode==='reopened')activeEditor={value:'New editor'};
    finishWrite();await task;
    await new Promise(resolve=>setImmediate(resolve));
    return {calls,renders,alerts,cache:_workspaceDocCache.get(root+'|'+filepath),beta:_workspaceDocCache.get(other+'|'+filepath),editing:_workspaceDocEditing,hasEditor:!!_workspaceDocEditContainer,textarea:textarea.value,content:_workspaceDocContent};
  }
  const result={};for(const mode of MODES)result[mode]=await run(mode);
  process.stdout.write(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('FUNCTIONS', json.dumps(KEY + RENDER + SAVE)).replace('MODES', json.dumps(modes)))


def test_save_publishes_confirmed_content_without_the_stale_inline_render():
    row = _scenarios('normal')['normal']
    assert [(r['container'], r['content']) for r in row['renders']] == [
        ('docModalBody', 'Submitted'), ('content', 'Submitted')]
    assert [call['method'] for call in row['calls']] == ['PUT', 'GET', 'GET', 'GET']
    assert row['calls'][0]['body'] == {'path': '/fixture/alpha', 'file': 'docs/review-1.md', 'content': 'Submitted'}
    assert row['cache']['comments'][0]['comment'] == 'keep me'
    assert row['cache']['artifact']['url'].endswith('/published')
    assert not row['editing'] and not row['hasEditor'] and not row['alerts']


def test_save_keeps_fresh_reconciliation_for_content_comments_and_artifacts():
    rows = _scenarios('fresh-content', 'fresh-comments', 'fresh-artifact', 'missing-cache', 'newer-cache', 'worktree')
    for mode in ('fresh-content', 'fresh-comments', 'fresh-artifact'):
        assert len(rows[mode]['renders']) == 3
        assert rows[mode]['renders'][1]['content'] == 'Submitted'
    assert rows['fresh-content']['renders'][-1]['content'] == 'External edit after save'
    assert rows['fresh-comments']['renders'][-1]['comments'][-1]['id'] == 2
    assert rows['fresh-artifact']['renders'][-1]['artifact']['url'].endswith('/new')
    assert len(rows['missing-cache']['renders']) == 2
    assert rows['missing-cache']['renders'][0].get('cache') is None, 'do not publish an incomplete cache entry'
    assert rows['missing-cache']['cache']['comments'][0]['id'] == 1
    assert rows['newer-cache']['renders'][0]['cache'] == 'Newer cached edit'
    assert rows['newer-cache']['cache']['content'] == 'Newer cached edit'
    assert rows['worktree']['calls'][0]['body']['path'] == '/fixture/worktree'
    assert [r['content'] for r in rows['worktree']['renders']] == ['Submitted', 'Submitted']


def test_delayed_save_preserves_other_workspaces_roots_drafts_and_reopened_editors():
    rows = _scenarios('workspace-switch', 'root-switch', 'file-switch', 'new-draft', 'closed', 'reopened')
    for row in rows.values():
        assert not row['renders']
        assert len(row['calls']) == 1
        assert row['calls'][0]['body']['path'] == '/fixture/alpha'
        assert row['cache']['content'] == 'Submitted'
        assert row['beta']['content'] == 'Beta'
    assert rows['workspace-switch']['content'] == 'Beta'
    assert rows['file-switch']['content'] == 'Other document'
    assert rows['new-draft']['editing'] and rows['new-draft']['hasEditor']
    assert rows['new-draft']['textarea'] == 'Still unsaved'
    assert rows['reopened']['editing'] and rows['reopened']['hasEditor']
    assert not rows['closed']['editing']


def test_failed_write_does_not_publish_or_close_the_editor():
    rows = _scenarios('failure', 'network-failure')
    for row in rows.values():
        assert row['cache']['content'] == 'Before'
        assert row['editing'] and row['hasEditor']
        assert not row['renders'] and len(row['calls']) == 1
    assert rows['failure']['alerts'] == ['Write denied']
    assert rows['network-failure']['alerts'] == ['Error: Connection lost']
