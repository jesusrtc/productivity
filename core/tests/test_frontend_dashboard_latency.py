"""Dashboard reads overlap rendering and cannot overwrite newer navigation."""
import pytest
from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize('background', [False, True])
@pytest.mark.parametrize('outcome', ['success', 'error', 'document', 'workspace'])
def test_dashboard_overlaps_sidebar_and_keeps_latest_owner(outcome, background):
    function = _js_between('  let _workspaceInfoSequence =', '  // ─── Theme + Settings')
    result = _run_node(r'''
let currentWorkspace={path:'/alpha',name:'alpha',is_workspace:true,repos:[]};
let currentRepo=null, _workspaceDocPath=null;
const content={innerHTML:'original',scrollTop:0};
const document={getElementById:()=>content,title:''};
const _setWorkspaceDisplayName=()=>{},workspaceTabsRender=()=>{};
const esc=String,escAttr=String;
const requests=[],errors=[],sidebarOptions=[];
process.on('unhandledRejection',error=>errors.push(String(error)));
let finishSidebar,finishOld,rejectOld, sidebarReady;
const blocked=new Promise(r=>sidebarReady=r);
const sidebarGate=new Promise(r=>finishSidebar=r);
const oldInfo=new Promise((ok,fail)=>{finishOld=ok;rejectOld=fail});
let round=0;
const _refreshWorkspaceSidebar=async options=>{
 round++;sidebarOptions.push(options.backgroundRefresh);
 options._beforeRender();options._beforeRender();
 if(round===1){sidebarReady();await sidebarGate;}
};
const info=title=>({id:'alpha',name:title,status:'active',created:'today',updated:'today'});
const fetch=async url=>{
 requests.push({round,url});
 if(url.includes('/api/workspace-info'))return {json:()=>round===1?oldInfo:Promise.resolve(info('Latest'))};
 if(url.includes('/api/workspace-onepager'))return {json:async()=>({content:''})};
 return {json:async()=>[]};
};
''' + function + r'''
(async()=>{
 const old=showWorkspaceInfo({keepShell:true,backgroundRefresh:BACKGROUND});await blocked;
 const beforeRender=requests.length;
 finishSidebar();await new Promise(r=>setTimeout(r,0));
 const outcome=OUTCOME;
 if(outcome==='document'){_workspaceDocPath='docs/open.md';content.innerHTML='Document';rejectOld(Error('Old failure'));}
 else if(outcome==='workspace'){currentWorkspace={path:'/beta',is_workspace:true};content.innerHTML='Beta';rejectOld(Error('Old failure'));}
 else{
   await showWorkspaceInfo({keepShell:true});
   if(outcome==='error')rejectOld(Error('Old failure'));
   else finishOld(info('Obsolete'));
 }
 await old;await new Promise(r=>setTimeout(r,0));
 console.log(JSON.stringify({sidebarOptions,beforeRender,requests:requests.length,errors,html:content.innerHTML,title:document.title}));
})();
'''.replace('OUTCOME', repr(outcome)).replace('BACKGROUND', str(background).lower()))
    assert result['sidebarOptions'][0] is background
    assert all(option is False for option in result['sidebarOptions'][1:])
    assert result['beforeRender'] == 5  # one batch, even if callback fires twice
    assert result['errors'] == []
    if outcome in {'success', 'error'}:
        assert result['requests'] == 10
        assert 'Latest' in result['html'] and 'Obsolete' not in result['html']
        assert result['title'] == 'Latest'
    else:
        assert result['html'] == ('Document' if outcome == 'document' else 'Beta')
