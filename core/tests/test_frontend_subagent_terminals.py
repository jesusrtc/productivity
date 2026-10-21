"""Cold browser hierarchy uses exact saved subagent parents inside task blocks."""
from .test_frontend_terminal_ui import _run_node
from .test_frontend_terminal_subtabs import GROUPS, LAB_SHELL_CSS
from .test_frontend_project_cache import _check_project_html

SETUP = r'''
const _TERM_GROUP_COLORS=['#58a6ff'];
let termCurrentSession='child',termCurrentWorkspaceId='demo';
const _termActiveWorkspaceId=()=> 'demo';
const termSessEsc=String,_termSessionDisplay=s=>s.label||s.name;
const parent={name:'parent',logical_name:'parent',tmux_socket:'owned',tmux_id:'$1',created:1};
const child={name:'child',label:'Review tests',logical_name:'child',tmux_socket:'owned',tmux_id:'$2',created:2,
 parent_terminal:'parent',subagent:{parent:{name:'parent',tmux_socket:'owned',tmux_id:'$1',created:1}}};
let termSessions=[parent,child];
window.LabObjectives={terminalTaskBlock:()=> 'task-one',taskForTerminal:s=>({status:'in_progress',inherited:s!==parent}),sameTerminalObjective:()=>true};
'''


def test_saved_parent_survives_cold_clients_but_not_recreated_sessions():
    result=_run_node(SETUP+GROUPS+r'''
const state=_termNormalizeGroupState({}),first=_termSubtabParents(state);
const render=_termSubtabRenderer(state,termSessions,s=>`<button data-name="${s.name}">${s.label||s.name}</button>`);
const html=termSessions.map(render).join('');
parent.tmux_id='$3';const replaced=_termSubtabParents(state);
const cached=_termSubtabParents(_termNormalizeGroupState({tabParents:{child:'parent'}}));
parent.tmux_id='$1';const cycle=_termSubtabParents(_termNormalizeGroupState({tabParents:{parent:'child'}}));
console.log(JSON.stringify({first,html,replaced,cached,cycle}));
''')
    assert result['first']=={'child':'parent'} and result['replaced']=={}
    assert result['cached']=={} and not (result['cycle'].get('child')=='parent' and result['cycle'].get('parent')=='child')
    assert result['html'].index('data-term-parent="parent"') < result['html'].index('data-name="child"')
    assert 'Review tests' in result['html'] and result['html'].count('data-name="child"')==1


def test_native_browser_renders_saved_child_inside_its_task_block(tmp_path):
    checks=r'''
try{
 const state=_termNormalizeGroupState({});
 function render(){const pill=_termSubtabRenderer(state,termSessions,s=>`<button class="sess" role="tab" data-name="${s.name}">${s.label||s.name}</button>`);document.getElementById('terms').innerHTML=termSessions.map(pill).join('');}
 render();
 const node=document.querySelector('[data-term-parent="parent"]');
 if(!node?.querySelector('.term-subtab-children [data-name="child"]')||node.querySelector('[data-name="child"]').hidden)throw Error('Child missing beneath its parent');
 if(node.querySelector('[data-name="child"]').textContent!=='Review tests')throw Error('Child label lost');
 // Rebuild with no browser layout: the saved relationship remains authoritative.
 render();if(!document.querySelector('[data-term-parent="parent"] [data-name="child"]'))throw Error('Cold reload lost hierarchy');
 parent.tmux_id='$99';render();if(document.querySelector('[data-term-parent="parent"]'))throw Error('Recreated parent adopted old child');
 document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(error.stack);}
'''
    html='<!doctype html><meta charset="utf-8"><style>'+LAB_SHELL_CSS.read_text()+'</style><div id="terms"></div><script>'+SETUP+GROUPS+checks+'</script>'
    _check_project_html(tmp_path,html,focused=True,screenshot=True)
