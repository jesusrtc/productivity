"""A chosen child occupies its parent's display slot without changing ownership."""
from .test_frontend_terminal_subtabs import GROUPS
from .test_frontend_terminal_ui import _run_node


def test_main_display_swaps_rows_but_keeps_real_parent_and_scope_state():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups';
let vault='one';
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const termSessions=['parent','child','nested','other'].map(name=>({name,logical_name:name,session_id:'uuid-'+name}));
termSessions[0].linked_scope={root:'/trees/red',worktree:'/trees/red',color:'#ff7b72'};
const termSessEsc=String,_termSessionDisplay=s=>s.name,_termSessionMeta=name=>termSessions.find(s=>s.name===name);
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>vault,_termSessionsKey=(w,v)=>v+'::'+w;
let renders=0;const termRenderSessionList=()=>renders++;
window.LabObjectives={taskForTerminal:()=>null};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({order:termSessions.map(s=>'s:'+s.name),tabParents:{child:'parent',nested:'child'}});
_termWriteGroupState(state);const before=JSON.stringify(termSessions),originalParents=JSON.stringify(state.tabParents);
const selected=_termSetDisplayMain('nested'),saved=_termReadGroupState();
const pill=(s,i)=>`<span class="sess" role="tab" data-name="${s.name}"${s.display_main?' data-display-main-parent="'+s.display_main.parent+'" data-color="'+s.display_main.color+'"':''}>${s.name}</span>`;
const html=termSessions.map(_termSubtabRenderer(saved,termSessions,pill)).join('');
const included=_termIncludeDisplayMains([termSessions[3]],termSessions,saved).map(s=>s.name);
vault='two';const otherVault=Object.keys(_termReadGroupState().tabDisplayMains);vault='one';
const restored=_termSetDisplayMain('nested',true),after=_termReadGroupState();
console.log(JSON.stringify({selected,saved,html,included,otherVault,restored,after,renders,
 unchanged:before===JSON.stringify(termSessions),parentsUnchanged:originalParents===JSON.stringify(saved.tabParents)}));
''')
    assert result['selected'] and result['restored'] and result['renders'] == 2
    assert result['saved']['tabDisplayMains'] == {'parent': 'nested'}
    assert not result['after']['tabDisplayMains'] and not result['otherVault']
    assert result['unchanged'] and result['parentsUnchanged']
    assert result['html'].index('data-name="nested"') < result['html'].index('data-name="parent"')
    assert 'data-display-main-parent="parent" data-color="#ff7b72"' in result['html']
    assert result['html'].count('data-name="parent"') == 1
    assert result['html'].count('data-name="nested"') == 1
    assert result['included'] == ['other', 'nested', 'child', 'parent']


def test_removed_moved_or_cross_objective_children_restore_normal_display():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],termSessEsc=String,_termSessionDisplay=s=>s.name;
const termSessions=['parent','child','other'].map(name=>({name,logical_name:name,objective:name==='other'?'two':'one'}));
window.LabObjectives={sameTerminalObjective:(a,b)=>a.objective===b.objective};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:{child:'parent'},tabDisplayMains:{parent:'child'}});
const selected=[..._termDisplayMains(state)];
const gone=[..._termDisplayMains(state,termSessions.filter(s=>s.name!=='child'))];
const moved=[..._termDisplayMains({...state,tabParents:{}})];
const foreign=[..._termDisplayMains({...state,tabParents:{child:'other'},tabDisplayMains:{other:'child'}})];
console.log(JSON.stringify({selected,gone,moved,foreign}));
''')
    assert result == {'selected': [['parent', 'child']], 'gone': [], 'moved': [], 'foreign': []}


def test_wip_parent_row_keeps_visibility_after_swap_while_automation_main_is_at_top():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],termSessEsc=String,_termSessionDisplay=s=>s.name;
const automation='automation-'+('a'.repeat(32))+'-1';
const termSessions=['parent',automation].map(name=>({name,logical_name:name}));
window.LabObjectives={taskForTerminal:s=>({status:'in_progress',inherited:s.name!=='parent'})};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:{[automation]:'parent'},tabDisplayMains:{parent:automation}});
console.log(JSON.stringify({html:termSessions.map(_termSubtabRenderer(state,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join(''),automation}));
''')
    assert result['html'].index(f'data-name="{result["automation"]}"') < result['html'].index('data-name="parent"')
    assert ' hidden' not in result['html']
