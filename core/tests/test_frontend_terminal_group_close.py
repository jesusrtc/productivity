"""Deleting a parent confirms and removes its complete terminal family."""
import json

import pytest

from .test_frontend_terminal_subtabs import GROUPS
from .test_frontend_terminal_ui import _js_between, _run_node


@pytest.mark.parametrize('mode', ['confirm', 'cancel', 'current', 'merged', 'navigate', 'child', 'failure', 'shared', 'selected', 'inherited'])
def test_parent_close_includes_nested_children_and_preserves_other_groups(mode):
    setup = r'''
const mode=MODE,_TERM_GROUPS_KEY='groups',_TERM_GROUP_COLORS=['#58a6ff'];
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
let vault='one',termCurrentSession=mode==='current'?'parent':'nested',termCurrentWorkspaceId='demo';
let termSessions=['parent','child','nested','sibling','outside','foreign'].map(name=>({name,logical_name:name,label:name,objective:name==='foreign'?'other':'one'}));
if(mode==='shared')termSessions[2].document_source={workspace_id:'source'};
const original=[...termSessions],_termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>vault;
const _termSessionsKey=(id,v)=>v+'::'+id,_vaultQuery=v=>'&vault='+v;
const termSessEsc=String,_termSessionDisplay=s=>s.label,_termSessionMeta=name=>termSessions.find(s=>s.name===name);
const calls=[],questions=[],alerts=[],toasts=[];
const confirm=question=>{questions.push(question);return mode!=='cancel';},alert=message=>alerts.push(message),explorerToast=message=>toasts.push(message);
const _termSessionsCache=new Map(),_termEvictCache=name=>calls.push(['evict',name]);
const termDetach=()=>{calls.push(['detach',termCurrentSession]);termCurrentSession=null;};
const termAttach=name=>{calls.push(['attach',name]);termCurrentSession=name;};
const termShowEmpty=()=>{},termSetStatus=()=>{},termRenderSessionList=()=>{};
const removed=new Set();
const _termRefreshSessionsForWorkspaceId=async()=>{calls.push(['refresh']);termSessions=termSessions.filter(row=>!removed.has(row.name));};
window.LabObjectives={sameTerminalObjective:(a,b)=>a.objective===b.objective};
if(mode==='inherited')window.LabObjectives.terminalParents=()=>({child:'parent',nested:'child',sibling:'parent'});
const fetch=async(url,options)=>{
 calls.push([options.method,url]);
 const name=decodeURIComponent(url.split('/').pop().split('?')[0]);
 const ok=!(mode==='failure'&&name==='nested');
 if(options.method==='DELETE'&&ok)removed.add(name);
 if(options.method==='DELETE'&&mode==='navigate')vault='two';
 return{ok,json:async()=>({detail:'sample failure'})};
};
'''.replace('MODE', json.dumps(mode))
    body = r'''
const state=_termNormalizeGroupState({order:termSessions.map(row=>'s:'+row.name),
 tabParents:{child:'parent',nested:'child',sibling:'parent',foreign:'parent'},
 tabExpanded:{parent:true,child:true,outside:true},tabMembership:{parent:'dev',child:'dev',outside:'dev'},
 tabGroups:[{id:'dev',name:'Development'}],tabAfter:{outside:'parent'}});
if(mode==='merged'){state.tabDisplayMains={parent:'child'};state.tabDisplayMainVersion=2;termCurrentSession='child';}
_termWriteGroupState(state);const before=JSON.stringify(stored);
(async()=>{
 const ok=mode==='current'||mode==='merged'?await termKillCurrent():await termCloseTabs(mode==='selected'?['parent','child']: [mode==='child'?'child':'parent']);
 console.log(JSON.stringify({ok,calls,questions,alerts,toasts,removed:[...removed],
  saved:_termReadGroupState('one::demo'),other:_termReadGroupState('two::demo'),
  unchanged:before===JSON.stringify(stored),pending:_termCloseTabsPending.size}));
})().catch(error=>{console.error(error);process.exit(1)});
'''
    result = _run_node(setup
        + _js_between('  const _termSessionListVersions =', '  // localStorage key prefix')
        + GROUPS
        + _js_between('  async function termKillCurrent(', '  const _termKillAllPending')
        + body)
    assert result['pending'] == 0
    if mode == 'shared':
        assert result['toasts'] and not result['questions'] and not result['calls']
        return
    assert len(result['questions']) == 1
    assert ('All 1 child terminal' if mode == 'child' else 'All 3 child terminals') in result['questions'][0]
    assert 'will also be deleted' in result['questions'][0]
    if mode == 'cancel':
        assert result['unchanged'] and not result['calls']
        return
    expected = {'child', 'nested'} if mode == 'child' else {'parent', 'child', 'nested', 'sibling'}
    requests = [row for row in result['calls'] if row[0] == 'DELETE']
    assert {row[1].split('/').pop().split('?')[0] for row in requests} == expected
    assert all(row[1].endswith('?purge=true&vault=one') for row in requests)
    assert requests[0][1].startswith('/api/term/sessions/nested?')
    assert bool(result['alerts']) == (mode == 'failure')
    assert set(result['removed']) == expected - ({'nested'} if mode == 'failure' else set())
    assert result['saved']['tabExpanded'] == ({'parent': True, 'outside': True} if mode == 'child' else {'outside': True})
    assert not result['saved']['tabDisplayMains']
    assert result['saved']['tabMembership']['outside'] == 'dev'
    assert not result['other']['tabParents']
    if mode == 'navigate':
        assert not any(row[0] in {'detach','refresh','attach'} for row in result['calls'])
    else:
        assert sum(row[0] == 'detach' for row in result['calls']) == int(mode != 'failure')
