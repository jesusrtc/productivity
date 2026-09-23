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

export function assistantDetailReady(expected,view) {
  if(!document.body.classList.contains('assistant-active') || currentWorkspace?.path!==expected.root)return false;
  const modal=document.getElementById('assistantDocumentModal');
  if(!modal?.classList.contains('active') || modal.hasAttribute('aria-busy') || modal.querySelector('.assistant-document-error'))return false;
  const index=view==='dashboard',selected=index?expected.rows[0]:expected.rows.find(row=>row.view===view);
  if(!selected || document.getElementById('assistantModalTitle')?.textContent!==selected.title)return false;
  const nav=[...modal.querySelectorAll('#assistantDocumentNav [data-record-path]')];
  if(nav.length!==expected.rows.length || !nav.every((button,number)=>{
    const row=expected.rows[number];
    return button.dataset.recordPath===row.path && button.dataset.recordKind==='note'
      && button.querySelector('.assistant-record-title')?.textContent===row.title
      && button.classList.contains('active')===(!index && row===selected);
  }))return false;
  if(modal.querySelector('[data-record-index]')?.classList.contains('active')!==index)return false;
  if(localStorage.getItem(expected.storageKey)!==(index?'index':selected.path))return false;
  const host=document.getElementById('assistantModalDocument');
  if(!host)return false;
  if(host.querySelector('[data-document-tasks] .assistant-tasks-section-head h2 small')?.textContent!=='0')return false;
  if(!['assistantCopyPlain','assistantCopyRich'].every(id=>document.getElementById(id)?.disabled===false))return false;
  if(!window.__assistantTerminal?.ready())return false;
  if(index) {
    const buttons=[...host.querySelectorAll('[data-tab-dashboard-path]')];
    return buttons.length===expected.rows.length && buttons.every((button,number)=>
      button.dataset.tabDashboardPath===expected.rows[number].path
      && button.querySelector('span')?.textContent==='▤ '+expected.rows[number].title
      && button.querySelector('small')?.textContent==='No pending tasks');
  }
  return host.querySelector('#assistantModalMarkdown')?.textContent.trim()===selected.body.trim()
    && document.getElementById('assistantEditNote')?.hidden===false;
}

export function installAssistantTerminal(marker) {
  if(typeof window._termGuardViewportDisposal!=='function')throw Error('Missing native terminal lifecycle hook');
  const original=window._termGuardViewportDisposal,records=[];
  let latest;
  const text=xt=>{
    const buffer=xt.buffer.active;let value='';
    for(let row=buffer.viewportY;row<=buffer.baseY+buffer.cursorY;row++)
      value+=buffer.getLine(row)?.translateToString(true,0,row===buffer.baseY+buffer.cursorY?buffer.cursorX+1:undefined)||'';
    return value;
  };
  window._termGuardViewportDisposal=function(xt,...args){
    const result=original.call(this,xt,...args),record={renders:0,rendered:false};
    xt.onRender(range=>{
      if(!xt.element?.closest('#assistantDocumentTerminal .assistant-terminal-screen'))return;
      if(!record.renders){records.push(record);latest=new WeakRef(xt);}
      record.renders++;
      const b=xt.buffer.active,row=b.baseY+b.cursorY-b.viewportY;
      if(range.start<=row && range.end>=row && text(xt).endsWith(marker)){
        record.rendered=true;record.renderAt=performance.now();
      }
    });
    return result;
  };
  window.__assistantTerminal={
    ready(){
      const xt=latest?.deref(),host=document.getElementById('assistantDocumentTerminal'),status=host?.querySelector('[data-terminal-status]');
      return !!xt && !!host && !host.hidden && host.contains(xt.element) && records.at(-1)?.rendered
        && text(xt).endsWith(marker) && status?.textContent==='Running' && !status.classList.contains('error');
    },
    snapshot(){return {agent:'owned-echo-cli',socketMode:'private',marker,records,ready:this.ready()};},
  };
}

export async function assistantActions(evaluate,workspaceRoot,samples,expected,{details=false,terminal=null}={}) {
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
  let detail;
  if(details) {
    if(terminal?.agent!=='owned-echo-cli' || terminal.socketMode!=='private' || !/^detail-[a-f0-9]{12}$/.test(terminal.marker))throw Error('Document details require the owned echo terminal');
    await evaluate(`(${installAssistantTerminal.toString()})(${JSON.stringify(terminal.marker)})`);
    // Every seventieth fixture note is starred and owns two subtabs, so it is
    // present near the top of the normal Starred view without changing filters.
    const number=Math.floor((expected.notes.length-1)/70)*70,root=expected.notes[number],digits=String(number).padStart(4,'0');
    detail={root:expected.root,storageKey:'lab.assistant.last-tab.v1:'+expected.root+':'+root.id,
      rows:[{view:'root',path:root.path,title:root.title,body:root.body},...[0,1].map(child=>({
        view:'subtab-'+child,path:root.path+'#tab=fixture-tab-'+digits+'-'+child,
        title:'Reference '+digits+'-'+child,body:'Child body '+digits+'-'+child+'.\n'}))]};
    await evaluate(`window.__assistantDetailExpected=${JSON.stringify(detail)};window.__assistantDetailReady=${assistantDetailReady.toString()};`);
  }
  const actions=[];
  for(let i=0;i<samples;i++) {
    const name=i%2?'beta':'alpha';
    for(const view of ['dashboard','all','starred'])actions.push({
      kind:view==='dashboard'?'assistant-open':'assistant-view',target:view,
      selector:view==='dashboard'?'.workspace-tab[data-kind="assistant"]':`#content [data-assistant-view="${view}"]`,
      ready:`__assistantReady(__assistantExpected,${JSON.stringify(view)})`,
    });
    if(detail) {
      actions.push({kind:'assistant-document-open',target:detail.rows[0].path,
        selector:`#content [data-assistant-document="${detail.rows[0].path}"]`,
        ready:'__assistantDetailReady(__assistantDetailExpected,"dashboard")'});
      for(const row of detail.rows)actions.push({kind:row.view==='root'?'assistant-document-root':'assistant-document-subtab',target:row.path,
        selector:`#assistantDocumentNav [data-record-path="${row.path}"]`,
        ready:`__assistantDetailReady(__assistantDetailExpected,${JSON.stringify(row.view)})`});
      actions.push({kind:'assistant-document-dashboard',target:detail.rows[0].path,selector:'#assistantDocumentNav [data-record-index]',
        ready:'__assistantDetailReady(__assistantDetailExpected,"dashboard")'},
        {kind:'assistant-document-close',target:detail.rows[0].path,selector:'#assistantDocumentModal .assistant-modal-close',
        ready:'!document.getElementById("assistantDocumentModal")?.classList.contains("active") && __assistantReady(__assistantExpected,"starred")'});
    }
    actions.push({kind:'workspace',target:name,selector:`.workspace-tab[data-workspace-id="${name}"]`,
      ready:`!document.body.classList.contains('assistant-active') && currentWorkspace?.path===${JSON.stringify(workspaceRoot+'/'+name)} && document.querySelector('#content [data-workspace-display-title]')?.textContent===${JSON.stringify(name==='alpha'?'Alpha':'Beta')}`,
      expectedDocuments:files});
  }
  return actions;
}
