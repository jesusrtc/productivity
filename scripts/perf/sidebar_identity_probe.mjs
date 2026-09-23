// Compare detached sidebar construction only, after native actions finish.
// This isolates repeated attributes; it is not a cold-open or input metric.
import {writeFile} from 'node:fs/promises';

export async function compareSidebarIdentity(evaluate,path) {
  const result=await evaluate(`(async()=>{
    const entry=[..._sidebarMarkupCache.values()].at(-1);
    if(!entry)throw Error('No retained fixture sidebar');
    const compact=entry.markup;
    let restored=0;
    const repeated=compact.replace(/(<a class="sidebar-file[^"]*" data-filepath="([^"]*)" draggable="true")(?= data-entry-root=)/g,(_,row,path)=>{
      restored++;return row+' data-entry-kind="file" data-entry-path="'+path+'"';
    });
    if(!restored)throw Error('Fixture has no shared-identity rows');
    const a=document.createElement('template'),b=document.createElement('template');
    a.innerHTML=repeated;b.innerHTML=compact;
    for(const row of a.content.querySelectorAll('[data-open-file]')){
      row.removeAttribute('data-entry-kind');row.removeAttribute('data-entry-path');
    }
    if(!a.content.isEqualNode(b.content))throw Error('Comparison changed other sidebar content');
    const rows=[];
    for(let round=0;round<12;round++)for(const variant of round%2?['compact','repeated']:['repeated','compact']){
      await new Promise(resolve=>requestAnimationFrame(resolve));
      const start=performance.now();
      const built=_buildSidebarMarkupTemplate(variant==='compact'?compact:repeated,[],null,new Map());
      const parsed=performance.now();
      const clone=built.template.content.cloneNode(true);
      const cloned=performance.now();
      if(clone.querySelectorAll('*').length!==entry.elements)throw Error('Comparison lost elements');
      rows.push({round,variant,parse:parsed-start,clone:cloned-parsed,total:cloned-start});
    }
    return {measurement:'Detached full template construction and clone; no live mount or input',restored,
      chars:{compact:compact.length,repeated:repeated.length},elements:entry.elements,rows};
  })()`);
  await writeFile(path,JSON.stringify(result,null,2));
}
