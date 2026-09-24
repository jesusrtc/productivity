"""Background changes must not replace an Assistant view still opening."""
import pytest

from .test_frontend_assistant import ASSISTANT_APP
from .test_frontend_terminal_ui import _run_node


def run_refresh(checks):
    source = ASSISTANT_APP.read_text()
    lifecycle = source[source.index('  async function refresh('):source.index("  window.addEventListener('storage'")]
    return _run_node(r'''
const assert=require('node:assert/strict');
const state={data:null,section:'documents',request:0,navigation:null,poll:null};
let active=true,modalDone=null,interval;
const events=[],requests=[],content={innerHTML:''};
const document={body:{classList:{contains:()=>active}},hidden:false,getElementById:()=>content};
window.location='https://lab.example/?view=assistant';
const history={replaceState(){}};
const e=String;
const setInterval=callback=>{interval=callback;return 1};
const fetch=url=>new Promise((resolve,reject)=>{requests.push({url,resolve,reject});events.push('read:'+url)});
const data=version=>({version,schema:2,exists:true,root:'/assistant',documents:[],workspaces:[]});
function reply(index,value,ok=true){assert(requests[index],`missing request ${index}`);requests[index].resolve({ok,statusText:'Failed',json:async()=>value})}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const background=()=>refresh({backgroundRefresh:true});
function workspaceRows(){return state.data.workspaces||[]}
function render(){events.push('paint:'+state.data.version)}
function isTaskSection(){return state.section!=='notes'}
function closeDocumentModal(){}
async function openDocumentModal(kind,path){events.push('open:'+kind+':'+path);if(modalDone)await modalDone;events.push('opened:'+path)}
async function refreshOpenDocument(){events.push('modal-refresh')}
''' + lifecycle + '\n(async()=>{\n' + checks + "\nconsole.log(JSON.stringify({passed:true}));\n})().catch(error=>{console.error(error);process.exitCode=1});")


def test_initial_view_renders_before_one_fresh_read_for_overlapping_changes():
    result = run_refresh(r'''
init({section:'documents',task:'task.md'});
const first=background(),second=background();
assert.equal(requests.length,1,'background events leave opening read in flight');
reply(0,data('opening'));await tick();
assert.equal(requests.length,2,'one fresh read follows all intervening events');
assert(events.indexOf('paint:opening')<events.lastIndexOf('read:/api/assistant'));
assert(events.indexOf('opened:task.md')<events.lastIndexOf('read:/api/assistant'));
let finished=false;first.then(()=>finished=true);await tick();assert.equal(finished,false);
reply(1,data('external-change'));await Promise.all([first,second]);
assert.equal(state.data.version,'external-change','fresh response reaches the view');
assert.deepEqual(events.filter(x=>x.startsWith('paint:')),['paint:opening','paint:external-change']);
assert.equal(events.filter(x=>x==='opened:task.md').length,1,'deep link opens only once');
''')
    assert result['passed']


def test_modal_open_and_legacy_note_file_read_finish_before_reconciliation():
    result = run_refresh(r'''
let release;modalDone=new Promise(resolve=>release=resolve);
init({section:'notes',meeting:'meeting.md'});
const queued=background();
reply(0,{...data('legacy'),schema:1});await tick();
assert.equal(requests.length,2);assert(requests[1].url.startsWith('/api/workspace-files?'));
const also=background();
reply(1,[{path:'extra.md'}]);await tick();
assert.equal(requests.length,2,'modal finishes before following read');
assert.deepEqual(state.noteFiles,[{path:'extra.md'}]);
assert(events.includes('open:meeting:meeting.md'));release();await tick();
assert.equal(requests.length,3);reply(2,data('fresh'));await Promise.all([queued,also]);
assert.equal(state.data.version,'fresh');
''')
    assert result['passed']


@pytest.mark.parametrize('action', ['explicit', 'reenter', 'section', 'leave', 'saved-generation'])
def test_newer_actions_cancel_old_queued_refreshes(action):
    checks = {
        'explicit': "const newer=refresh();assert.equal(requests.length,2);reply(1,data('newer'));await newer;",
        'reenter': "init({section:'documents',task:'new.md'});assert.equal(requests.length,2);reply(1,data('newer'));await tick();",
        'section': "state.section='notes';",
        'leave': "active=false;",
        'saved-generation': "++state.request;state.data=data('saved');",
    }
    result = run_refresh(r'''
init({section:'documents',task:'old.md'});
const queued=background();
''' + checks[action] + r'''
const count=requests.length;reply(0,data('old'));await queued;await tick();
assert.equal(requests.length,count,'stale queued event must not read again');
''' + ("assert.equal(state.data.version,'newer');assert(!events.includes('opened:old.md'));" if action in {'explicit','reenter'} else '')
        + ("assert.equal(state.data.version,'saved');assert(!events.includes('paint:old'));" if action=='saved-generation' else '')
        + ("assert(!events.includes('paint:old'));" if action=='leave' else ''))
    assert result['passed']


def test_old_completion_cannot_clear_new_navigation_or_its_queued_changes():
    result = run_refresh(r'''
init({task:'old.md'});const oldQueued=background();
init({task:'new.md'});const newQueued=background();
reply(0,data('old'));await oldQueued;await tick();
const another=background();assert.equal(requests.length,2,'new opening still owns background events');
reply(1,data('new'));await tick();assert.equal(requests.length,3);
reply(2,data('latest'));await Promise.all([newQueued,another]);
assert.equal(state.data.version,'latest');assert(!events.includes('opened:old.md'));
assert.deepEqual(events.filter(x=>x.startsWith('paint:')),['paint:new','paint:latest']);
''')
    assert result['passed']


@pytest.mark.parametrize('failure', ['http', 'network', 'json'])
def test_failed_initial_read_releases_queued_retry(failure):
    settle = {
        'http': "reply(0,{detail:'temporary failure'},false);",
        'network': "requests[0].reject(new Error('temporary failure'));",
        'json': "requests[0].resolve({ok:false,json:async()=>{throw new Error('broken JSON')}});",
    }
    result = run_refresh(r'''
init({section:'documents'});const queued=background();
''' + settle[failure] + r'''
await tick();assert.equal(requests.length,2);assert(content.innerHTML.includes('Assistant'));
reply(1,data('recovered'));await queued;assert.equal(state.data.version,'recovered');
const next=background();assert.equal(requests.length,3,'idle background reads are still immediate');
reply(2,data('next'));await next;assert.equal(state.data.version,'next');
''')
    assert result['passed']


def test_periodic_refresh_uses_background_mode_and_keeps_visibility_guards():
    result = run_refresh(r'''
init({section:'documents'});interval();interval();assert.equal(requests.length,1);
reply(0,data('opening'));await tick();assert.equal(requests.length,2);
reply(1,data('fresh'));await tick();
document.hidden=true;interval();assert.equal(requests.length,2);
document.hidden=false;active=false;interval();assert.equal(requests.length,2);
active=true;interval();assert.equal(requests.length,3);reply(2,data('visible'));await tick();
assert.equal(state.data.version,'visible');
''')
    assert result['passed']
