// Save/cancel coverage uses only the navigation fixture's four Markdown files.
import {readFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';

export async function documentEditActions(workspaceRoot,samples) {
  const root=resolve(workspaceRoot);
  if(root!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(root))throw new Error('Document editing requires the disposable fixture');
  if(!Number.isInteger(samples)||samples<2)throw new Error('Document editing requires at least two samples');
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
    const saved=before+'\n\n'+marker.replace('<literal>','`<literal>`')+'\n';
    const cancelled=saved+'\nUNSAVED fixture revision '+(i+1)+'\n';
    const sections=Array.from(saved.matchAll(/^## (Section \d+)$/gm),match=>match[1]);
    const paragraphs=[...sections.map(()=>'Fixture paragraph with formatting and code.'),
      ...Array.from(saved.matchAll(/^Saved fixture revision .+$/gm),match=>match[0].replaceAll('`',''))];
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
      {kind:'edit-save',target:workspace,selector:'#docModalBody button[onclick^="saveWorkspaceDoc("]',input:saved,inputSelector:'#docModalBody #workspaceDocEditor',ready:`${modal} && ${rendered(saved)}`},
      {kind:'edit-reopen',target:workspace,selector:'#docModalBody button[onclick="startWorkspaceDocEdit()"]',ready:editor(saved)},
      {kind:'edit-cancel',target:workspace,selector:'#docModalBody button[onclick^="cancelWorkspaceDocEdit("]',input:cancelled,inputSelector:'#docModalBody #workspaceDocEditor',ready:`${modal} && ${rendered(saved)}`},
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
