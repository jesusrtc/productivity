from .test_frontend_terminal_ui import _js_between, _run_node


def test_opening_assistant_only_attaches_live_sessions_even_when_auto_spawn_is_enabled():
    restore=_js_between('  async function _termRestoreSessionsForWorkspace(', '  function termStartPeriodicRefresh()')
    result=_run_node(restore+'''
const calls=[];
let termSessions=[];
const _termVaultId=()=> '__assistant__', _vaultQuery=()=>'', _termIsScopeActive=()=>true;
const _termRefreshSessionsForWorkspaceId=async()=>{}, _termClientLog=()=>{};
const _termKillAllPending=new Set(), _termCloseTabsPending=new Set(), _termSessionsKey=id=>id;
const localStorage={getItem:()=> '1'}, termAutoSpawnEnabled=async()=>true;
const termDetach=()=>{}, termShowEmpty=()=>{}, termSetStatus=()=>{};
const _termPickRestoreName=()=>termSessions[0]?.name, termAttach=name=>calls.push(['attach',name]);
const termSpawnSession=async()=>{throw new Error('Automatic spawn is forbidden in Assistant')};
const fetch=async(url,options={})=>{
 if(options.method==='POST')throw new Error('Saved sessions must not auto-resume in Assistant');
 return {ok:true,json:async()=>[{name:'old',kind:'claude'}]};
};
(async()=>{
 await _termRestoreSessionsForWorkspace('__assistant__');
 const empty=calls.length;
 termSessions=[{name:'running-one',logical_name:'old'}];
 await _termRestoreSessionsForWorkspace('__assistant__');
 process.stdout.write(JSON.stringify({empty,calls}));
})();
''')
    assert result=={'empty':0,'calls':[['attach','running-one']]}
