(() => {
      const root = document.getElementById('lab-objectives-proposal');
      const find = name => root.querySelector('[data-' + name + ']');
      const channel = 'lab-objectives-demo-v1';
      let hydrated = false;
      const iconNames = {document:'file-text',assistant:'files',notebook:'notebook',link:'external-link',task:'square-check',file:'file-code',folder:'folder'};
      const objectives = [
        {id:'sms',name:'SMS recovery',purpose:'Restore reliable phone verification',color:'#58a6ff',selected:'phone-fix',selectedItem:'incident',draft:'',worktrees:[{id:'phone-fix',name:'sdui/fix-phone',repo:'client',color:'#58a6ff'},{id:'checkpoint',name:'checkpoint/verification',repo:'client',color:'#ff7b72'}],items:[
          {id:'incident',kind:'document',title:'Incident notes',scope:null,body:'Investigate failed phone verification and record the recovery plan.'},
          {id:'track',kind:'assistant',title:'Investigation — Track 3',scope:null,body:'Linked Assistant document. Its existing content and tasks remain owned by Assistant.'},
          {id:'volume',kind:'notebook',title:'Verification volume.ipynb',scope:null},
          {id:'thread',kind:'link',title:'Malformed-phone discussion',scope:null,url:'https://example.com/discussion'},
          {id:'channel',kind:'link',title:'Incident channel',scope:null,url:'https://example.com/channel'},
          {id:'ticket',kind:'link',title:'Ticket — Unparseable phone',scope:null,url:'https://example.com/ticket'},
          {id:'validate',kind:'task',title:'Validate phone parsing',scope:null,checks:[{title:'Reproduce malformed input',done:true},{title:'Verify recovery behavior',done:true}],detail:'incident'},
          {id:'rollout',kind:'task',title:'Review rollout results',scope:null,checks:[{title:'Compare verification rates',done:true}],done:true},
          {id:'fallback',kind:'task',title:'Confirm the recovery fallback',scope:null,checks:[],done:true},
          {id:'regression',kind:'task',title:'Record regression coverage',scope:null,checks:[{title:'Cover malformed phone numbers',done:true},{title:'Cover the recovery route',done:true}]},
          {id:'release',kind:'task',title:'Release the parsing change',scope:null,checks:[],done:false},
          {id:'monitor',kind:'task',title:'Monitor recovery after rollout',scope:null,checks:[],done:false},
          {id:'prs',kind:'link',title:'PRs for this branch',scope:'phone-fix',url:'https://example.com/pull-requests'}],recent:['api/phone_parser.py','tests/test_phone_parser.py'],files:['api/','applications/','build/','client/']},
        {id:'api',name:'API cleanup',purpose:'Simplify the public API',color:'#bc8cff',selected:'api-main',selectedItem:'api-plan',draft:'',worktrees:[{id:'api-main',name:'cleanup/routes',repo:'service',color:'#bc8cff'},{id:'api-tests',name:'cleanup/contract-tests',repo:'service',color:'#e3b341'}],items:[{id:'api-plan',kind:'document',title:'API cleanup plan',scope:null,body:'Review route behavior, remove redundant paths, and document the supported API.'},{id:'api-reference',kind:'link',title:'API reference',scope:null,url:'https://example.com/api'},{id:'api-task',kind:'task',title:'Review compatibility',scope:null,checks:[{title:'List existing consumers',done:true},{title:'Verify current contracts',done:false}],detail:'api-plan'}],recent:['service/routes.py','tests/test_contracts.py'],files:['service/','tests/','README.md']},
        {id:'latency',name:'Latency study',purpose:'Understand response time',color:'#ffa657',selected:'timing',selectedItem:'measurements',draft:'',worktrees:[{id:'timing',name:'perf/timing',repo:'service',color:'#ffa657'}],items:[{id:'measurements',kind:'notebook',title:'Measurements.ipynb',scope:null},{id:'latency-task',kind:'task',title:'Compare response times',scope:null,checks:[{title:'Capture a baseline',done:true},{title:'Repeat the measurements',done:false}],detail:'measurements'}],recent:['scripts/benchmark.py'],files:['scripts/','results/']},
        {id:'docs',name:'Documentation',purpose:'Improve onboarding',color:'#39c5cf',selected:'docs-main',selectedItem:'onboarding',draft:'',worktrees:[{id:'docs-main',name:'docs/onboarding',repo:'client',color:'#39c5cf'}],items:[{id:'onboarding',kind:'document',title:'Onboarding guide',scope:null,body:'Document the setup and first useful workflow.'}],recent:['docs/setup.md'],files:['docs/','README.md']}
      ];
      const terminals = [{id:'t1',objective:'sms',tree:'phone-fix',name:'Parsing fix',linked:'validate',state:'working',draft:''},{id:'t2',objective:'sms',tree:'phone-fix',name:'Test runner',linked:null,state:'ready',draft:''},{id:'t3',objective:'sms',tree:'checkpoint',name:'Investigation',linked:'incident',state:'idle',draft:''},{id:'t4',objective:'api',tree:'api-main',name:'Route review',linked:'api-plan',state:'working',draft:''},{id:'t5',objective:'api',tree:'api-tests',name:'Contract tests',linked:null,state:'idle',draft:''},{id:'t6',objective:'latency',tree:'timing',name:'Benchmark',linked:'measurements',state:'ready',draft:''},{id:'t7',objective:'docs',tree:'docs-main',name:'Guide edits',linked:'onboarding',state:'idle',draft:''}];
      const config = {groupResources:false,terminalVisibility:'all'};
      let focused = ['sms','api','latency'], selected = 'sms', activeTerminal = 't1', serial = 10, recentMode = 'Uncommitted';
      const openFolders = new Set();
      const hoverTimers = new Map();
      let shelfTimer;
      const hoverDelay = 1500, shelfDuration = 5 * 60 * 1000;
      const palettes = [['#58a6ff','#ff7b72','#3fb950','#d29922'],['#bc8cff','#e3b341','#56d6c0','#ff9bce'],['#ffa657','#f778ba','#a9d14c','#b3a456'],['#39c5cf','#e86b8d','#d1bcff','#acd68f']];
      objectives.forEach((o,index)=>{
        o.palette=palettes[index];
        o.worktrees.forEach(tree=>seedFiles(o,tree));
        o.items.filter(i=>i.kind==='notebook').forEach(i=>{i.source='rates = [0.96, 0.98, 0.99]\nmean_rate = sum(rates) / len(rates)\nprint(f"Mean verification rate: {mean_rate:.1%}")';i.output='Mean verification rate: 97.7%';});
        normalizeObjective(o);
        o.items.filter(i=>i.kind==='task').forEach(task=>{task.due=dateOffset(index===1?2:index===2?-1:6);});
      });
      terminals.forEach(t=>t.logs=['Objectives demo terminal · help lists simulated commands.']);
      const fresh = JSON.parse(JSON.stringify(snapshot()));

      function snapshot() {return {version:1,objectives,terminals,config,focused,selected,activeTerminal,serial,recentMode,openFolders:[...openFolders]};}
      function persist() {if(hydrated&&window.parent!==window)window.parent.postMessage({channel,type:'save',state:snapshot()},'*');}
      function dateOffset(offset) {const day=new Date();day.setDate(day.getDate()+offset);return localDate(day);}
      function localDate(day=new Date()) {return day.getFullYear()+'-'+String(day.getMonth()+1).padStart(2,'0')+'-'+String(day.getDate()).padStart(2,'0');}
      function dayNumber(value) {if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;return Date.parse(value+'T00:00:00Z')/86400000;}
      function taskComplete(task) {return task.checks.length?task.checks.every(c=>c.done):task.done===true;}
      function taskProgress(o) {
        const tasks=o.items.filter(i=>i.kind==='task'),done=tasks.filter(taskComplete).length;
        const deadlines=tasks.flatMap(t=>taskComplete(t)?[]:[t.due,...t.checks.filter(c=>!c.done).map(c=>c.due||t.due)]).map(dayNumber).filter(n=>n!==null);
        const days=deadlines.map(n=>n-dayNumber(localDate()));
        const status=tasks.length&&done===tasks.length?'complete':days.some(d=>d<0)?'overdue':days.some(d=>d<=2)?'risk':'track';
        return {done,total:tasks.length,status,label:{complete:'All complete',overdue:'Past due',risk:'At risk · due within 2 days',track:tasks.length?'On track':'No tasks yet'}[status]};
      }
      function progressBadge(o) {const p=taskProgress(o),el=element('span','ob-progress ob-progress-'+p.status,p.done+'/'+p.total);el.title=p.label;el.setAttribute('aria-label',p.done+' of '+p.total+' tasks complete · '+p.label);return el;}
      function taskDocument(o) {
        let doc=o.items.find(i=>i.taskDocument&&i.kind==='document');
        if(!doc){doc={id:o.id+'-task-details',kind:'document',title:'Task details.md',scope:null,body:'# '+o.name+' tasks\n\nEach task and subtask has its own document subtab. Open a task’s document button to read its context.',tabs:[],taskDocument:true};o.items.push(doc);}
        return doc;
      }
      function ensureDetails(o,task,entry=task) {
        let doc=o.items.find(i=>i.id===entry.detail&&i.kind==='document');
        if(!doc){doc=entry===task?taskDocument(o):(o.items.find(i=>i.id===task.detail&&i.kind==='document')||taskDocument(o));entry.detail=doc.id;}
        doc.tabs ||= [];
        let tab=doc.tabs.find(t=>t.id===entry.tab);
        if(!tab){tab={id:entry.id+'-details',title:entry.title,body:'# '+entry.title+'\n\nObjective: '+o.purpose+'\n\n## Outcome\nDescribe the expected result and the evidence needed to complete this '+(entry===task?'task':'subtask')+'.\n\n## Notes\nRecord findings, decisions, and next steps here.'};doc.tabs.push(tab);entry.tab=tab.id;}
      }
      function normalizeObjective(o) {
        o.view ||= 'tasks';o.selectedTab ||= null;o.tabShelf ||= {};o.palette ||= [];
        o.items.filter(i=>i.kind==='document'||i.kind==='assistant'||i.kind==='file'&&i.title.endsWith('.md')).forEach(i=>{
          if(!Array.isArray(i.tabs))i.tabs=i.id==='incident'?[{id:'timeline',title:'Timeline',body:'# Incident timeline\n\n## Detection\nPhone verification failures increased after the rollout.\n\n## Recovery\nThe parsing fix restores the fallback flow.'},{id:'recovery-plan',title:'Recovery plan',body:'# Recovery plan\n\n- Reproduce the malformed input.\n- Verify the fallback.\n- Check verification volume.'}]:i.kind==='assistant'?[{id:'analysis',title:'Analysis',body:'# Investigation — Analysis\n\nSimulated reference to an Assistant subtab. The original document remains owned by Assistant.'},{id:'follow-up',title:'Follow-up',body:'# Follow-up\n\nReview the findings with the recovery team.'}]:[];
        });
        o.items.filter(i=>i.kind==='task').forEach(task=>{
          task.done=task.done===true;task.checks ||= [];task.due ||= '';
          ensureDetails(o,task);
          task.checks.forEach((c,index)=>{c.id ||= task.id+'-todo-'+index;c.due ||= '';ensureDetails(o,task,c);});
        });
        o.items.filter(i=>i.kind==='notebook').forEach(seedNotebook);
      }
      function seedNotebook(item) {
        if(Array.isArray(item.cells))return;
        item.cells=[{id:item.id+'-intro',kind:'markdown',source:'# '+item.title.replace(/\.ipynb$/,'')+'\n\nCompare phone verification across entry points and record the recovery signal.'},
          {id:item.id+'-mean',kind:'code',source:item.source||'print(1 + 1)',output:item.output||'',execution:item.output?1:null},
          {id:item.id+'-distribution',kind:'code',source:'entry_points = ["SMS", "Recovery", "Settings"]\nvalues = [96, 98, 99]\n# Display a table and chart for these verification rates',output:'Verification rate by entry point',execution:2,table:[['SMS',96],['Recovery',98],['Settings',99]]},
          {id:item.id+'-notes',kind:'markdown',source:'## Interpretation\n\nRecovery remains available across all three entry points. Repeat this check after rollout.'}];
      }
      function seedFiles(o,tree) {
        const paths=[...new Set([...o.recent,'README.md',tree.repo==='client'?'api/phone_parser.py':'service/routes.py',tree.repo==='client'?'tests/test_phone_parser.py':'tests/test_contracts.py'])];
        paths.forEach((path,index)=>o.items.push({id:'file-'+tree.id+'-'+index,kind:'file',title:path,scope:tree.id,listed:false,body:path.endsWith('.md')?'# '+o.name+'\n\nNotes for '+tree.name+'.':path.endsWith('.py')?'# Simulated file in '+tree.name+'\n\ndef verify(value):\n    return bool(value)\n':'Simulated file content.',updated:Date.now()}));
      }
      function validState(state) {
        if(state?.version!==1||!Array.isArray(state.objectives)||!state.objectives.length||state.objectives.length>100||!Array.isArray(state.terminals)||!Array.isArray(state.focused)||state.focused.length>3||!state.focused.length)return false;
        const ids=new Set();
        for(const o of state.objectives){
          if(typeof o.id!=='string'||ids.has(o.id)||typeof o.name!=='string'||typeof o.color!=='string'||!Array.isArray(o.worktrees)||!Array.isArray(o.items)||!Array.isArray(o.files)||!Array.isArray(o.recent))return false;
          ids.add(o.id);const treeIds=new Set(o.worktrees.map(t=>t.id));
          if(o.worktrees.some(t=>typeof t.name!=='string'||typeof t.color!=='string'||typeof t.repo!=='string')||o.selected&&!treeIds.has(o.selected))return false;
          if(o.items.some(i=>typeof i.id!=='string'||typeof i.title!=='string'||!Object.hasOwn(iconNames,i.kind)||i.scope&&!treeIds.has(i.scope)||i.kind==='task'&&(!Array.isArray(i.checks)||i.checks.some(c=>typeof c.title!=='string'||typeof c.done!=='boolean'))))return false;
          if(o.items.some(i=>i.tabs!==undefined&&(!Array.isArray(i.tabs)||i.tabs.some(t=>typeof t.id!=='string'||typeof t.title!=='string'||typeof t.body!=='string'))||i.cells!==undefined&&(!Array.isArray(i.cells)||i.cells.some(c=>typeof c.id!=='string'||!['code','markdown'].includes(c.kind)||typeof c.source!=='string'||c.table!=null&&(!Array.isArray(c.table)||c.table.some(r=>!Array.isArray(r)||typeof r[0]!=='string'||!Number.isFinite(r[1])))))))return false;
          if(o.tabShelf!==undefined&&(!o.tabShelf||typeof o.tabShelf!=='object'||Array.isArray(o.tabShelf)||Object.values(o.tabShelf).some(s=>!s||!Number.isFinite(s.until)||!Array.isArray(s.pinned)||s.pinned.some(id=>typeof id!=='string'))))return false;
        }
        if(new Set(state.focused).size!==state.focused.length||state.focused.some(id=>!ids.has(id))||!state.focused.includes(state.selected))return false;
        return state.terminals.every(t=>typeof t.id==='string'&&typeof t.name==='string'&&state.objectives.some(o=>o.id===t.objective&&(t.tree==='objective'||o.worktrees.some(tree=>tree.id===t.tree))));
      }
      function restore(state) {if(!validState(state))return false;objectives.splice(0,objectives.length,...state.objectives);terminals.splice(0,terminals.length,...state.terminals);config.groupResources=state.config?.groupResources===true;config.terminalVisibility=state.config?.terminalVisibility==='selected'?'selected':'all';focused=[...state.focused];selected=state.selected;activeTerminal=state.activeTerminal;serial=Number.isSafeInteger(state.serial)?state.serial:100;recentMode=state.recentMode||'Uncommitted';openFolders.clear();(state.openFolders||[]).forEach(id=>openFolders.add(id));objectives.forEach(normalizeObjective);return true;}
      window.addEventListener('message',event=>{if(event.source!==window.parent||event.data?.channel!==channel||event.data.type!=='hydrate'||hydrated)return;restore(event.data.state);hydrated=true;render();});
      const objective = () => objectives.find(item => item.id === selected);
      function element(tag, className, content) { const el=document.createElement(tag); if(className) el.className=className; if(content!==undefined) el.textContent=content; return el; }
      function icon(name) { const el=element('span','ob-icon',({'target':'◎','git-branch':'⑂','file-text':'▤','files':'▥','notebook':'▦','terminal':'›_','external-link':'↗','square-check':'☑','file-code':'◇','folder':'▸'})[name]||'◇');el.setAttribute('aria-hidden','true');return el; }
      function button(label, className, action) { const el=element('button',className,label); el.type='button'; el.onclick=action; return el; }
      function message(text) { find('message').textContent=text; }
      function refreshIcons() {}
      function todoCount(o) { return o.items.filter(i=>i.kind==='task').reduce((n,i)=>n+(i.checks.length?i.checks.filter(c=>!c.done).length:Number(!taskComplete(i))),0); }
      function showTasks(o=objective()) {o.view='tasks';o.selectedTab=null;render();}
      function switchObjective(id) { selected=id; const o=objective();o.view='tasks';o.selectedTab=null; const t=terminals.find(t=>t.objective===id&&t.tree===o.selected)||terminals.find(t=>t.objective===id); activeTerminal=t?t.id:null; find('dialog').hidden=true; render(); message(o.name+' · '+todoCount(o)+' open to-dos · '+o.worktrees.length+' associated worktrees'); }
      function attachDrop(el, type, action) {
        el.ondragover=e=>{if(e.dataTransfer.types.includes(type)){e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect='link';el.classList.add('ob-drop');}};
        el.ondragleave=()=>el.classList.remove('ob-drop');
        el.ondrop=e=>{el.classList.remove('ob-drop');const id=e.dataTransfer.getData(type);if(id){e.preventDefault();e.stopPropagation();action(id);}};
      }
      function renderFocus() {
        const host=find('focus'); host.replaceChildren();
        const title=element('div','ob-section-heading');title.append(element('span','','OBJECTIVES · 3 IN FOCUS'));const add=button('+','ob-quiet',focusDialog);add.setAttribute('aria-label','Choose another objective');title.append(add);host.append(title);
        focused.forEach(id=>{const o=objectives.find(o=>o.id===id);const b=button('', 'ob-focus-slot',()=>switchObjective(id));b.style.setProperty('--objective-color',o.color);b.setAttribute('aria-pressed',id===selected);b.setAttribute('aria-label','Open objective '+o.name);b.append(icon('target'),element('span','ob-focus-name',o.name),progressBadge(o));host.append(b);});
      }
      function heading(host,label,action) {const row=element('div','ob-section-heading');row.append(element('span','',label));if(action){const add=button('+','ob-quiet',action);add.setAttribute('aria-label','Add to '+label.toLowerCase());row.append(add);}host.append(row);}
      function resourceTarget(o,ref) {const [id,tabId]=ref.split('::');const item=o.items.find(i=>i.id===id);return item?{item,tab:item.tabs?.find(t=>t.id===tabId)}:null;}
      function openResource(o,item,tab=null) {o.view=item.kind==='task'?'tasks':'resource';o.selectedItem=item.id;o.selectedTab=tab?.id||null;if(item.scope)o.selected=item.scope;if(tab)retainTabs(o,item);render();}
      function resourceRow(item,o,tab=null) {
        const row=button('','ob-resource'+(tab?' ob-subtab':''),()=>openResource(o,item,tab));row.dataset.item=item.id;if(tab)row.dataset.tab=tab.id;row.dataset.selected=o.view==='resource'&&o.selectedItem===item.id&&(o.selectedTab||null)===(tab?.id||null);row.draggable=true;row.setAttribute('aria-label',tab?'Open subtab '+tab.title+' in '+item.title:item.title+' · '+item.kind);row.title=tab?item.title+' / '+tab.title:'Drag onto a worktree to limit visibility';
        row.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-item',item.id+(tab?'::'+tab.id:''));e.dataTransfer.effectAllowed='link';};row.ondragend=()=>root.querySelectorAll('.ob-drop').forEach(el=>el.classList.remove('ob-drop'));
        row.append(icon(tab?'file-text':iconNames[item.kind]||'file-text'),element('span','ob-label',tab?tab.title:item.title));
        if(item.kind==='assistant'&&!tab)row.append(element('span','ob-kind','Assistant'));
        attachDrop(row,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id);if(t&&t.objective===o.id){t.linked=item.id;t.linkedTab=tab?.id||null;render();message('Linked '+t.name+' to '+(tab?.title||item.title)+' · launch folder kept');}else{message('Choose a terminal in '+o.name+' to link this resource');}});
        return row;
      }
      function retainTabs(o,item) {const state=o.tabShelf[item.id] ||= {until:0,pinned:[]};state.until=Date.now()+shelfDuration;state.pinned ||= [];scheduleShelfExpiry();}
      function scheduleShelfExpiry() {
        clearTimeout(shelfTimer);const now=Date.now(),deadlines=objectives.flatMap(o=>Object.values(o.tabShelf||{}).map(s=>s.until)).filter(t=>t>now);
        if(deadlines.length)shelfTimer=setTimeout(()=>{renderOverview();persist();scheduleShelfExpiry();},Math.max(1,Math.min(...deadlines)-now));
      }
      function subtabList(wrapper,item,o) {
        let list=wrapper.querySelector('.ob-subtabs');if(!list){list=element('div','ob-subtabs');wrapper.append(list);}list.replaceChildren();
        const state=o.tabShelf[item.id]||{until:0,pinned:[]},visible=item.tabs.filter(tab=>state.until>Date.now()||state.pinned?.includes(tab.id));
        visible.forEach(tab=>{const line=element('div','ob-subtab-line'),pin=button(state.pinned.includes(tab.id)?'◆':'◇','ob-pin',()=>{const shelf=o.tabShelf[item.id] ||= {until:0,pinned:[]};if(shelf.pinned.includes(tab.id))shelf.pinned=shelf.pinned.filter(id=>id!==tab.id);else shelf.pinned.push(tab.id);subtabList(wrapper,item,o);persist();});pin.setAttribute('aria-label','Pin subtab '+tab.title);pin.setAttribute('aria-pressed',state.pinned.includes(tab.id));pin.title=state.pinned.includes(tab.id)?'Pinned · click to unpin':'Keep in sidebar after five minutes';line.append(resourceRow(item,o,tab),pin);list.append(line);});
      }
      function documentRow(item,o) {
        if(!item.tabs?.length)return resourceRow(item,o);
        const wrapper=element('div','ob-document-group'),head=element('div','ob-resource-head'),expand=button('⌄','ob-expand',()=>{retainTabs(o,item);subtabList(wrapper,item,o);persist();});expand.setAttribute('aria-label','Show subtabs for '+item.title);expand.title='Hover for 1.5 seconds, or click to show subtabs';head.append(resourceRow(item,o),expand);wrapper.append(head);subtabList(wrapper,item,o);
        wrapper.onmouseenter=()=>{clearTimeout(hoverTimers.get(wrapper));hoverTimers.set(wrapper,setTimeout(()=>{hoverTimers.delete(wrapper);if(!wrapper.isConnected||selected!==o.id)return;retainTabs(o,item);subtabList(wrapper,item,o);persist();message('Subtabs stay here for five minutes. Pin a subtab to keep it.');},hoverDelay));};
        wrapper.onmouseleave=()=>{clearTimeout(hoverTimers.get(wrapper));hoverTimers.delete(wrapper);};return wrapper;
      }
      function listResources(host,items,o) {const list=element('div','ob-list');items.forEach(item=>list.append(documentRow(item,o)));host.append(list);}
      function renderOverview() {
        const host=find('overview'),o=objective();host.replaceChildren();
        hoverTimers.forEach(clearTimeout);hoverTimers.clear();
        const overviewHeader=element('div','ob-section-heading');overviewHeader.append(element('span','',o.name.toUpperCase()),button('Settings','ob-quiet',settingsDialog));host.append(overviewHeader);
        const shared=element('section');shared.setAttribute('aria-label','Objective-wide resources');attachDrop(shared,'application/x-objective-item',ref=>{const target=resourceTarget(o,ref);if(target){target.item.scope=null;render();message(target.item.title+' now appears across '+o.name);}});
        const general=o.items.filter(i=>!i.scope&&i.kind!=='task'&&i.listed!==false);
        if(config.groupResources){heading(shared,'DOCUMENTS & LINKS',()=>itemDialog());listResources(shared,general,o);}
        else {heading(shared,'DOCUMENTS & NOTEBOOKS',()=>itemDialog('document'));listResources(shared,general.filter(i=>i.kind!=='link'),o);heading(shared,'LINKS',()=>itemDialog('link'));listResources(shared,general.filter(i=>i.kind==='link'),o);}
        const tasks=button('','ob-resource ob-tasks-entry',()=>showTasks(o));tasks.setAttribute('aria-label','Open tasks for '+o.name);tasks.dataset.selected=o.view==='tasks';tasks.append(icon('square-check'),element('span','ob-label','Tasks'),progressBadge(o));shared.append(tasks);host.append(shared);
        heading(host,'WORKTREES',worktreeDialog);const trees=element('div','ob-list');
        o.worktrees.forEach(tree=>{const b=button('','ob-worktree',()=>{o.selected=tree.id;render();message(tree.name+' selected · objective resources remain visible');});b.style.setProperty('--tree-color',tree.color);b.setAttribute('aria-pressed',tree.id===o.selected);b.setAttribute('aria-label','Select worktree '+tree.name);b.append(icon('git-branch'),element('span','ob-label',tree.name),element('span','ob-kind',tree.repo));attachDrop(b,'application/x-objective-item',ref=>{const target=resourceTarget(o,ref);if(target){target.item.scope=tree.id;o.selected=tree.id;render();message(target.item.title+' now appears only when '+tree.name+' is selected');}});trees.append(b);});host.append(trees);
        const scoped=o.items.filter(i=>i.scope===o.selected&&i.listed!==false&&i.kind!=='task');if(scoped.length){heading(host,'FOR THIS WORKTREE',()=>itemDialog('link',o.selected));listResources(host,scoped,o);}
        heading(host,'RECENTLY UPDATED');const filters=element('div','ob-filters');['15 min','1 hour','24 hours','Uncommitted','vs main'].forEach(mode=>{const b=button(mode,'',()=>{recentMode=mode;renderOverview();persist();});b.setAttribute('aria-pressed',mode===recentMode);filters.append(b);});host.append(filters);
        const tree=o.worktrees.find(t=>t.id===o.selected);if(!tree){host.append(element('div','ob-muted','Associate a worktree to browse its files.'));return;}
        const files=o.items.filter(i=>i.scope===tree.id&&i.listed===false);const recent=files.filter(i=>i.updated).sort((a,b)=>b.updated-a.updated).slice(0,recentMode==='vs main'?2:recentMode==='15 min'?1:4);
        recent.forEach(item=>host.append(fileButton(item.title,o,tree)));
        heading(host,'FILES · '+tree.name,()=>itemDialog('file',tree.id));
        const folders=[...new Set(files.filter(i=>i.title.includes('/')).map(i=>i.title.split('/')[0]+'/'))].sort();
        folders.forEach(folder=>{const id=o.id+'/'+tree.id+'/'+folder;const b=button('','ob-file',()=>{if(openFolders.has(id))openFolders.delete(id);else openFolders.add(id);renderOverview();persist();});b.setAttribute('aria-expanded',openFolders.has(id));b.setAttribute('aria-label','Folder '+folder);b.append(icon('folder'),element('span','',folder));host.append(b);if(openFolders.has(id))files.filter(i=>i.title.startsWith(folder)).forEach(i=>{const file=fileButton(i.title,o,tree);file.classList.add('ob-file-child');host.append(file);});});
        files.filter(i=>!i.title.includes('/')).forEach(i=>host.append(fileButton(i.title,o,tree)));
      }
      function fileButton(path,o,tree) {
        const getItem=()=>o.items.find(i=>i.title===path&&i.scope===tree.id&&i.listed===false);
        if(getItem()?.tabs?.length)return documentRow(getItem(),o);
        const b=button('','ob-file',()=>openResource(o,getItem()));b.append(icon(path.endsWith('/')?'folder':'file-code'),element('span','',path));b.title=tree.repo+' / '+tree.name+' / '+path;
        b.draggable=true;b.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-item',getItem().id);e.dataTransfer.effectAllowed='link';};
        attachDrop(b,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id);if(t&&t.objective===o.id){t.linked=getItem().id;t.linkedTab=null;render();message('Linked '+t.name+' to '+path+' · launch folder kept');}else message('Choose a terminal in '+o.name+' to link this file');});return b;
      }
      function renderReader() {
        const host=find('reader'),o=objective();host.replaceChildren();
        if(o.view==='tasks'){renderTasks(host,o);return;}
        const item=o.items.find(i=>i.id===o.selectedItem)||o.items.find(i=>i.kind!=='task');if(!item){host.append(element('p','ob-muted','Choose or create a document, notebook, or link.'));return;}
        if(item.kind==='task'){o.view='tasks';renderTasks(host,o);return;}
        const tab=item.tabs?.find(t=>t.id===o.selectedTab),content=tab||item;
        const top=element('div','ob-reader-head');top.append(element('h2','',content.title));top.append(button(tab?'Rename subtab':'Rename','ob-quiet',()=>tab?renameSubtabDialog(item,tab):renameDialog(item)));host.append(top);
        const trail=element('div','ob-breadcrumb');trail.append(button('← Tasks','ob-quiet',()=>showTasks(o)),element('span','ob-muted',o.name+' / '+(item.scope?o.worktrees.find(t=>t.id===item.scope).name:'Objective')+(tab?' / '+item.title:'')));host.append(trail);
        if(item.listed!==false){const visibility=element('label','ob-visibility','Visible in '),selector=element('select');selector.setAttribute('aria-label','Resource visibility');[{id:'',name:'Whole objective'},...o.worktrees].forEach(t=>{const opt=element('option','',t.name);opt.value=t.id;selector.append(opt);});selector.value=item.scope||'';selector.onchange=()=>{item.scope=selector.value||null;render();message(item.scope?'Resource scoped to the selected worktree':'Resource visible throughout the objective');};visibility.append(selector);host.append(visibility);}
        if(item.kind==='notebook')renderNotebook(host,item);
        else if(item.kind==='link')host.append(element('p','',item.title),element('p','ob-muted',item.url),element('p','ob-muted','External link preview'));
        else {
          const preview=element('article','ob-document-preview');if(item.kind==='file'&&!item.title.endsWith('.md')&&!tab)preview.append(element('pre','',content.body||''));else renderMarkdown(preview,content.body||'No notes yet.');host.append(preview);
          if(item.kind==='assistant')host.append(element('p','ob-muted','Simulated Assistant reference · original content stays in Assistant.'));
          else {
            const edit=button(content.editing?'Done editing':'Edit content','ob-action',()=>{content.editing=!content.editing;renderReader();persist();});host.append(edit);
            if(content.editing){const editor=element('textarea','ob-editor');editor.setAttribute('aria-label',tab?'Edit simulated subtab content':'Edit simulated file content');editor.value=content.body||'';editor.oninput=()=>{content.body=editor.value;item.updated=Date.now();persist();};host.append(editor);}
          }
          if(!tab&&item.tabs?.length){heading(host,'SUBTABS');const list=element('div','ob-list');item.tabs.forEach(t=>list.append(button(t.title,'ob-resource',()=>openResource(o,item,t))));host.append(list);}
        }
        const linked=terminals.filter(t=>t.objective===o.id&&t.linked===item.id&&(t.linkedTab||null)===(tab?.id||null));if(linked.length){host.append(element('h3','','Linked terminals'));linked.forEach(t=>host.append(button(t.name,'ob-resource',()=>selectTerminal(t))));}
        const actions=element('div','ob-reader-actions');actions.append(button('Link terminal','ob-action',()=>linkTerminalDialog(item,tab)));if((item.kind==='document'||item.kind==='file'&&item.title.endsWith('.md'))&&!tab)actions.append(button('+ Subtab','ob-action',()=>subtabDialog(item)));if(!tab)actions.append(button('Delete item','ob-quiet',()=>deleteDialog(item)));host.append(actions);
      }
      function renderTasks(host,o) {
        const top=element('div','ob-reader-head');top.append(element('h2','','Tasks'),button('+ Task','ob-action',()=>itemDialog('task')));host.append(top,element('p','ob-muted',o.name+' · '+(o.purpose||'Define the outcome for this objective.')));
        const summary=element('div','ob-task-summary');summary.append(progressBadge(o),element('span','',taskProgress(o).label));host.append(summary);
        const list=element('div','ob-task-list');o.items.filter(i=>i.kind==='task').forEach(task=>{list.append(taskLine(o,task,task));task.checks.forEach(check=>list.append(taskLine(o,task,check)));});host.append(list);
        if(!list.childElementCount)host.append(element('p','ob-muted','Add a task to start. Its details document and subtab are created with it.'));
        host.append(element('p','ob-task-legend','▤ opens the task’s document subtab. Dates apply to unfinished work; subtasks inherit their parent’s deadline until you set one.'));
      }
      function taskLine(o,task,entry) {
        const child=entry!==task,row=element('div','ob-task-row'+(child?' ob-task-child':'')),check=element('input');row.dataset.task=entry.id;check.type='checkbox';check.checked=child?entry.done:taskComplete(task);check.setAttribute('aria-label','Complete '+(child?'subtask ':'task ')+entry.title);check.onchange=()=>{entry.done=check.checked;if(!child)task.checks.forEach(c=>c.done=check.checked);render();};
        const title=element('span','ob-task-title',entry.title);title.title=entry.title;title.dataset.done=check.checked;title.draggable=true;title.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-item',child?entry.detail+'::'+entry.tab:task.id);e.dataTransfer.effectAllowed='link';};
        const doc=o.items.find(i=>i.id===entry.detail),tab=doc?.tabs.find(t=>t.id===entry.tab),details=button('▤','ob-task-doc',()=>openResource(o,doc,tab));details.setAttribute('aria-label','Open details for '+entry.title);details.title=doc.title+' / '+tab.title;
        const due=element('input','ob-task-due');due.type='date';due.value=entry.due||'';due.setAttribute('aria-label','Due date for '+entry.title);due.title=child&&!entry.due&&task.due?'Inherits '+task.due:'Due date';due.onchange=()=>{entry.due=due.value;render();};const days=dayNumber(entry.due||task.due);if(!check.checked&&days!==null)due.dataset.status=days<dayNumber(localDate())?'overdue':days<=dayNumber(localDate())+2?'risk':'track';
        const actions=element('div','ob-task-actions'),edit=button('⋯','ob-quiet',()=>taskEditDialog(task,entry));edit.setAttribute('aria-label','Edit '+entry.title);actions.append(edit);if(!child){const add=button('+','ob-quiet',()=>todoDialog(task));add.setAttribute('aria-label','Add subtask to '+task.title);actions.append(add);}
        row.append(check,title,details,due,actions);attachDrop(row,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id&&t.objective===o.id);if(t){t.linked=child?doc.id:task.id;t.linkedTab=child?tab.id:null;render();}});return row;
      }
      function renderMarkdown(host,source) {
        let list=null,code=null;source.split('\n').forEach(line=>{if(line.startsWith('```')){if(code){host.append(code);code=null;}else code=element('pre','ob-markdown-code','');list=null;return;}if(code){code.textContent+=line+'\n';return;}const headingMatch=line.match(/^(#{1,3})\s+(.+)/);if(headingMatch){host.append(element('h'+(headingMatch[1].length+1),'',headingMatch[2]));list=null;}else if(/^[-*] /.test(line)){if(!list){list=element('ul');host.append(list);}list.append(element('li','',line.slice(2)));}else if(line.trim()){host.append(element('p','',line));list=null;}else list=null;});if(code)host.append(code);
      }
      function runNotebookCell(item,cell) {
        cell.execution=Math.max(0,...item.cells.map(c=>c.execution||0))+1;cell.output=simulateCell(cell.source);cell.table=null;
        const labels=cell.source.match(/entry_points\s*=\s*(\[[^\n]*\])/),values=cell.source.match(/values\s*=\s*\[([\d.,\s]+)\]/);
        if(labels&&values){try{const names=JSON.parse(labels[1]),numbers=values[1].split(',').map(Number);if(names.every(n=>typeof n==='string')&&names.length===numbers.length&&numbers.every(Number.isFinite)){cell.table=names.map((name,index)=>[name,numbers[index]]);cell.output='Verification rate by entry point';}}catch(_) { /* Unsupported sample syntax keeps the text result. */ }}
      }
      function renderNotebook(host,item) {
        seedNotebook(item);const toolbar=element('div','ob-notebook-toolbar');toolbar.append(element('span','ob-muted','Python 3 · simulated'),button('Run all','ob-action',()=>{item.cells.filter(c=>c.kind==='code').forEach(c=>runNotebookCell(item,c));renderReader();persist();}),button('+ Code','ob-action',()=>addNotebookCell(item,'code')),button('+ Markdown','ob-action',()=>addNotebookCell(item,'markdown')));host.append(toolbar);
        item.cells.forEach((cell,index)=>{
          const wrapper=element('section','ob-cell'),head=element('div','ob-cell-head'),type=select([{id:'code',name:'Code'},{id:'markdown',name:'Markdown'}]);type.value=cell.kind;type.setAttribute('aria-label','Cell '+(index+1)+' type');type.onchange=()=>{cell.kind=type.value;cell.output='';cell.table=null;renderReader();persist();};head.append(element('span','ob-cell-number',cell.kind==='code'?'In ['+(cell.execution||' ')+']':String(index+1)),type);
          if(cell.kind==='code'){const run=button('▶ Run','ob-quiet',()=>{runNotebookCell(item,cell);renderReader();persist();});run.setAttribute('aria-label','Run cell '+(index+1));head.append(run);}else head.append(button(cell.editing?'Preview':'Edit','ob-quiet',()=>{cell.editing=!cell.editing;renderReader();persist();}));
          const up=button('↑','ob-quiet',()=>{[item.cells[index-1],item.cells[index]]=[item.cells[index],item.cells[index-1]];renderReader();persist();});up.disabled=index===0;up.setAttribute('aria-label','Move cell '+(index+1)+' up');const remove=button('×','ob-quiet',()=>{item.cells.splice(index,1);renderReader();persist();});remove.setAttribute('aria-label','Delete cell '+(index+1));head.append(up,remove);wrapper.append(head);
          if(cell.kind==='code'||cell.editing){const code=element('textarea','ob-editor ob-code');code.rows=Math.min(12,Math.max(3,cell.source.split('\n').length));code.setAttribute('aria-label',(cell.kind==='code'?'Code':'Markdown')+' for cell '+(index+1));code.value=cell.source;code.oninput=()=>{cell.source=code.value;persist();};code.onkeydown=e=>{if(cell.kind==='code'&&e.key==='Enter'&&(e.ctrlKey||e.metaKey)){e.preventDefault();runNotebookCell(item,cell);renderReader();persist();}};wrapper.append(code);}else {const preview=element('div','ob-cell-markdown');renderMarkdown(preview,cell.source);wrapper.append(preview);}
          if(cell.kind==='code'&&cell.output)wrapper.append(element('pre','ob-output',cell.output));
          if(cell.kind==='code'&&cell.table){const table=element('table','ob-notebook-table'),headingRow=element('tr');headingRow.append(element('th','','Entry point'),element('th','','Verification'));const thead=element('thead');thead.append(headingRow);table.append(thead);const tbody=element('tbody'),chart=element('div','ob-notebook-chart');chart.setAttribute('aria-label','Verification rates chart');cell.table.forEach(([name,value])=>{const tr=element('tr');tr.append(element('td','',name),element('td','',value+'%'));tbody.append(tr);const bar=element('div','ob-chart-row'),track=element('div','ob-chart-track'),fill=element('span','ob-chart-fill');fill.style.width=Math.max(0,Math.min(100,value))+'%';track.append(fill);bar.append(element('span','',name),track,element('span','',value+'%'));chart.append(bar);});table.append(tbody);wrapper.append(table,chart);}
          host.append(wrapper);
        });
        host.append(element('p','ob-muted','Cells, Markdown, tables, and charts are saved in this demo. Running a cell simulates its output. Ctrl/⌘ + Enter runs the current code cell.'));
      }
      function addNotebookCell(item,kind) {item.cells.push({id:'cell-'+serial++,kind,source:kind==='code'?'print(1 + 1)':'## Notes\n\nAdd your findings here.',editing:kind==='markdown',output:'',execution:null});renderReader();persist();}
      function selectTerminal(t) {selected=t.objective;const o=objective();if(t.tree!=='objective')o.selected=t.tree;const item=o.items.find(i=>i.id===t.linked);if(item){o.selectedItem=item.id;o.selectedTab=t.linkedTab||null;o.view=item.kind==='task'?'tasks':'resource';if(t.linkedTab)retainTabs(o,item);}activeTerminal=t.id;render();message(t.name+' · '+(t.tree==='objective'?'Objective folder':o.worktrees.find(tree=>tree.id===t.tree).name));}
      function renderTerminals() {
        const host=find('terminals');host.replaceChildren();const head=element('div','ob-terminal-heading');head.append(element('strong','','Terminals'));const mode=element('select');mode.setAttribute('aria-label','Visible terminal groups');[['all','3 objectives'],['selected','Selected objective']].forEach(([value,label])=>{const opt=element('option','',label);opt.value=value;mode.append(opt);});mode.value=config.terminalVisibility;mode.onchange=()=>{config.terminalVisibility=mode.value;renderTerminals();persist();};head.append(mode);host.append(head);const surface=element('div','ob-terminal-surface'),rail=element('div','ob-terminal-groups');surface.append(rail);host.append(surface);
        focused.filter(id=>config.terminalVisibility==='all'||id===selected).forEach(id=>{const o=objectives.find(o=>o.id===id);const heading=element('div','ob-terminal-objective');heading.style.setProperty('--objective-color',o.color);heading.append(icon('target'),button(o.name,'',()=>switchObjective(id)));rail.append(heading);
          [{id:'objective',name:'Objective folder',color:o.color},...o.worktrees].forEach(tree=>{const group=terminals.filter(t=>t.objective===id&&t.tree===tree.id);if(!group.length)return;const label=element('div','ob-terminal-tree');label.style.setProperty('--tree-color',tree.color);label.append(element('span','ob-tree-dot'),element('span','',tree.name));rail.append(label);
            group.forEach(t=>{const item=o.items.find(i=>i.id===t.linked),tab=item?.tabs?.find(sub=>sub.id===t.linkedTab),linkedTitle=tab?item.title+' / '+tab.title:item?.title;const b=button('','ob-terminal',()=>selectTerminal(t));b.style.setProperty('--tree-color',tree.color);b.setAttribute('aria-pressed',t.id===activeTerminal);b.draggable=true;b.setAttribute('aria-label',t.name+' terminal'+(item?' linked to '+linkedTitle:''));b.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-terminal',t.id);e.dataTransfer.effectAllowed='link';};b.ondragend=()=>root.querySelectorAll('.ob-drop').forEach(el=>el.classList.remove('ob-drop'));attachDrop(b,'application/x-objective-item',ref=>{const target=resourceTarget(o,ref);if(target){t.linked=target.item.id;t.linkedTab=target.tab?.id||null;render();message('Linked '+t.name+' to '+(target.tab?.title||target.item.title)+' · launch folder kept');}else message('Choose an item from '+o.name);});b.append(icon(item?(iconNames[item.kind]||'terminal'):'terminal'),element('span','ob-label',linkedTitle||t.name));if(t.state!=='idle'){const dot=element('span','ob-status-dot'+(t.state==='ready'?' ready':''));dot.setAttribute('aria-label',t.state==='ready'?'Ready to review':'Working');b.append(dot);}rail.append(b);});
          });
        });
        rail.append(button('+ Terminal','ob-action ob-new-terminal',terminalDialog));const t=terminals.find(t=>t.id===activeTerminal);if(t){const console=element('div','ob-console');const folder=t.tree==='objective'?'objectives/'+t.objective:objectives.find(o=>o.id===t.objective).worktrees.find(tree=>tree.id===t.tree).name;console.append(element('strong','',t.name),element('p','ob-muted','/demo/'+folder));const logs=element('pre','ob-console-log',(t.logs||[]).join('\n\n'));console.append(logs);const label=element('label','','Command or prompt'),draft=element('textarea','ob-editor');draft.value=t.draft;draft.setAttribute('aria-label','Unsent prompt for '+t.name);draft.oninput=()=>{t.draft=draft.value;persist();};label.append(draft);console.append(label,button('Run simulation','ob-action',()=>runCommand(t)),element('div','ob-console-note','Try pwd, ls, cat README.md, echo hello, or help.'));if(t.linked)console.append(button('Unlink item','ob-quiet',()=>{t.linked=null;t.linkedTab=null;render();}));surface.append(console);}
      }
      function dialog(title) {const host=find('dialog');host.hidden=false;host.replaceChildren(element('h3','',title));const form=element('form');host.append(form);form.append(button('Cancel','ob-quiet',()=>{host.hidden=true;}));return form;}
      function field(form,labelText,control) {const label=element('label','',labelText);control.setAttribute('aria-label',labelText);label.append(control);form.insertBefore(label,form.lastChild);return control;}
      function select(options) {const el=element('select');options.forEach(o=>{const opt=element('option','',o.name);opt.value=o.id;el.append(opt);});return el;}
      function submit(form,label,action) {const b=button(label,'ob-action');b.type='submit';form.insertBefore(b,form.lastChild);form.onsubmit=e=>{e.preventDefault();action();find('dialog').hidden=true;render();};}
      function focusDialog() {
        const available=objectives.filter(o=>!focused.includes(o.id));const form=dialog('Bring an objective into focus');const pick=field(form,'Objective',select([...available,{id:'__new',name:'Create a new objective…'}]));const name=field(form,'New objective name',element('input'));name.type='text';name.parentElement.hidden=true;pick.onchange=()=>{name.parentElement.hidden=pick.value!=='__new';name.required=pick.value==='__new';};pick.onchange();const slot=field(form,'Replace focus slot',select(focused.map((id,index)=>({id:String(index),name:objectives.find(o=>o.id===id).name}))));submit(form,'Replace',()=>{const old=focused[Number(slot.value)];let o=objectives.find(o=>o.id===pick.value);if(pick.value==='__new'){o={id:'objective-'+serial++,name:name.value.trim(),purpose:'',color:nextColor(),selected:null,selectedItem:null,draft:'',worktrees:[],items:[],recent:[],files:[]};normalizeObjective(o);objectives.push(o);}if(o){o.view='tasks';o.selectedTab=null;focused[Number(slot.value)]=o.id;selected=o.id;activeTerminal=terminals.find(t=>t.objective===o.id)?.id||null;message(o.name+' is in focus · '+objectives.find(o=>o.id===old).name+' sessions keep running');}});
      }
      function itemDialog(kind='document',scope=null) {
        const form=dialog(kind==='file'?'Create a simulated worktree file':'Add an objective resource');const kinds=kind==='file'?['file','notebook','document']:['document','notebook','task','link','assistant'];const type=field(form,'Type',select(kinds.map(id=>({id,name:id==='assistant'?'Assistant document reference':id[0].toUpperCase()+id.slice(1)}))));type.value=kind;const input=field(form,'Name',element('input'));input.type='text';input.required=true;if(kind==='file')input.placeholder='notes/findings.md';const url=field(form,'URL for a link',element('input'));url.type='text';const due=field(form,'Due date',element('input'));due.type='date';type.onchange=()=>{url.parentElement.hidden=type.value!=='link';due.parentElement.hidden=type.value!=='task';};type.onchange();
        submit(form,'Create',()=>{const o=objective(),k=type.value;let title=input.value.trim();if(k==='notebook'&&!title.endsWith('.ipynb'))title+='.ipynb';const item={id:'item-'+serial++,kind:k,title,scope,body:k==='assistant'?'Simulated reference to an existing Assistant document.':'',source:'',url:url.value,listed:kind==='file'?false:true,updated:Date.now(),checks:k==='task'?[]:undefined,done:false,due:due.value};o.items.push(item);normalizeObjective(o);o.selectedItem=item.id;o.selectedTab=null;o.view=k==='task'?'tasks':'resource';message('Created '+title+(k==='task'?' with a details document subtab':'')+' in '+o.name+' · demo data');});
      }
      function renameDialog(item) {const form=dialog('Rename '+item.kind),input=field(form,'Name',element('input'));input.type='text';input.value=item.title;input.required=true;submit(form,'Rename',()=>{item.title=input.value.trim();if(item.kind==='notebook'&&!item.title.endsWith('.ipynb'))item.title+='.ipynb';message('Renamed resource · its links remain intact');});}
      function nextColor(o=null) {
        const used=new Set(objectives.flatMap(o=>o.worktrees.map(t=>t.color)));const reserved=new Set(objectives.flatMap(o=>[o.color,...(o.palette||[])]));
        const own=o?.palette?.find(c=>!used.has(c));if(own)return own;
        const extra=['#79c0ff','#da9dff','#8ddb8c','#ffad80'].find(c=>!used.has(c)&&!reserved.has(c));return extra||'hsl('+((serial*137.508)%360)+' 66% 65%)';
      }
      function worktreeDialog() {
        const form=dialog('Associate a worktree');const action=field(form,'Action',select([{id:'existing',name:'Bring an existing worktree'},{id:'new',name:'Create a new worktree'}]));const repo=field(form,'Repository',select([{id:'client',name:'client'},{id:'service',name:'service'}]));const existing=field(form,'Existing worktree',select([{id:'feature/retry',name:'feature/retry'},{id:'feature/analytics',name:'feature/analytics'},{id:'main',name:'main'}]));const name=field(form,'New branch name',element('input'));name.type='text';name.value='fix/follow-up';name.parentElement.hidden=true;action.onchange=()=>{name.parentElement.hidden=action.value!=='new';name.required=action.value==='new';existing.parentElement.hidden=action.value==='new';};
        submit(form,'Associate',()=>{const o=objective(),title=action.value==='new'?name.value.trim():existing.value;const duplicate=objectives.find(p=>p.worktrees.some(t=>t.name===title&&t.repo===repo.value));if(duplicate){message(title+' is already associated with '+duplicate.name);return;}const tree={id:'tree-'+serial++,name:title,repo:repo.value,color:nextColor(o)};o.worktrees.push(tree);seedFiles(o,tree);o.selected=tree.id;message((action.value==='new'?'Created':'Associated')+' '+tree.name+' with '+o.name+' · demo data');});
      }
      function terminalDialog() {const o=objective(),form=dialog('New terminal · '+o.name),scope=field(form,'Launch folder',select([{id:'objective',name:'Objective folder'},...o.worktrees]));scope.value=o.selected||'objective';submit(form,'Open terminal',()=>{const id='terminal-'+serial++,tree=scope.value;const t={id,objective:o.id,tree,name:'Terminal '+serial,linked:null,state:'idle',draft:'',logs:['New simulated session. Type help to explore.']};terminals.push(t);activeTerminal=id;message('Opened simulated terminal · launch folder remains fixed');});}
      function settingsDialog() {const form=dialog('Objective settings'),o=objective(),input=field(form,'Objective name',element('input'));input.type='text';input.value=o.name;input.required=true;const goal=field(form,'Outcome',element('input'));goal.type='text';goal.value=o.purpose||'';const grouping=field(form,'Resource sections',select([{id:'separate',name:'Documents / Links / Tasks'},{id:'combined',name:'Documents & links / Tasks'}]));grouping.value=config.groupResources?'combined':'separate';submit(form,'Save',()=>{o.name=input.value.trim();o.purpose=goal.value;config.groupResources=grouping.value==='combined';message('Objective settings updated');});}
      function todoDialog(item) {const form=dialog('Add a subtask'),input=field(form,'Subtask',element('input'));input.type='text';input.required=true;const due=field(form,'Due date (optional)',element('input'));due.type='date';submit(form,'Add',()=>{const entry={id:'subtask-'+serial++,title:input.value.trim(),done:false,due:due.value};item.checks.push(entry);ensureDetails(objective(),item,entry);message('Subtask created with its own document subtab');});}
      function taskEditDialog(task,entry) {
        const o=objective(),form=dialog('Edit '+(entry===task?'task':'subtask')),name=field(form,'Name',element('input'));name.type='text';name.required=true;name.value=entry.title;
        const due=field(form,'Due date',element('input'));due.type='date';due.value=entry.due||'';
        const doc=field(form,'Details document',select(o.items.filter(i=>i.kind==='document').map(i=>({id:i.id,name:i.title}))));doc.value=entry.detail;
        const tab=field(form,'Document subtab',select([]));doc.onchange=()=>{tab.replaceChildren();[{id:'__new',title:'Create a subtab for this task'},...(o.items.find(i=>i.id===doc.value)?.tabs||[])].forEach(t=>{const option=element('option','',t.title);option.value=t.id;tab.append(option);});tab.value=doc.value===entry.detail?entry.tab:'__new';};doc.onchange();
        const remove=button(entry===task?'Delete task':'Delete subtask','ob-quiet',()=>{if(entry===task)deleteDialog(task);else {const complete=taskComplete(task);task.checks.splice(task.checks.indexOf(entry),1);if(!task.checks.length)task.done=complete;find('dialog').hidden=true;render();}});form.insertBefore(remove,form.lastChild);
        submit(form,'Save',()=>{const oldTitle=entry.title;entry.title=name.value.trim();entry.due=due.value;entry.detail=doc.value;entry.tab=tab.value==='__new'?null:tab.value;ensureDetails(o,task,entry);const details=o.items.find(i=>i.id===entry.detail).tabs.find(t=>t.id===entry.tab);if(details.title===oldTitle)details.title=entry.title;message('Task details and deadline updated');});
      }
      function subtabDialog(item) {const form=dialog('New document subtab'),name=field(form,'Subtab name',element('input'));name.type='text';name.required=true;submit(form,'Create',()=>{const tab={id:'tab-'+serial++,title:name.value.trim(),body:'# '+name.value.trim()+'\n\nAdd your notes here.'};item.tabs ||= [];item.tabs.push(tab);const o=objective();o.selectedItem=item.id;o.selectedTab=tab.id;o.view='resource';retainTabs(o,item);message('Created a document subtab · retained for five minutes');});}
      function renameSubtabDialog(item,tab) {const form=dialog('Rename document subtab'),name=field(form,'Name',element('input'));name.type='text';name.required=true;name.value=tab.title;submit(form,'Rename',()=>{tab.title=name.value.trim();message('Renamed subtab · task and terminal links remain intact');});}
      function linkTerminalDialog(item,tab=null) {const form=dialog('Link an existing simulated terminal'),pick=field(form,'Terminal',select(terminals.filter(t=>t.objective===selected).map(t=>({id:t.id,name:t.name}))));if(!pick.options.length){form.insertBefore(element('p','ob-muted','Create a terminal with + Terminal first.'),form.lastChild);return;}submit(form,'Link',()=>{const terminal=terminals.find(t=>t.id===pick.value);terminal.linked=item.id;terminal.linkedTab=tab?.id||null;message('Item linked · terminal launch folder kept');});}
      function deleteDialog(item) {const o=objective(),form=dialog('Delete '+item.title+' from the demo?');if(o.items.filter(i=>i.kind==='task').some(t=>t.detail===item.id||t.checks.some(c=>c.detail===item.id))){form.insertBefore(element('p','ob-muted','This document describes a task. Choose a different details document in the task’s edit menu before deleting it.'),form.lastChild);return;}submit(form,'Delete',()=>{o.items.splice(o.items.indexOf(item),1);terminals.filter(t=>t.objective===o.id&&t.linked===item.id).forEach(t=>{t.linked=null;t.linkedTab=null;});delete o.tabShelf[item.id];o.selectedItem=o.items.find(i=>i.listed!==false)?.id||null;o.selectedTab=null;if(item.kind==='task')o.view='tasks';message('Deleted simulated item · linked sessions remain');});}
      function simulateCell(source) {
        const rates=source.match(/rates\s*=\s*\[([\d.,\s]+)\]/);if(rates&&source.includes('mean_rate')){const values=rates[1].split(',').map(Number);return 'Mean verification rate: '+(values.reduce((a,b)=>a+b,0)/values.length*100).toFixed(1)+'%';}
        const text=source.match(/print\(\s*['"]([^'"]*)['"]\s*\)/);if(text)return text[1];
        const number=source.match(/print\(\s*(\d+(?:\.\d+)?)\s*([+*/-])\s*(\d+(?:\.\d+)?)\s*\)/);if(number){const a=Number(number[1]),b=Number(number[3]);return String(({'+':()=>a+b,'-':()=>a-b,'*':()=>a*b,'/':()=>a/b})[number[2]]());}
        return 'Simulated cell finished.';
      }
      function runCommand(t) {
        const command=(t.draft||'').trim();if(!command)return;const o=objectives.find(o=>o.id===t.objective),tree=o.worktrees.find(tree=>tree.id===t.tree),files=o.items.filter(i=>i.listed===false&&i.scope===t.tree);let output;
        if(command==='clear'){t.logs=[];t.draft='';render();return;}
        if(command==='pwd')output='/demo/'+(tree?tree.repo+'/worktrees/'+tree.name:'objectives/'+o.id);
        else if(command==='ls')output=files.map(i=>i.title).join('\n')||'documents/\nnotebooks/\ntasks/';
        else if(command.startsWith('cat ')){const item=files.find(i=>i.title===command.slice(4).trim());output=item?(item.body||''):'No such simulated file.';}
        else if(command.startsWith('echo '))output=command.slice(5);
        else if(command==='help')output='pwd · ls · cat <path> · echo <text> · clear\ndone marks the linked task complete.\nAny other text produces a simulated agent response.';
        else if(command==='done'){const item=o.items.find(i=>i.id===t.linked&&i.kind==='task');if(item){item.done=true;item.checks.forEach(c=>c.done=true);output='Linked task complete.';}else output='Link this terminal to a task first.';}
        else output='Simulated agent completed: '+command;
        t.logs=[...(t.logs||[]),'$ '+command,output].slice(-40);t.draft='';t.state='ready';render();message(t.name+' · simulated result ready to review');
      }
      function render() {renderFocus();renderOverview();renderReader();renderTerminals();scheduleShelfExpiry();persist();}
      render();
      let currentDay=localDate();setInterval(()=>{if(localDate()!==currentDay){currentDay=localDate();renderFocus();renderOverview();if(objective().view==='tasks')renderReader();}},60000);
      find('reset').onclick=()=>{const form=dialog('Reset all simulated changes?');submit(form,'Reset demo',()=>{restore(JSON.parse(JSON.stringify(fresh)));message('Demo reset to its sample data');});};
      if(window.parent!==window)window.parent.postMessage({channel,type:'ready'},'*');else hydrated=true;
    })();
