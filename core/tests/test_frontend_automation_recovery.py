"""Failed reconnect cards stay red, target their group, and preserve agent reports."""
from .test_frontend_terminal_ui import ROOT
from .test_frontend_terminal_completion import MODULE
from .test_frontend_terminal_notifications import NOTIFICATIONS
from .test_frontend_project_cache import _check_project_html


def test_failed_reconnect_card_priority_history_stale_clicks_and_exact_action_in_chrome(tmp_path):
    setup = r'''
const assert=(ok,message)=>{if(!ok)throw Error(message)};
const until=async fn=>{for(let i=0;i<100;i++){if(fn())return;await new Promise(r=>setTimeout(r,5));}throw Error('Timed out '+fn)};
const terminal={name:'group-main',logical_name:'Main',workspace_id:'demo',vault:'owner',tmux_socket:'owned',tmux_id:'$1',created:1,llm_controlled:false,
 terminal_status:{version:1,state:'finished',id:'finish',revision:20,updated_at:20,message:'A newer ordinary finish'},
 terminal_recovery_alert:null};
const target={logical_name:'automation-'+'a'.repeat(32)+'-1',launch_id:'failed-third-attempt'};
const failure={version:1,state:'attention',kind:'reconnect',active:true,id:'failure',revision:10,updated_at:10,
 source:'reconnect:cycle',targets:[target],message:'Could not reconnect after 3 attempts, 2 minutes apart: Remote SSH.'};
const snapshot={'owner::demo':[terminal],'borrower::demo':[terminal]};
'''
    checks = r'''
(async()=>{try{
const N=LabTerminalNotifications,C=LabTerminalCompletion,host=document.getElementById('termNotifications');
let opened=0,reconnected=0,release,errors=[];
N.configure({open:async item=>{assert(item.session===terminal,'exact main navigation');opened++;return terminal},
 error:message=>errors.push(message),reconnect:async item=>{
  assert(item.owner.workspace_id==='demo'&&item.owner.vault==='owner'&&item.targets[0].launch_id===target.launch_id,'captured owner and exact failed generation');
  reconnected++;await new Promise(resolve=>release=resolve);
 }});
N.update(snapshot);assert(!host.querySelector('[data-notification-reconnect]'),'no reconnect notification while attempts are pending');
terminal.terminal_recovery_alert=failure;N.update(snapshot);
assert(N.items().length===1&&N.items()[0].kind==='reconnect','shared main appears once and failure precedes a newer green report');
let card=host.querySelector('.term-notification');
assert(card.textContent.includes('Reconnect failed')&&getComputedStyle(card).backgroundColor==='rgb(156, 48, 56)','failure card is red');
assert(!host.querySelector('[data-notification-snooze]')&&host.querySelector('[data-notification-reconnect]'),'failure offers reconnect');
assert(C.status(terminal).state==='finished','failed reconnect cannot invent agent status');
card.click();await until(()=>opened===1);assert(host.querySelector('.attention'),'opening failure leaves it visible even when history holds a newer green report');
const old=host.querySelector('[data-notification-reconnect]');old.click();old.click();await until(()=>reconnected===1);
assert(host.querySelector('[data-notification-reconnect]').disabled,'in-flight duplicate action is blocked');
release();await new Promise(r=>setTimeout(r,5));
terminal.terminal_recovery_alert={...failure,id:'replacement',revision:30,targets:[{...target,launch_id:'new-generation'}]};N.update(snapshot);
old.click();await new Promise(r=>setTimeout(r,5));assert(reconnected===1,'detached old controls cannot reconnect a replacement generation');
terminal.terminal_recovery_alert.active=false;N.update(snapshot);
assert(!host.querySelector('[data-notification-reconnect]'),'successful recovery resolves active red card');
N.showHistory(true);assert(host.textContent.includes('3 attempts')&&host.textContent.includes('History'),'resolved failure remains in history');
N.showHistory(false);terminal.terminal_recovery_alert={...failure,id:'replacement',revision:30};N.update(snapshot);
assert(!errors.length,errors.join('; '));document.body.dataset.result='pass';
}catch(error){document.body.dataset.result='fail';document.body.append(String(error.stack||error));}})();
'''
    css = (ROOT/'core/src/core/static/css/lab-shell.css').read_text()
    html = '<!doctype html><meta charset="utf-8"><style>'+css+'''
body{--bg-secondary:#161b22;--text-primary:#e6edf3;--border:#30363d;background:#0d1117;color:#e6edf3}
</style><div id="termNotifications" class="term-notifications"></div><script>'''+setup+MODULE+NOTIFICATIONS+checks+'</script>'
    _check_project_html(tmp_path,html,focused=True,screenshot=True)
