"""Native-editor evidence must fail on missing, misplaced or corrupted input."""
import subprocess
import sys

from .test_frontend_logging import _run_node
from .test_perf_document_edit import ROOT


def test_document_typing_requires_its_owned_workflow():
    result = subprocess.run(
        [sys.executable, str(ROOT / 'scripts/perf/lab_navigation_latency.py'),
         '--document-typing'], capture_output=True, text=True)
    assert result.returncode == 2
    assert '--document-typing requires --document-edit' in result.stderr


def test_document_typing_refuses_foreign_scopes_and_unsupported_keys():
    result = _run_node(r"""
(async()=>{
  const {documentTypingKeys,runDocumentTyping}=await import('./scripts/perf/document_typing_probe.mjs');
  let calls=0;const errors=[];
  for(const [workspaceRoot,target] of [['/vault/workspaces','alpha'],
    ['/tmp/lab-navigation-owned/vault/workspaces/../workspaces','alpha'],
    ['/tmp/lab-navigation-owned/vault/workspaces','foreign']]) {
    try{await runDocumentTyping({send:()=>calls++},()=>calls++,[],{
      workspaceRoot,action:{target,typingInput:'x'},sample:1});}catch(error){errors.push(error.message);}
  }
  const rejected=[];
  for(const text of ['', 'é', 'a\b', 'Escape'])try{documentTypingKeys(text);}catch(error){rejected.push(text);}
  process.stdout.write(JSON.stringify({calls,errors,rejected,keys:documentTypingKeys('a 7\n\tz')}));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    assert result['calls'] == 0
    assert result['errors'] == ['Document typing requires the disposable fixture'] * 3
    assert len(result['rejected']) == 4
    assert [key['key'] for key in result['keys']] == ['a', ' ', '7', 'Enter', 'Tab', 'z']
    assert result['keys'][3]['text'] == '\r'
    assert result['keys'][4]['insert'] == '    '
    assert 'text' not in result['keys'][4]


def test_document_typing_checks_each_edit_and_frame_then_removes_listeners():
    result = _run_node(r"""
(async()=>{
  const {documentTypingKeys,observeDocumentTyping}=await import('./scripts/perf/document_typing_probe.mjs');
  const realTimeout=global.setTimeout,frames=[];
  global.requestAnimationFrame=callback=>frames.push(callback);
  global.setTimeout=callback=>frames.push(callback);
  function target() {
    const listeners=new Map();
    return {listeners,
      addEventListener(type,callback,capture=false){listeners.set(type+':'+!!capture,callback);},
      removeEventListener(type,callback,capture=false){const key=type+':'+!!capture;
        if(listeners.get(key)===callback)listeners.delete(key);},
      emit(type,event,capture=false){listeners.get(type+':'+!!capture)?.(event);}};
  }
  function scenario(fault) {
    const editor=Object.assign(target(),{value:'prefix\ncafé',selectionStart:11,selectionEnd:11,isConnected:true});
    global.document=Object.assign(target(),{activeElement:editor});
    const keys=documentTypingKeys('x\n\tz');
    const clock=event=>({source:event.timeStamp,handlerAt:event.timeStamp+1,sourceEpoch:1000+event.timeStamp});
    const probe=observeDocumentTyping(editor,keys,editor.value,clock);
    for(const [index,key] of keys.entries()) {
      if(fault==='missing' && index===3)break;
      const event={type:'keydown',key:key.key,code:key.code,target:editor,isTrusted:true,timeStamp:performance.now()};
      if(fault==='target' && index===0)event.target={};
      if(fault==='untrusted' && index===0)event.isTrusted=false;
      document.emit('keydown',event,true);
      editor.value+=key.insert;editor.selectionStart=editor.selectionEnd=editor.value.length;
      if(fault==='value' && index===0)editor.value+='wrong';
      if(fault==='cursor' && index===0)editor.selectionStart--;
      if(key.key==='Tab') {
        event.defaultPrevented=true;document.emit('keydown',event);
      } else editor.emit('input',{type:'input',target:editor,isTrusted:true,inputType:key.key==='Enter'?'insertLineBreak':'insertText'});
      if(fault==='frame' && index===0)editor.value='different frame';
      while(frames.length)frames.shift()();
    }
    const snapshot=probe.snapshot();probe.dispose();
    return {...snapshot,remainingListeners:editor.listeners.size+document.listeners.size};
  }
  const scenarios=Object.fromEntries(['good','missing','target','untrusted','value','cursor','frame'].map(fault=>[fault,scenario(fault)]));
  global.setTimeout=realTimeout;
  process.stdout.write(JSON.stringify(scenarios));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    good = result['good']
    assert good['complete'] and good['valueVerified'] and good['error'] is None
    assert [row['inputType'] for row in good['rows']] == [
        'insertText', 'insertLineBreak', 'tab-handler', 'insertText']
    assert all(row['done'] and row['valueVerified'] and row['paintValueVerified']
               for row in good['rows'])
    assert not result['missing']['complete']
    for fault in ('target', 'untrusted', 'value', 'cursor', 'frame'):
        assert result[fault]['error'], fault
    assert all(row['remainingListeners'] == 0 for row in result.values())


def test_document_typing_keeps_dispatching_before_acknowledgments_and_retains_bad_clocks():
    result = _run_node(r"""
(async()=>{
  const {runDocumentTyping}=await import('./scripts/perf/document_typing_probe.mjs');
  async function run(badClock) {
    const sent=[],pending=[],rows=[];let disposed=false,error=null,acknowledgedAfter=null;
    const client={send(method,event){sent.push(event);return new Promise(resolve=>{
      pending.push(resolve);if(sent.length===6){acknowledgedAfter=sent.length;pending.forEach(done=>done({}));}
    });}};
    const evaluate=async expression=>{
      if(expression==='__documentTyping.snapshot()')return {complete:true,valueVerified:true,error:null,
        rows:sent.filter(event=>event.type==='keyDown').map((event,index)=>{
          const epoch=event.timestamp*1000,source=index*25;
          return {index,key:event.key,done:true,ms:20,clock:{source,sourceEpoch:epoch,handlerAt:source+2,
            wallEpoch:epoch+2+(badClock?50:0),wallSampleEnd:source+2}};
        })};
      if(expression.includes('.dispose()'))disposed=true;
    };
    let timer;
    try {
      await Promise.race([runDocumentTyping(client,evaluate,rows,{
        workspaceRoot:'/tmp/lab-navigation-owned/vault/workspaces',
        action:{target:'alpha',kind:'edit-save',typingInput:'x\ny',typingBefore:'original'},sample:4}),
        new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Dispatch waited for acknowledgments')),2000);})]);
    } catch(failure){error=failure.message;} finally{clearTimeout(timer);}
    return {error,disposed,acknowledgedAfter,rows,eventTypes:sent.map(event=>event.type),enter:sent[2]};
  }
  process.stdout.write(JSON.stringify({good:await run(false),bad:await run(true)}));
})().catch(error=>{console.error(error);process.exitCode=1;});
""")
    good, bad = result['good'], result['bad']
    assert good['error'] is None and good['disposed']
    assert good['acknowledgedAfter'] == 6
    assert good['eventTypes'] == ['keyDown', 'keyUp'] * 3
    assert good['enter']['text'] == '\r'
    assert all(row['clockCheck']['valid'] for row in good['rows'])
    assert bad['error'] == 'Document typing failed: incomplete input or invalid clock'
    assert bad['disposed'] and len(bad['rows']) == 3
    assert all(not row['clockCheck']['valid'] for row in bad['rows'])
