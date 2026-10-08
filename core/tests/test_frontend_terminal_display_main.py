"""A merged parent tab retains its identity and opens the chosen child console."""
from .test_frontend_terminal_subtabs import GROUPS, PILL
from .test_frontend_terminal_ui import _run_node


def test_merge_combines_rows_but_keeps_parent_identity_real_relationships_and_scope():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups';
let vault='one';
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const termSessions=['parent','child','nested','other'].map(name=>({name,logical_name:name,session_id:'uuid-'+name}));
const termCurrentSession='parent',termCurrentWorkspaceId='demo';
termSessions[0].linked_scope={root:'/trees/red',worktree:'/trees/red',color:'#ff7b72'};
const termSessEsc=String,_termSessionDisplay=s=>s.name,_termSessionMeta=name=>termSessions.find(s=>s.name===name);
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=>vault,_termSessionsKey=(w,v)=>v+'::'+w;
let renders=0;const termRenderSessionList=()=>renders++;
window.LabObjectives={taskForTerminal:()=>null};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({order:termSessions.map(s=>'s:'+s.name),tabParents:{child:'parent',nested:'child'}});
_termWriteGroupState(state);const before=JSON.stringify(termSessions),originalParents=JSON.stringify(state.tabParents);
const selected=_termSetDisplayMain('nested'),saved=_termReadGroupState();
const pill=(s,i)=>`<span class="sess" role="tab" data-name="${s.name}"${s.display_main?' data-display-main-parent="'+s.display_main.parent+'" data-color="'+s.display_main.color+'"':''}>${s.display_main?.identity.name||s.name}</span>`;
const html=termSessions.map(_termSubtabRenderer(saved,termSessions,pill)).join('');
const included=_termIncludeVisibleSubtabs([termSessions[3]],termSessions,saved).map(s=>s.name);
vault='two';const otherVault=Object.keys(_termReadGroupState().tabDisplayMains);vault='one';
const restored=_termSetDisplayMain('nested',true),after=_termReadGroupState();
console.log(JSON.stringify({selected,saved,html,included,otherVault,restored,after,renders,
 unchanged:before===JSON.stringify(termSessions),parentsUnchanged:originalParents===JSON.stringify(saved.tabParents)}));
''')
    assert result['selected'] and result['restored'] and result['renders'] == 2
    assert result['saved']['tabDisplayMains'] == {'child': 'nested'}
    assert result['saved']['tabDisplayMainVersion'] == 2
    assert not result['after']['tabDisplayMains'] and not result['otherVault']
    assert result['unchanged'] and result['parentsUnchanged']
    assert result['html'].index('data-name="parent"') < result['html'].index('data-name="nested"')
    assert 'data-term-parent="parent"><span class="sess" role="tab" aria-expanded="true" data-subtab-toggle data-name="parent"' in result['html']
    assert 'data-display-main-parent="child" data-color="#ff7b72"' in result['html']
    assert result['html'].count('data-name="parent"') == 1
    assert result['html'].count('data-name="nested"') == 1
    assert 'data-name="child"' not in result['html']
    assert '>child</span>' in result['html']
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


def test_merged_tab_uses_parent_name_icon_color_and_child_session_identity():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups',termSessEsc=String;
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const automation='automation-'+('a'.repeat(32))+'-1';
const parent={name:'parent',logical_name:'parent',label:'Parent connection',session_id:'parent-id'};
const child={name:'child-session',logical_name:automation,label:'Child process',session_id:'child-id'};
const termSessions=[parent,child],termCurrentSession=child.name,termCurrentWorkspaceId='demo';
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'one',_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),_termSessionDisplay=s=>s.label;
const termRenderSessionList=()=>{},_termRecentScopeKey=()=> 'demo',termDeadSessions=new Set();
const _termSessionVisual=s=>({kind:'terminal',badge:'Terminal',icon:s.name==='parent'?'🧠':'💻'});
const _termSessionRecentMeta=()=>null,_termSessionIsWorking=()=>false,_termSessionContext=()=>({label:'Requests'}),_termSessionSummary=()=>'',_termSessionTooltipPayload=()=> '{}';
window.LabObjectives={taskForTerminal:()=>null,terminalColor:s=>s.name==='parent'?'#58a6ff':'#ff7b72'};
''' + GROUPS + PILL + r'''
const state=_termNormalizeGroupState({tabParents:{[automation]:'parent'}});_termWriteGroupState(state);
_termSetDisplayMain(child.name);const before=JSON.stringify(termSessions);
const html=termSessions.map(_termSubtabRenderer(_termReadGroupState(),termSessions,_termSessionPillHtml)).join('');
console.log(JSON.stringify({html,unchanged:JSON.stringify(termSessions)===before}));
''')
    html = result['html']
    assert result['unchanged']
    assert 'data-name="child-session"' in html and 'data-name="parent"' not in html
    assert 'aria-selected="true"' in html
    assert 'class="sess-icon" aria-hidden="true">🧠</span>' in html
    assert 'class="sess-label custom">Parent connection</span>' in html
    assert '--term-display-main-color:#58a6ff' in html
    assert 'Merged with Child process' in html


