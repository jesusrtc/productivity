// Save/cancel coverage uses only the navigation fixture's four Markdown files.
import {readFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';

export async function documentEditActions(workspaceRoot,samples,{inputMode='replace',typing=false}={}) {
  const root=resolve(workspaceRoot);
  if(root!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(root))throw new Error('Document editing requires the disposable fixture');
  if(!Number.isInteger(samples)||samples<2)throw new Error('Document editing requires at least two samples');
  if(!['replace','append'].includes(inputMode))throw new Error('Unknown document input mode');
  const expected=new Map();
  for(const workspace of ['alpha','beta'])for(const number of [1,2]) {
    const file=join(root,workspace,'docs',`review-${number}.md`);
    expected.set(file,await readFile(file,'utf8'));
  }
  const actions=[];
  for(let i=0;i<samples;i++) {
    const workspace=i%2?'beta':'alpha',scope=join(root,workspace),path='docs/review-1.md';
    const file=join(scope,path),before=expected.get(file);
    const title=workspace[0].toUpperCase()+workspace.slice(1);
    const marker='Saved fixture revision '+(i+1)+' — café <literal> & "quoted".';
    const saveInput=before+'\n\n'+marker.replace('<literal>','`<literal>`')+'\n';
    const saveKeys=typing?'\nnative keys '+(i+1)+' jqvxmb\tznrp\n':'';
    const saved=saveInput+saveKeys.replaceAll('\t','    ');
    const cancelInput=saved+'\nUNSAVED fixture revision '+(i+1)+'\n';
    const cancelKeys=typing?'\ndiscard keys '+(i+1)+' qzvmbr\txjnp\n':'';
    const sections=Array.from(saved.matchAll(/^## (Section \d+)$/gm),match=>match[1]);
    const paragraphs=[...sections.map(()=>'Fixture paragraph with formatting and code.'),
      ...Array.from(saved.matchAll(/^(?:Saved fixture revision|native keys) .+$/gm),match=>match[0].replaceAll('`',''))];
    const identity=`currentWorkspace?.path===${JSON.stringify(scope)} && _workspaceDocRoot===${JSON.stringify(scope)} && _workspaceDocPath===${JSON.stringify(path)}`;
    const modal=`document.getElementById('docViewModal').classList.contains('active') && document.getElementById('docModalTitle').textContent===${JSON.stringify(path)}`;
    const fileList=`document.querySelectorAll('#docModalFiles .doc-modal-file').length===2 && !document.querySelector('#docModalFiles select').disabled`;
    const editor=source=>`${identity} && ${modal} && ${fileList} && _workspaceDocEditing && _workspaceDocEditContainer===document.getElementById('docModalBody') && document.activeElement?.id==='workspaceDocEditor' && document.querySelector('#docModalBody #workspaceDocEditor')?.value===${JSON.stringify(source)} && Array.from(document.querySelectorAll('#docModalFiles .doc-modal-file')).every(button=>button.disabled)`;
    const rendered=source=>`${identity} && !_workspaceDocEditing && !_workspaceDocEditContainer && _workspaceDocContent===${JSON.stringify(source)} && !document.querySelector('#docModalBody #workspaceDocEditor') && ['#content','#docModalBody'].every(selector=>document.querySelector(selector+' #workspaceDocBody h1')?.textContent===${JSON.stringify(title+' review 1')} && JSON.stringify(Array.from(document.querySelectorAll(selector+' #workspaceDocBody h2'),heading=>heading.firstChild.textContent))===${JSON.stringify(JSON.stringify(sections))} && JSON.stringify(Array.from(document.querySelectorAll(selector+' #workspaceDocBody p'),paragraph=>paragraph.textContent))===${JSON.stringify(JSON.stringify(paragraphs))}) && Array.from(document.querySelectorAll('#docModalFiles .doc-modal-file')).every(button=>!button.disabled)`;
    actions.push(
      {kind:i<2?'workspace':'edit-workspace-restore',target:workspace,selector:'.workspace-tab[data-workspace-id="'+workspace+'"]',ready:i<2
        ?`currentWorkspace?.path===${JSON.stringify(scope)} && document.querySelector('#content [data-workspace-display-title]')?.textContent===${JSON.stringify(title)}`
        :`${identity} && _workspaceDocContent===${JSON.stringify(before)} && document.querySelector('#content h1')?.textContent===${JSON.stringify(title+' review 1')}`},
      {kind:'edit-document',target:workspace,selector:'.sidebar-file[data-open-file][data-filepath="'+path+'"]',ready:`${identity} && _workspaceDocContent===${JSON.stringify(before)} && document.querySelector('#content h1')?.textContent===${JSON.stringify(title+' review 1')}`},
      {kind:'edit-open',target:workspace,selector:'#content button[onclick="startWorkspaceDocEdit()"]',ready:editor(before)},
      {kind:'edit-save',target:workspace,selector:'#docModalBody button[onclick^="saveWorkspaceDoc("]',input:inputMode==='append'?saveInput.slice(before.length):saveInput,inputAppend:inputMode==='append',inputSelector:'#docModalBody #workspaceDocEditor',...(typing?{typingInput:saveKeys,typingBefore:saveInput}:{}),ready:`${modal} && ${rendered(saved)}`},
      {kind:'edit-reopen',target:workspace,selector:'#docModalBody button[onclick="startWorkspaceDocEdit()"]',ready:editor(saved)},
      {kind:'edit-cancel',target:workspace,selector:'#docModalBody button[onclick^="cancelWorkspaceDocEdit("]',input:inputMode==='append'?cancelInput.slice(saved.length):cancelInput,inputAppend:inputMode==='append',inputSelector:'#docModalBody #workspaceDocEditor',...(typing?{typingInput:cancelKeys,typingBefore:cancelInput}:{}),ready:`${modal} && ${rendered(saved)}`},
      {kind:'edit-close',target:workspace,selector:'#docViewModal .doc-modal-close',ready:`!document.getElementById('docViewModal').classList.contains('active') && ${rendered(saved)}`},
    );
    expected.set(file,saved);
    // Snapshot all four files for each save and cancel: two identically named
    // files in another workspace must remain untouched, as must the sibling.
    for(const action of actions.slice(-7).filter(action=>['edit-save','edit-cancel','edit-close'].includes(action.kind)))action.expectedDocuments=[...expected];
  }
  return actions;
}

export async function verifyEditedDocuments(expected) {
  for(const [file,content] of expected)if(!(await readFile(file)).equals(Buffer.from(content,'utf8')))throw new Error('Saved/cancelled document content or workspace identity changed: '+file);
  return {files:expected.length,bytes:expected.reduce((sum,[,content])=>sum+Buffer.byteLength(content),0)};
}

// Exercise the browser's real history stack in the owned, completed workflow.
// Timings include CDP and controller overhead: command-to-verified-paint upper
// bounds, separate from timestamped mouse/key input and physical display.
export async function verifyDocumentHistory(client,evaluate,expected,workspaceRoot,results=[]) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot))throw Error('Document history requires the disposable fixture');
  const original=await client.send('Page.getNavigationHistory');
  if(original.currentIndex<2)throw Error('Document history needs two workspace visits');
  const origin=new URL(original.entries[original.currentIndex].url).origin;
  for(const [direction,index] of [['back',original.currentIndex-1],['forward',original.currentIndex]]) {
    const entry=original.entries[index],url=new URL(entry.url),scope=url.searchParams.get('workspace');
    if(url.hostname!=='127.0.0.1' || url.origin!==origin || !['alpha','beta'].some(name=>scope===join(workspaceRoot,name)))throw Error('History entry escaped the disposable workspaces');
    const source=new Map(expected).get(join(scope,'docs/review-1.md'));
    if(typeof source!=='string')throw Error('History document expectation is missing');
    const headings=Array.from(source.matchAll(/^## (Section \d+)$/gm),match=>match[1]);
    const paragraphs=[...headings.map(()=>'Fixture paragraph with formatting and code.'),
      ...Array.from(source.matchAll(/^(?:Saved fixture revision|native keys) .+$/gm),match=>match[0].replaceAll('`',''))];
    const title=source.split('\n')[0].slice(2);
    const started=performance.now();
    await client.send('Page.navigateToHistoryEntry',{entryId:entry.id});
    await evaluate(`(async()=>{
      const ready=()=>currentWorkspace?.path===${JSON.stringify(scope)} && _workspaceDocRoot===${JSON.stringify(scope)}
        && _workspaceDocPath==='docs/review-1.md' && _workspaceDocContent===${JSON.stringify(source)}
        && location.href===${JSON.stringify(entry.url)} && !_workspaceDocEditing
        && !document.getElementById('docViewModal').classList.contains('active')
        && document.querySelector('#content #workspaceDocBody h1')?.textContent===${JSON.stringify(title)}
        && JSON.stringify(Array.from(document.querySelectorAll('#content #workspaceDocBody h2'),h=>h.firstChild.textContent))===${JSON.stringify(JSON.stringify(headings))}
        && JSON.stringify(Array.from(document.querySelectorAll('#content #workspaceDocBody p'),p=>p.textContent))===${JSON.stringify(JSON.stringify(paragraphs))}
        && Array.from(document.querySelectorAll('#sidebar [data-open-file]')).length>0
        && Array.from(document.querySelectorAll('#sidebar [data-open-file]')).every(row=>row.dataset.entryRoot===${JSON.stringify(scope)});
      const deadline=performance.now()+10000;
      while(!ready()){
        if(performance.now()>deadline)throw Error('History document/sidebar did not finish');
        await new Promise(resolve=>setTimeout(resolve,10));
      }
      await new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0)));
      if(!ready())throw Error('History changed before the verified paint');
    })()`);
    const ms=performance.now()-started;
    const current=await client.send('Page.getNavigationHistory');
    if(current.currentIndex!==index || JSON.stringify(current.entries.map(e=>[e.id,e.url]))!==JSON.stringify(original.entries.map(e=>[e.id,e.url])))throw Error('History navigation added or changed entries');
    results.push({direction,ms,entryId:entry.id,target:scope.split('/').at(-1),verified:true,
      measurement:'CDP history command to verified paint opportunity and controller acknowledgment',
      documentVerification:await verifyEditedDocuments(expected)});
  }
  return results;
}
