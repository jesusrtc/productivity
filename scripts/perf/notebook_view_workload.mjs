// Read-only notebook controls in the CLI-created navigation fixture.
import {readFile} from 'node:fs/promises';
import {resolve,join} from 'node:path';

export function notebookViewReady(expected,{codeHidden=false,collapsed=false}={}) {
  if(currentWorkspace?.path!==expected.scope || _workspaceDocRoot!==expected.scope
      || _workspaceDocPath!=='notebooks/review.ipynb')return false;
  const content=document.getElementById('content'),notebook=content?.querySelector('.nb-container');
  if(!notebook || notebook.classList.contains('nb-code-hidden')!==codeHidden)return false;
  if(content.querySelector('[data-nb-toggle-code]')?.getAttribute('aria-pressed')!==String(codeHidden))return false;
  const cells=Array.from(notebook.querySelectorAll(':scope > .nb-cell'));
  if(cells.length!==expected.cells.length)return false;
  return cells.every((cell,index)=>{
    const source=expected.cells[index];
    if(cell.dataset.cellId!==source.id || cell.dataset.cellIndex!==String(index)
        || cell.dataset.cellType!==source.cell_type || !cell.querySelector('.nb-cell-del'))return false;
    if(source.cell_type==='markdown')return cell.querySelector('.nb-markdown h2')?.firstChild.textContent===source.heading
      && cell.querySelector('.nb-markdown p')?.textContent===source.paragraph;
    const editor=cell.querySelector('.nb-cell-edit-area'),output=cell.querySelector(':scope > .nb-outputs');
    const run=cell.querySelector('.nb-cell-run');
    return editor?.value===source.source && !editor.readOnly && run && !run.disabled
      && cell.querySelector('.nb-cell-edit-highlight code')?.textContent===source.source
      && output?.querySelector('.nb-outputs-body')?.textContent===source.output
      && output.classList.contains('nb-outputs-collapsed')===(index===1&&collapsed);
  });
}

export async function notebookViewActions(evaluate,workspaceRoot,samples,{typing=false}={}) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot))throw Error('Notebook viewing requires the disposable fixture');
  if(!Number.isInteger(samples)||samples<2)throw Error('Notebook viewing requires at least two samples');
  const expected={},files=[];
  for(const name of ['alpha','beta']) {
    const scope=join(workspaceRoot,name),file=join(scope,'notebooks/review.ipynb'),raw=await readFile(file,'utf8');
    files.push([file,raw]);
    const notebook=JSON.parse(raw);
    if(!Array.isArray(notebook.cells)||notebook.cells.length<2)throw Error('Notebook fixture is incomplete');
    expected[name]={scope,cells:notebook.cells.map((cell,index)=>{
      if(cell.id!==`${name}-cell-${index}` || cell.cell_type!==(index%2?'code':'markdown'))throw Error('Unexpected notebook cell identity');
      return {...cell,heading:`${name[0].toUpperCase()+name.slice(1)} cell ${index}`,
        paragraph:`Fixture formatted paragraph ${index}.`,output:cell.outputs?.map(o=>o.text).join('')};
    })};
  }
  await evaluate(`window.__notebookViewExpected=${JSON.stringify(expected)};window.__notebookViewReady=${notebookViewReady.toString()};`);
  const drafts=Object.fromEntries(Object.entries(expected).map(([name,value])=>[name,value.cells[1].source]));
  const actions=[];
  for(let i=0;i<samples;i++) {
    const name=i%2?'beta':'alpha',identity=`__notebookViewExpected[${JSON.stringify(name)}]`;
    const ready=options=>`__notebookViewReady(${identity},${JSON.stringify(options||{})})`;
    const toggle='#content [data-nb-toggle-code]',output='#content .nb-cell[data-cell-index="1"] .nb-outputs-toggle';
    actions.push(
      {kind:i<2?'workspace':'notebook-workspace-restore',target:name,selector:'.workspace-tab[data-workspace-id="'+name+'"]',ready:i<2
        ?`currentWorkspace?.path===${JSON.stringify(expected[name].scope)} && document.querySelector('#content [data-workspace-display-title]')?.textContent===${JSON.stringify(name[0].toUpperCase()+name.slice(1))}`:ready()},
      {kind:'notebook-open',target:name,selector:'.sidebar-file[data-open-file][data-filepath="notebooks/review.ipynb"]',ready:ready()},
      {kind:'notebook-hide-code',target:name,selector:toggle,ready:ready({codeHidden:true})},
      {kind:'notebook-show-code',target:name,selector:toggle,ready:ready()},
      {kind:'notebook-collapse-output',target:name,selector:output,ready:ready({collapsed:true})},
      {kind:'notebook-expand-output',target:name,selector:output,ready:ready()},
    );
    // These controls must never write or execute either notebook.
    actions.at(-1).expectedDocuments=files;
    if(typing) {
      const text=`\nfixture draft ${i+1} jqvxmb\n`;
      actions.at(-1).notebookTyping={before:drafts[name],text};
      drafts[name]+=text;
    }
  }
  if(typing)for(const name of ['alpha','beta'])actions.push({
    kind:'notebook-draft-restore',target:name,selector:'.workspace-tab[data-workspace-id="'+name+'"]',
    ready:`__notebookViewReady(__notebookViewExpected[${JSON.stringify(name)}])`,expectedDocuments:files,
  });
  return actions;
}
