// Native Assistant entry and view changes in the disposable navigation vault.
import {readFile} from 'node:fs/promises';
import {dirname,join,resolve} from 'node:path';

// A controlled overlap, not watcher/WebSocket delivery timing. Never delay a
// native click, alter readiness, mock a response, or disable normal polling.
export async function installAssistantRefreshStress(evaluate,workspaceRoot,delayMs) {
  if(!/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot))throw Error('Assistant refresh stress requires the disposable fixture');
  if(!Number.isInteger(delayMs)||delayMs<1||delayMs>1000)throw Error('Assistant refresh delay must be 1–1000 ms');
  await evaluate(`(()=>{
    const original=AssistantView.init,events=[];let generation=0;
    AssistantView.init=function(...args){
      const owner=++generation,event={started:performance.now(),delivered:false};events.push(event);
      const result=original.apply(this,args);
      setTimeout(()=>{
        event.fired=performance.now();
        if(owner!==generation||!document.body.classList.contains('assistant-active'))return;
        event.delivered=true;
        AssistantView.refresh({backgroundRefresh:true}).then(()=>event.completed=performance.now(),error=>event.error=String(error));
      },${delayMs});
      return result;
    };
    window.__assistantRefreshStress=()=>({delayMs:${delayMs},events});
  })()`);
}

export function assistantRefreshCoverage(rows,events) {
  return rows.filter(row=>row.kind==='assistant-open').map(row=>{
    const start=row.clock.source,end=start+row.ms;
    const deliveries=events.filter(event=>event.started>=start && event.started<=end
      && event.delivered && event.fired>=event.started && event.fired<=end && !event.error);
    const delivered=deliveries.length;
    // A late timer after the initial request would not test the targeted race.
    const initial=row.requests.find(request=>request.route==='/api/assistant');
    const overlapping=deliveries.filter(event=>initial && start+initial.start<=event.fired
      && start+initial.start+initial.ms>event.fired).length;
    const completed=deliveries.filter(event=>Number.isFinite(event.completed) && event.completed>=event.fired).length;
    return {sample:row.sample,delivered,overlapping,completed};
  });
}

export function assistantReady(expected,view) {
  if(!document.body.classList.contains('assistant-active') || currentWorkspace?.path!==expected.root)return false;
  const content=document.getElementById('content');
  if(content?.querySelector('[data-assistant-view].active')?.dataset.assistantView!==view)return false;
  const cardsMatch=(host,rows)=>{
    const cards=[...host.querySelectorAll('[data-assistant-document]')];
    return cards.length===rows.length && cards.every((card,index)=>{
      const row=rows[index],article=card.closest('[data-assistant-entry-wrap]');
      return card.dataset.assistantDocument===row.path && card.dataset.documentKind==='note'
        && article?.dataset.documentKey===row.path && article.dataset.assistantEntryWrap===row.path
        && card.querySelector('.assistant-row-title strong')?.textContent===row.title
        && card.querySelector('.assistant-row-tldr')?.textContent===row.tldr
        && card.querySelector('.assistant-work-status.empty')?.textContent==='No tasks'
        && article.querySelector('[data-star-path]')?.getAttribute('aria-pressed')===String(row.starred);
    });
  };
  if(view==='dashboard') {
    const sections=[...content.querySelectorAll('[data-dashboard-section]')];
    if(sections.length!==expected.sections.length)return false;
    return sections.every((section,index)=>{
      const target=expected.sections[index];
      return section.dataset.dashboardSection===target.id && section.getAttribute('aria-label')===target.title
        && section.querySelector('h2 small')?.textContent===String(target.rows.length)
        && cardsMatch(section,target.rows)
        && (section.querySelector('.assistant-section-overflow')?.textContent||'')===(target.overflow
          ?`${target.overflow} more match. Use Show filter to change the JSON item limit.`:'')
        && (!!section.querySelector('.assistant-empty')===!target.rows.length);
    });
  }
  const list=content.querySelector('[data-testid="assistant-list"]');
  const rows=view==='starred'?expected.documents.filter(row=>row.starred):expected.documents;
  return !!list && cardsMatch(list,rows) && content.querySelector('.assistant-filter-count')?.textContent===`${rows.length} item${rows.length===1?'':'s'}`;
}

export async function assistantActions(evaluate,workspaceRoot,samples,expected) {
  if(resolve(workspaceRoot)!==workspaceRoot || !/\/lab-navigation-[^/]+\/vault\/workspaces$/.test(workspaceRoot)
      || expected.root!==join(dirname(dirname(workspaceRoot)),'assistant'))throw Error('Assistant requires the disposable fixture');
  if(!Number.isInteger(samples)||samples<2||expected.documents.length<2)throw Error('Incomplete Assistant fixture');
  const files=await Promise.all(expected.documents.map(async row=>{
    const file=join(expected.root,row.path);
    return [file,await readFile(file,'utf8')];
  }));
  const newest=[...expected.documents].sort((a,b)=>b.created.localeCompare(a.created)||a.title.localeCompare(b.title));
  const starred=newest.filter(row=>row.starred);
  expected.sections=[
    {id:'priority',title:'Priority',rows:[],overflow:0},
    {id:'starred',title:'Starred',rows:starred.slice(0,10),overflow:Math.max(0,starred.length-10)},
    {id:'documents',title:'Documents',rows:newest.slice(0,20),overflow:Math.max(0,newest.length-20)},
  ];
  await evaluate(`window.__assistantExpected=${JSON.stringify(expected)};window.__assistantReady=${assistantReady.toString()};`);
  const actions=[];
  for(let i=0;i<samples;i++) {
    const name=i%2?'beta':'alpha';
    for(const view of ['dashboard','all','starred'])actions.push({
      kind:view==='dashboard'?'assistant-open':'assistant-view',target:view,
      selector:view==='dashboard'?'.workspace-tab[data-kind="assistant"]':`#content [data-assistant-view="${view}"]`,
      ready:`__assistantReady(__assistantExpected,${JSON.stringify(view)})`,
    });
    actions.push({kind:'workspace',target:name,selector:`.workspace-tab[data-workspace-id="${name}"]`,
      ready:`!document.body.classList.contains('assistant-active') && currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/'+name)} && document.querySelector('#content [data-workspace-display-title]')?.textContent===${JSON.stringify(name==='alpha'?'Alpha':'Beta')}`,
      expectedDocuments:files});
  }
  return actions;
}
