// Notebook textarea input must also reach its visible syntax overlay and draft.
import {resolve} from 'node:path';
import {captureInputClock,validateInputClock} from './input_clock.mjs';
import {documentTypingKeys,observeDocumentTyping} from './document_typing_probe.mjs';

export function notebookDraftReady(editor,highlight,draftKey,expected) {
  return editor.isConnected && !editor.readOnly && highlight?.isConnected
    && highlight.textContent===expected && localStorage.getItem(draftKey)===expected;
}

export async function runNotebookTyping(client,evaluate,output,{workspaceRoot,action,sample,cadenceMs=25}) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot)
    || !['alpha','beta'].includes(action.target))throw Error('Notebook typing requires the disposable fixture');
  if(cadenceMs!==25)throw Error('Notebook typing uses the fixed 25 ms cadence');
  const {before,text}=action.notebookTyping;
  if(text.includes('\t'))throw Error('Notebook typing does not substitute indentation for native Tab');
  const keys=documentTypingKeys(text),sent=[],scope=workspaceRoot+'/'+action.target;
  await evaluate(`(async()=>{
    const expected=__notebookViewExpected[${JSON.stringify(action.target)}];
    if(currentWorkspace?.path!==${JSON.stringify(scope)} || !__notebookViewReady(expected)
      || expected.cells[1].source!==${JSON.stringify(before)})throw Error('Unexpected notebook typing scope/source');
    const cell=document.querySelector('#content .nb-cell[data-cell-index="1"]');
    const editor=cell?.querySelector('.nb-cell-edit-area'),highlight=cell?.querySelector('.nb-cell-edit-highlight code');
    if(!editor || editor.value!==${JSON.stringify(before)})throw Error('Notebook editor is not ready');
    editor.focus();editor.setSelectionRange(editor.value.length,editor.value.length);
    editor.scrollIntoView({block:'end'});
    await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
    const verify=${notebookDraftReady.toString()};
    const draftKey=_cellDraftKey(${JSON.stringify('workspaces/'+action.target+'/notebooks/review.ipynb')},cell.dataset.cellId);
    window.__notebookTyping=(${observeDocumentTyping.toString()})(editor,${JSON.stringify(keys)},
      ${JSON.stringify(before)},${captureInputClock.toString()},value=>verify(editor,highlight,draftKey,value));
  })()`);
  try {
    const jobs=[];
    for(const [index,descriptor] of keys.entries()) {
      const {insert,...key}=descriptor,sentEpoch=Date.now();sent.push(sentEpoch);
      jobs.push(client.send('Input.dispatchKeyEvent',{type:'keyDown',timestamp:sentEpoch/1000,...key}));
      const {text,...released}=key;
      jobs.push(client.send('Input.dispatchKeyEvent',{type:'keyUp',timestamp:sentEpoch/1000,...released}));
      if(index<keys.length-1)await new Promise(resolve=>setTimeout(resolve,cadenceMs));
    }
    const acknowledgments=await Promise.allSettled(jobs),deadline=Date.now()+10000;
    let result;
    do {
      result=await evaluate('__notebookTyping.snapshot()');
      if(result.complete||result.error)break;
      await new Promise(resolve=>setTimeout(resolve,10));
    } while(Date.now()<deadline);
    for(const row of result.rows)output.push({...row,sample,kind:'notebook-typing',target:action.target,
      sentEpoch:sent[row.index],clockCheck:validateInputClock(row.clock,sent[row.index])});
    if(acknowledgments.some(row=>row.status==='rejected'))throw Error('Notebook key dispatch failed');
    if(result.error || !result.complete || !result.valueVerified
      || output.slice(-result.rows.length).some(row=>!row.clockCheck.valid))throw Error('Notebook typing failed: '+(result.error||'incomplete input or invalid clock'));
    await evaluate(`(()=>{
      const expected=__notebookViewExpected[${JSON.stringify(action.target)}];
      expected.cells[1].source=${JSON.stringify(before+text)};
      if(!__notebookViewReady(expected))throw Error('Notebook typing changed another cell, output or control');
    })()`);
  } finally {
    await evaluate('window.__notebookTyping?.dispose();delete window.__notebookTyping');
  }
}
