"""Promoting a terminal preserves its own session and the complete family."""
from .test_frontend_terminal_subtabs import GROUPS
from .test_frontend_terminal_ui import _run_node


SETUP = r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups';
let vault='one',termCurrentSession='parent',termCurrentWorkspaceId='demo';
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const termSessions=['grandparent','parent','child','sibling','nested','other'].map(name=>({name,logical_name:name,cwd:'/original/'+name,asset:name}));
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>vault,_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),termSessEsc=String,_termSessionDisplay=s=>s.name;
const activated=[],termRenderSessionList=()=>{},_termActivateTab=async name=>activated.push(name);
window.LabObjectives={};
'''


def test_primary_promotes_whole_family_at_immediate_parent_depth_and_reverses():
    result = _run_node(SETUP + GROUPS + r'''
(async()=>{
 const state=_termNormalizeGroupState({order:termSessions.map(s=>'s:'+s.name),tabParents:{parent:'grandparent',child:'parent',sibling:'parent',nested:'child'},tabDisplayMains:{parent:'child'}});
 _termWriteGroupState(state);const before=JSON.stringify(termSessions);
 const selected=await _termMakePrimary('child'),saved=_termReadGroupState();
 const html=termSessions.map(_termSubtabRenderer(saved,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join('');
 const reversed=await _termMakePrimary('parent'),after=_termReadGroupState();
 console.log(JSON.stringify({selected,reversed,saved,after,html,activated,unchanged:JSON.stringify(termSessions)===before}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['selected'] and result['reversed'] and result['unchanged']
    assert result['saved']['tabParents'] == {
        'parent': 'child', 'child': 'grandparent', 'sibling': 'child', 'nested': 'child',
    }
    assert result['saved']['order'] == ['s:grandparent', 's:child', 's:parent', 's:sibling', 's:nested', 's:other']
    assert not result['saved']['tabDisplayMains']
    assert all(result['html'].count(f'data-name="{name}"') == 1
               for name in ['grandparent', 'parent', 'child', 'sibling', 'nested', 'other'])
    assert result['after']['tabParents']['parent'] == 'grandparent'
    assert result['after']['tabParents']['child'] == 'parent'
    assert result['activated'] == ['child', 'parent']


def test_failed_primary_save_preserves_layout_and_duplicate_requests_are_ignored():
    result = _run_node(SETUP + GROUPS + r'''
(async()=>{
 _termWriteGroupState(_termNormalizeGroupState({tabParents:{child:'parent'}}));
 const before=JSON.stringify(_termReadGroupState());let reject,calls=0;
 window.LabObjectives.makeTerminalPrimary=()=>{calls++;return new Promise((_,r)=>reject=r)};
 const first=_termMakePrimary('child'),duplicate=await _termMakePrimary('child');
 reject(Error('Changed elsewhere'));let error;try{await first}catch(e){error=e.message}
 console.log(JSON.stringify({calls,duplicate,error,activated,unchanged:JSON.stringify(_termReadGroupState())===before,pending:_termPrimaryChanges.size}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result == {'calls': 1, 'duplicate': False, 'error': 'Changed elsewhere',
                      'activated': [], 'unchanged': True, 'pending': 0}


def test_primary_save_keeps_captured_vault_without_activating_another_workspace():
    result = _run_node(SETUP + GROUPS + r'''
(async()=>{
 _termWriteGroupState(_termNormalizeGroupState({tabParents:{child:'parent'},tabRoots:['parent']}));
 let resolve;window.LabObjectives.makeTerminalPrimary=()=>new Promise(r=>resolve=r);
 const save=_termMakePrimary('child');vault='two';resolve();await save;
 const current=_termReadGroupState();vault='one';const saved=_termReadGroupState();
 console.log(JSON.stringify({current,saved,activated}));
})().catch(e=>{console.error(e);process.exit(1)});
''')
    assert result['activated'] == [] and result['current']['tabParents'] == {}
    assert result['saved']['tabParents'] == {'parent': 'child'}
    assert result['saved']['tabRoots'] == ['child']
