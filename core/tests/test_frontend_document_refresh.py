"""Background file reads must not invalidate an editor opened while they wait."""
import json
from pathlib import Path

import pytest

from .test_frontend_logging import _run_node

APP = (Path(__file__).resolve().parents[1] / 'src/core/static/js/lab-app.js').read_text()
OPEN = APP[APP.index('  async function openWorkspaceDoc('):APP.index('  // ─── Workspace proxies')]
POLL = APP[APP.index('  // Auto-refresh workspace view when any file in the workspace folder changes'):
           APP.index('  // Sidebar git decorations poll.')]


@pytest.mark.parametrize('mode', ['already-editing', 'edit-during-read', 'error-during-edit', 'read-only', 'explicit-navigation'])
def test_background_document_refresh_preserves_active_editor(mode):
    result = _run_node(r'''
(async()=>{
  const mode=MODE,filepath='docs/review.md',root='/fixture/worktree';
  let currentWorkspace={path:'/fixture/alpha'},_workspaceDocRoot=root,_workspaceDocPath=filepath;
  let _workspaceDocEditing=['already-editing','explicit-navigation'].includes(mode),_workspaceDocContent='Saved source';
  let _contextSubView='document',_workspaceComments=[],_workspaceDocArtifact=null;
  const _workspaceDocCache=new Map(),calls=[],renders=[],effects=[],releases=[];
  const content={id:'content',scrollTop:17,innerHTML:'Original inline document'};
  const textarea={value:'My unsaved draft'},modal={id:'docModalBody'};
  const _workspaceDocEditContainer=modal;
  const document={body:{classList:{contains:()=>false}},getElementById:id=>id==='content'?content:null,querySelectorAll:()=>[]};
  const CSS={escape:value=>value},window={};
  const _clearNbNavigation=()=>effects.push('clear-navigation'),renderRepoTabs=()=>effects.push('tabs');
  const setLastWorkspaceDoc=()=>effects.push('remember'),_sidebarApplyForView=()=>effects.push('sidebar');
  const _workspaceDocCacheKey=(root,path)=>root+'|'+path;
  const _sidebarScopedRoot=()=>root;
  const renderWorkspaceDoc=(path,container)=>renders.push({path,container:container.id,content:_workspaceDocContent});
  const _renderDocInto=async(path,container)=>{_workspaceDocContent='Explicit navigation';renderWorkspaceDoc(path,container);};
  const fetch=url=>{calls.push(url);return new Promise(resolve=>releases.push(()=>resolve({ok:mode!=='error-during-edit',json:async()=>url.startsWith('/api/workspace-file?')?{content:'External source',detail:'Read failed'}:url.startsWith('/api/workspace-comments?')?[{file:filepath,comment:'New comment'}]:{artifacts:[{file:filepath,url:'https://example.invalid/new'}]}})));};
  const open=eval(OPEN+'\nopenWorkspaceDoc');
  const task=open(filepath,{preserveScroll:mode!=='explicit-navigation'});
  if(mode==='edit-during-read'||mode==='error-during-edit')_workspaceDocEditing=true;
  releases.forEach(release=>release());await task;
  process.stdout.write(JSON.stringify({calls,renders,effects,editing:_workspaceDocEditing,content:_workspaceDocContent,inline:content.innerHTML,scroll:content.scrollTop,draft:textarea.value,container:_workspaceDocEditContainer.id,cache:_workspaceDocCache.get(root+'|'+filepath)}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('MODE', json.dumps(mode)).replace('OPEN', json.dumps(OPEN)))
    assert result['draft'] == 'My unsaved draft' and result['container'] == 'docModalBody'
    assert result['scroll'] == 17
    if mode == 'explicit-navigation':
        assert not result['editing']
        assert result['content'] == 'Explicit navigation'
        assert result['renders'] == [{'path': 'docs/review.md', 'container': 'content', 'content': 'Explicit navigation'}]
        assert result['effects'] == ['clear-navigation', 'tabs', 'remember', 'sidebar']
        assert not result['calls']
    elif mode == 'read-only':
        assert not result['editing']
        assert result['content'] == 'External source'
        assert result['renders'] == [{'path': 'docs/review.md', 'container': 'content', 'content': 'External source'}]
    else:
        assert result['editing']
        assert result['content'] == 'Saved source'
        assert result['inline'] == 'Original inline document'
        assert result['renders'] == []
    if mode == 'already-editing':
        assert not result['calls'] and not result['effects']
    elif mode != 'explicit-navigation':
        assert len(result['calls']) == 3
        assert all('path=%2Ffixture%2Fworktree' in url for url in result['calls'])
        if mode != 'error-during-edit':
            assert result['cache']['content'] == 'External source'
            assert result['cache']['comments'][0]['comment'] == 'New comment'


@pytest.mark.parametrize('root', ['/fixture/alpha', '/fixture/worktree'])
def test_mtime_response_after_edit_starts_defers_change_until_editing_ends(root):
    result = _run_node(r'''
(async()=>{
  let tick,currentWorkspace={path:'/fixture/alpha',is_workspace:true},currentRepo=null;
  let _workspaceDocEditing=false,_workspaceDocPath='docs/review.md';
  const root=ROOT,UI_CHECK=false,calls=[],releases=[],refreshes=[];
  const _sidebarScopedRoot=()=>root;
  const document={hidden:false,body:{classList:{contains:()=>false}}};
  const setInterval=callback=>{tick=callback;};
  const fetch=url=>{calls.push(url);return new Promise(resolve=>releases.push(mtime=>resolve({ok:true,json:async()=>({mtime})})));};
  const openWorkspaceDoc=(path,options)=>refreshes.push({kind:'document',path,options});
  const _refreshWorkspaceSidebar=options=>refreshes.push({kind:'sidebar',options});
  const poll=eval(POLL+'\n({tick,baseline:()=>_lastWorkspaceMtime,inFlight:()=>_workspaceMtimeInFlight})');
  let pending=poll.tick();releases.shift()(1);await pending;
  pending=poll.tick();_workspaceDocEditing=true;releases.shift()(2);await pending;
  const during={baseline:poll.baseline(),inFlight:poll.inFlight(),refreshes:refreshes.slice()};
  await poll.tick();const readsDuring=calls.length;
  _workspaceDocEditing=false;pending=poll.tick();releases.shift()(2);await pending;
  process.stdout.write(JSON.stringify({during,readsDuring,calls,refreshes,baseline:poll.baseline(),inFlight:poll.inFlight()}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''.replace('ROOT', json.dumps(root)).replace('POLL', json.dumps(POLL)))
    assert result['during'] == {'baseline': 1, 'inFlight': False, 'refreshes': []}
    assert result['readsDuring'] == 2
    assert len(result['calls']) == 3
    assert result['baseline'] == 2 and not result['inFlight']
    assert result['refreshes'] == [
        {'kind': 'document', 'path': 'docs/review.md', 'options': {'preserveScroll': True}},
        {'kind': 'sidebar', 'options': {'preserveScroll': True, 'backgroundRefresh': True}},
    ]
    from urllib.parse import parse_qs, urlsplit
    assert all(parse_qs(urlsplit(url).query) == {'path': [root], 'include_dotfiles': ['false']}
               for url in result['calls'])
