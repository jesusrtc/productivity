"""Confirmed Pin writes update warm paint without borrowing another scope."""
import json

import pytest

from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize('pinned', [False, True])
@pytest.mark.parametrize('cached', [False, True])
@pytest.mark.parametrize('change', ['none', 'workspace', 'new-cache'])
def test_pin_publishes_confirmed_state_to_latest_cache(pinned, cached, change):
    toggle = _js_between('  async function togglePin(', '  function showWorkspaceDashboard(')
    result = _run_node(r'''
const pinned = PINNED, cached = CACHED, change = CHANGE;
const name=`docs/name ' " & résumé.md`;
let currentWorkspace={path:'/alpha'};
const payload={files:[{path:'original.md'}],recentFiles:[],pinned:['other.md'],references:[{url:'https://example.test'}],proxies:[],fileRoot:'/alpha'};
const _workspaceSidebarCache=new Map(cached?[['/alpha',payload]]:[]);
const before=JSON.stringify(payload),requests=[],paints=[];
const showWorkspaceInfo=()=>paints.push({path:currentWorkspace.path,pinned:_workspaceSidebarCache.get('/alpha')?.pinned});
let release,reached;
const gate=new Promise(r=>release=r),blocked=new Promise(r=>reached=r);
const fetch=async(url,options)=>{
 requests.push({url,body:options?JSON.parse(options.body):null});
 if(!options)return {ok:true,json:async()=>({id:'alpha',pinned:pinned?['other.md',name]:['other.md'],description:'Keep me'})};
 reached();await gate;return {ok:true};
};
'''.replace('PINNED', str(pinned).lower()).replace('CACHED', str(cached).lower()).replace('CHANGE', repr(change)) + toggle + r'''
(async()=>{
 const pending=togglePin(name);await blocked;
 const beforeConfirmation=JSON.stringify(_workspaceSidebarCache.get('/alpha')||null);
 if(change==='workspace')currentWorkspace={path:'/beta'};
 if(change==='new-cache')_workspaceSidebarCache.set('/alpha',{...payload,files:[{path:'fresh.md'}],fileRoot:'/alpha/new-worktree'});
 release();await pending;
 console.log(JSON.stringify({name,requests,paints,beforeConfirmation,cache:_workspaceSidebarCache.get('/alpha')||null,unchanged:before===JSON.stringify(payload)}));
})();
''')
    expected = ['other.md'] + ([] if pinned else [result['name']])
    assert result['requests'] == [
        {'url': '/api/workspace-info?path=%2Falpha', 'body': None},
        {'url': '/api/workspace-info', 'body': {'path': '/alpha', 'data': {
            'id': 'alpha', 'pinned': expected, 'description': 'Keep me'}}},
    ]
    assert result['unchanged']
    before_confirmation = json.loads(result['beforeConfirmation'])
    assert (before_confirmation['pinned'] if cached else before_confirmation) == (['other.md'] if cached else None)
    if cached or change == 'new-cache':
        assert result['cache']['pinned'] == expected
        assert result['cache']['files'] == [{'path': 'fresh.md' if change == 'new-cache' else 'original.md'}]
        assert result['cache']['fileRoot'] == ('/alpha/new-worktree' if change == 'new-cache' else '/alpha')
        assert result['cache']['references'] == [{'url': 'https://example.test'}]
    else:
        assert result['cache'] is None
    if change == 'workspace':
        assert result['paints'] == []
    else:
        assert result['paints'] == [{'path': '/alpha', **({'pinned': expected} if cached or change == 'new-cache' else {})}]


@pytest.mark.parametrize('failure', ['get-http', 'get-network', 'put-http', 'put-network'])
def test_pin_does_not_publish_failed_write(failure):
    toggle = _js_between('  async function togglePin(', '  function showWorkspaceDashboard(')
    result = _run_node(r'''
let currentWorkspace={path:'/alpha'};
const payload={files:[],pinned:[],fileRoot:'/alpha'},_workspaceSidebarCache=new Map([['/alpha',payload]]);
const requests=[],paints=[];const showWorkspaceInfo=()=>paints.push('paint');
const failure=FAILURE;
const fetch=async(url,options)=>{
 requests.push(url);
 const phase=options?'put':'get';
 if(failure===phase+'-network')throw Error('Offline');
 return {ok:failure!==phase+'-http',json:async()=>({pinned:[]})};
};
'''.replace('FAILURE', repr(failure)) + toggle + r'''
(async()=>{await togglePin('docs/a.md');console.log(JSON.stringify({requests,paints,same:_workspaceSidebarCache.get('/alpha')===payload,pinned:payload.pinned}));})();
''')
    assert len(result['requests']) == (1 if failure.startswith('get') else 2)
    assert result['same'] and result['pinned'] == [] and result['paints'] == []


def test_pin_read_retains_original_write_scope():
    toggle = _js_between('  async function togglePin(', '  function showWorkspaceDashboard(')
    result = _run_node(r'''
let currentWorkspace={path:'/alpha'};
const _workspaceSidebarCache=new Map(),requests=[],paints=[];
const showWorkspaceInfo=()=>paints.push(currentWorkspace.path);
const fetch=async(url,options)=>{
 if(!options){currentWorkspace={path:'/beta'};return {ok:true,json:async()=>({id:'alpha',pinned:[]})};}
 requests.push(JSON.parse(options.body));return {ok:true};
};
''' + toggle + r'''
(async()=>{await togglePin('docs/a.md');console.log(JSON.stringify({requests,paints}));})();
''')
    assert result == {'requests': [{'path': '/alpha', 'data': {'id': 'alpha', 'pinned': ['docs/a.md']}}], 'paints': []}