def test_wip_parent_and_automation_child_have_one_visible_merged_row():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],termSessEsc=String,_termSessionDisplay=s=>s.name;
const automation='automation-'+('a'.repeat(32))+'-1';
const termSessions=['parent',automation].map(name=>({name,logical_name:name}));
const termCurrentSession='parent',termCurrentWorkspaceId='demo',_termActiveWorkspaceId=()=> 'demo';
window.LabObjectives={taskForTerminal:s=>({status:'in_progress',inherited:s.name!=='parent'})};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:{[automation]:'parent'},tabDisplayMains:{parent:automation}});
console.log(JSON.stringify({html:termSessions.map(_termSubtabRenderer(state,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join(''),automation}));
''')
    assert result['html'].count(f'data-name="{result["automation"]}"') == 1
    assert 'data-name="parent"' not in result['html']
    assert ' hidden' not in result['html']


def test_saved_grandparent_swap_corrects_to_immediate_parent_and_restores():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups';
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const termSessions=['grandparent','parent','child'].map(name=>({name,logical_name:name}));
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'one',_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),termRenderSessionList=()=>{};
window.LabObjectives={};
''' + GROUPS + r'''
const legacy=_termNormalizeGroupState({tabParents:{parent:'grandparent',child:'parent'},tabDisplayMains:{grandparent:'child'}});
_termWriteGroupState(legacy);
const corrected=[..._termDisplayMains(_termReadGroupState())];
const staleNewPreference=[..._termDisplayMains({...legacy,tabDisplayMainVersion:2})];
const restore=_termSetDisplayMain('parent',true),saved=_termReadGroupState();
console.log(JSON.stringify({corrected,staleNewPreference,restore,saved}));
''')
    assert result['corrected'] == [['parent', 'child']]
    assert result['staleNewPreference'] == []
    assert result['restore'] and not result['saved']['tabDisplayMains']
    assert result['saved']['tabDisplayMainVersion'] == 2
    assert result['saved']['tabParents'] == {'parent': 'grandparent', 'child': 'parent'}


def test_adjacent_merges_replace_conflicting_pairs_without_duplicating_rows():
    result = _run_node(r'''
const _TERM_GROUP_COLORS=['#58a6ff'],_TERM_GROUPS_KEY='groups';
const stored={},localStorage={getItem:key=>stored[key],setItem:(key,value)=>stored[key]=value};
const termSessions=['grandparent','parent','child','nested','sibling','other-parent','other-child'].map(name=>({name,logical_name:name}));
const termCurrentSession='grandparent',termCurrentWorkspaceId='demo';
const _termActiveWorkspaceId=()=> 'demo',_termVaultId=()=> 'one',_termSessionsKey=(w,v)=>v+'::'+w;
const _termSessionMeta=name=>termSessions.find(s=>s.name===name),termRenderSessionList=()=>{};
const termSessEsc=String,_termSessionDisplay=s=>s.name;
window.LabObjectives={};
''' + GROUPS + r'''
const state=_termNormalizeGroupState({tabParents:{parent:'grandparent',child:'parent',nested:'child',sibling:'parent','other-child':'other-parent'}});
_termWriteGroupState(state);
_termSetDisplayMain('child');const first=_termReadGroupState().tabDisplayMains;
_termSetDisplayMain('nested');const second=_termReadGroupState().tabDisplayMains;
_termSetDisplayMain('other-child');_termSetDisplayMain('sibling');const saved=_termReadGroupState();
const html=termSessions.map(_termSubtabRenderer(saved,termSessions,s=>`<span class="sess" role="tab" data-name="${s.name}">${s.name}</span>`)).join('');
console.log(JSON.stringify({first,second,saved,counts:Object.fromEntries(termSessions.map(s=>[s.name,html.split('data-name="'+s.name+'"').length-1]))}));
''')
    assert result['first'] == {'parent': 'child'}
    assert result['second'] == {'child': 'nested'}
    assert result['saved']['tabDisplayMains'] == {
        'child': 'nested', 'other-parent': 'other-child', 'parent': 'sibling',
    }
    assert result['counts'] == {'grandparent': 1, 'parent': 0, 'child': 0,
                                'nested': 1, 'sibling': 1, 'other-parent': 0, 'other-child': 1}
