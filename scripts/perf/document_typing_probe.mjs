// Native editor input -> verified value/cursor -> animation-frame task.
// A browser paint opportunity estimate, not physical display or paste latency.
import {captureInputClock,validateInputClock} from './input_clock.mjs';
import {resolve} from 'node:path';

export function documentTypingKeys(text) {
  if(!text || !/^[a-z0-9 \n\t]+$/.test(text))throw Error('Unsupported document typing text');
  return [...text].map(key=>key==='\n'
    ? {key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r',insert:'\n'}
    : key==='\t' ? {key:'Tab',code:'Tab',windowsVirtualKeyCode:9,insert:'    '}
    : {key,code:key===' '?'Space':/[0-9]/.test(key)?'Digit'+key:'Key'+key.toUpperCase(),
      windowsVirtualKeyCode:key.toUpperCase().charCodeAt(0),text:key,insert:key});
}

// Serialized into the fixture browser. No module-level dependencies.
export function observeDocumentTyping(editor,keys,before,captureClock) {
  if(!editor || document.activeElement!==editor || editor.value!==before
    || editor.selectionStart!==before.length || editor.selectionEnd!==before.length)throw Error('Document typing source/cursor is not ready');
  const state={rows:[],expected:before,error:null},pending=[];
  const fail=message=>{state.error ||= message;};
  const checkValue=()=>editor.isConnected && document.activeElement===editor
    && editor.value===state.expected && editor.selectionStart===state.expected.length
    && editor.selectionEnd===state.expected.length;
  const keydown=event=>{
    const key=keys[state.rows.length];
    if(event.target!==editor || !event.isTrusted || !key || event.key!==key.key || event.code!==key.code) {
      fail('Unexpected document key or editor identity');return;
    }
    const clock=captureClock(event),row={index:state.rows.length,key:event.key,clock,
      queue:clock.handlerAt-clock.source,sourceEpoch:clock.sourceEpoch,done:false};
    state.rows.push(row);pending.push(row);
  };
  const edited=event=>{
    // Lab handles Tab directly on the textarea without dispatching input.
    // Observe its ordinary bubbling keydown after that production handler.
    if(event.type==='keydown' && event.key!=='Tab')return;
    const row=pending.shift(),key=row&&keys[row.index];
    if(!row || event.target!==editor || !event.isTrusted
      || (event.type==='keydown')!==(key.key==='Tab')) {fail('Unexpected document edit event');return;}
    if(key.key==='Tab' && !event.defaultPrevented)fail('Tab did not retain the editor focus');
    state.expected+=key.insert;
    row.editAt=performance.now();row.inputType=event.inputType||'tab-handler';
    row.valueVerified=checkValue();
    if(!row.valueVerified)fail('Document value, cursor or focus differs after input');
    requestAnimationFrame(()=>setTimeout(()=>{
      row.paintValueVerified=checkValue();
      if(!row.paintValueVerified)fail('Document value, cursor or focus differs at paint opportunity');
      row.paintIndex=state.rows.length-1;
      row.ms=performance.now()-row.clock.source;row.done=true;
    },0));
  };
  document.addEventListener('keydown',keydown,true);
  document.addEventListener('keydown',edited);
  editor.addEventListener('input',edited);
  return {
    snapshot:()=>({rows:state.rows,error:state.error,complete:state.rows.length===keys.length
      && !pending.length && state.rows.every(row=>row.done),valueVerified:checkValue()}),
    dispose:()=>{document.removeEventListener('keydown',keydown,true);
      document.removeEventListener('keydown',edited);editor.removeEventListener('input',edited);},
  };
}

export async function runDocumentTyping(client,evaluate,output,{workspaceRoot,action,sample,cadenceMs=25}) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot)
    || !['alpha','beta'].includes(action.target))throw Error('Document typing requires the disposable fixture');
  if(cadenceMs!==25)throw Error('Document typing uses the fixed 25 ms cadence');
  const keys=documentTypingKeys(action.typingInput),sent=[];
  await evaluate(`(()=>{
    if(currentWorkspace?.path!==${JSON.stringify(workspaceRoot+'/'+action.target)} || !_workspaceDocEditing
      || _workspaceDocRoot!==currentWorkspace.path || _workspaceDocPath!=='docs/review-1.md')throw Error('Unexpected document typing scope');
    window.__documentTyping=(${observeDocumentTyping.toString()})(document.querySelector('#docModalBody #workspaceDocEditor'),
      ${JSON.stringify(keys)},${JSON.stringify(action.typingBefore)},${captureInputClock.toString()});
  })()`);
  let result;
  try {
    const jobs=[];
    for(const [index,descriptor] of keys.entries()) {
      const {insert,...key}=descriptor,sentEpoch=Date.now();sent.push(sentEpoch);
      // Send independently of acknowledgments, retaining queued input. The
      // next key is never delayed until the renderer processes this one.
      jobs.push(client.send('Input.dispatchKeyEvent',{type:'keyDown',timestamp:sentEpoch/1000,...key}));
      const {text,...released}=key;
      jobs.push(client.send('Input.dispatchKeyEvent',{type:'keyUp',timestamp:sentEpoch/1000,...released}));
      if(index<keys.length-1)await new Promise(resolve=>setTimeout(resolve,cadenceMs));
    }
    const acknowledgments=await Promise.allSettled(jobs);
    const deadline=Date.now()+10000;
    do {
      result=await evaluate('__documentTyping.snapshot()');
      if(result.complete||result.error)break;
      await new Promise(resolve=>setTimeout(resolve,10));
    } while(Date.now()<deadline);
    for(const row of result.rows)output.push({...row,sample,kind:action.kind,target:action.target,
      sentEpoch:sent[row.index],clockCheck:validateInputClock(row.clock,sent[row.index])});
    if(acknowledgments.some(row=>row.status==='rejected'))throw Error('Document key dispatch failed');
    if(result.error || !result.complete || !result.valueVerified
      || output.slice(-result.rows.length).some(row=>!row.clockCheck.valid))throw Error('Document typing failed: '+(result.error||'incomplete input or invalid clock'));
  } finally {
    await evaluate('window.__documentTyping?.dispose();delete window.__documentTyping');
  }
}
