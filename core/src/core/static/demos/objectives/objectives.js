(() => {
      const root = document.getElementById('lab-objectives-proposal');
      const find = name => root.querySelector('[data-' + name + ']');
      const channel = 'lab-objectives-demo-v1';
      let hydrated = false;
      const focusSlots = 5;
      const iconNames = {document:'file-text',assistant:'files',notebook:'notebook',link:'external-link',task:'square-check',file:'file-code',folder:'folder'};
      const objectives = [
        {id:'sms',name:'SMS recovery',purpose:'Restore reliable phone verification',color:'#58a6ff',selected:'phone-fix',selectedItem:'incident',draft:'',worktrees:[{id:'phone-fix',name:'sdui/fix-phone',repo:'client',color:'#58a6ff'},{id:'checkpoint',name:'checkpoint/verification',repo:'client',color:'#ff7b72'},{id:'triage',name:'recovery/triage',repo:'client',color:'#3fb950'}],items:[
          {id:'incident',kind:'document',title:'Incident notes',scope:null,body:'Investigate failed phone verification and record the recovery plan.'},
          {id:'track',kind:'assistant',title:'Investigation — Track 3',scope:null,body:'Linked Assistant document. Its existing content and tasks remain owned by Assistant.'},
          {id:'volume',kind:'notebook',title:'Verification volume.ipynb',scope:null},
          {id:'thread',kind:'link',title:'Malformed-phone discussion',scope:null,url:'https://app.slack.com/client/demo/thread'},
          {id:'channel',kind:'link',title:'Incident channel',scope:null,url:'https://app.slack.com/client/demo/incident'},
          {id:'ticket',kind:'link',title:'Ticket — Unparseable phone',scope:null,url:'https://demo.atlassian.net/browse/PHONE-26080'},
          {id:'validate',kind:'task',title:'Validate phone parsing',scope:null,checks:[{title:'Reproduce malformed input',done:true},{title:'Verify recovery behavior',done:true}],detail:'incident'},
          {id:'rollout',kind:'task',title:'Review rollout results',scope:null,checks:[{title:'Compare verification rates',done:true}],done:true},
          {id:'fallback',kind:'task',title:'Confirm the recovery fallback',scope:null,checks:[],done:true},
          {id:'regression',kind:'task',title:'Record regression coverage',scope:null,checks:[{title:'Cover malformed phone numbers',done:true},{title:'Cover the recovery route',done:true}]},
          {id:'release',kind:'task',title:'Release the parsing change',scope:null,checks:[],done:false},
          {id:'monitor',kind:'task',title:'Monitor recovery after rollout',scope:null,checks:[],done:false},
          {id:'prs',kind:'link',title:'PRs for this branch',scope:'phone-fix',url:'https://github.com/example/client/pulls'}],recent:['api/phone_parser.py','tests/test_phone_parser.py'],files:['api/','applications/','build/','client/']},
        {id:'api',name:'API cleanup',purpose:'Simplify the public API',color:'#bc8cff',selected:'api-main',selectedItem:'api-plan',draft:'',worktrees:[{id:'api-main',name:'cleanup/routes',repo:'service',color:'#bc8cff'},{id:'api-tests',name:'cleanup/contract-tests',repo:'service',color:'#e3b341'}],items:[{id:'api-plan',kind:'document',title:'API cleanup plan',scope:null,body:'Review route behavior, remove redundant paths, and document the supported API.'},{id:'api-reference',kind:'link',title:'API reference',scope:null,url:'https://example.com/api'},{id:'api-task',kind:'task',title:'Review compatibility',scope:null,checks:[{title:'List existing consumers',done:true},{title:'Verify current contracts',done:false}],detail:'api-plan'}],recent:['service/routes.py','tests/test_contracts.py'],files:['service/','tests/','README.md']},
        {id:'latency',name:'Latency study',purpose:'Understand response time',color:'#ffa657',selected:'timing',selectedItem:'measurements',draft:'',worktrees:[{id:'timing',name:'perf/timing',repo:'service',color:'#ffa657'}],items:[{id:'measurements',kind:'notebook',title:'Measurements.ipynb',scope:null},{id:'latency-task',kind:'task',title:'Compare response times',scope:null,checks:[{title:'Capture a baseline',done:true},{title:'Repeat the measurements',done:false}],detail:'measurements'}],recent:['scripts/benchmark.py'],files:['scripts/','results/']},
        {id:'docs',name:'Documentation',purpose:'Improve onboarding',color:'#39c5cf',selected:'docs-main',selectedItem:'onboarding',draft:'',worktrees:[{id:'docs-main',name:'docs/onboarding',repo:'client',color:'#39c5cf'}],items:[{id:'onboarding',kind:'document',title:'Onboarding guide',scope:null,body:'Document the setup and first useful workflow.'}],recent:['docs/setup.md'],files:['docs/','README.md']}
      ];
      objectives.push({id:'release-study',name:'Release verification',purpose:'Verify the change before release',worktrees:[],items:[{id:'release-plan',kind:'document',title:'Release checklist.md',body:'# Release checklist\n\nRecord evidence before deploying.',scope:null},{id:'release-task',kind:'task',title:'Verify release evidence',checks:[],done:false}],recent:[],files:[]}, {id:'followup-study',name:'Follow-up investigation',purpose:'Capture the next question',worktrees:[],items:[],recent:[],files:[]});
      const terminals = [{id:'t1',objective:'sms',tree:'phone-fix',name:'Parsing fix',linked:'validate',state:'working',draft:''},{id:'t2',objective:'sms',tree:'phone-fix',name:'Test runner',linked:null,state:'ready',draft:''},{id:'t3',objective:'sms',tree:'checkpoint',name:'Investigation',linked:'incident',state:'idle',draft:''},{id:'t4',objective:'api',tree:'api-main',name:'Route review',linked:'api-plan',state:'working',draft:''},{id:'t5',objective:'api',tree:'api-tests',name:'Contract tests',linked:null,state:'idle',draft:''},{id:'t6',objective:'latency',tree:'timing',name:'Benchmark',linked:'measurements',state:'ready',draft:''},{id:'t7',objective:'docs',tree:'docs-main',name:'Guide edits',linked:'onboarding',state:'idle',draft:''}];
      const config = {terminalVisibility:'all'};
      let focused = ['sms','api','latency','docs','release-study'], selected = 'sms', activeTerminal = 't1', serial = 10, recentMode = 'Uncommitted';
      const openFolders = new Set();
      const hoverTimers = new Map();
      const hoverDelay = 1500;
      const documentEditors = new Map();
      let taskStatusMenu;
      const taskStatuses = {todo:{icon:'⬜',label:'Undo'},in_progress:{icon:'🟡',label:'In progress'},done:{icon:'✅',label:'Completed'}};
      const palettes = [['#58a6ff','#ff7b72','#3fb950','#d29922'],['#bc8cff','#e3b341','#56d6c0','#ff9bce'],['#ffa657','#f778ba','#a9d14c','#238a97'],['#39c5cf','#d67ad2','#e5a07c','#85c56a'],['#8b9dff','#e87f91','#a6be4f','#58b9a6']];
      objectives.forEach((o,index)=>{
        o.palette=palettes[index]||[];o.color=o.palette[0]||'#8b949e';
        o.worktrees.forEach(tree=>seedFiles(o,tree));
        o.items.filter(i=>i.kind==='notebook').forEach(i=>{i.source='rates = [0.96, 0.98, 0.99]\nmean_rate = sum(rates) / len(rates)\nprint(f"Mean verification rate: {mean_rate:.1%}")';i.output='Mean verification rate: 97.7%';});
        normalizeObjective(o);
        o.items.filter(i=>i.kind==='task').forEach(task=>{task.due=dateOffset(index===1?2:index===2?-1:6);});
      });
      const sample=objectives[0];sample.objectiveAssets=['incident','channel'];
      sample.items.push({id:'metrics-query',kind:'file',title:'queries/volume.sql',scope:'phone-fix',body:'SELECT entry_point, COUNT(*) FROM verification_events GROUP BY entry_point;',tabs:[]},
        {id:'google-doc',kind:'link',title:'Telesign Incident Room — Track 3',scope:null,url:'https://docs.google.com/document/d/demo/edit',tldr:'Shared incident record with investigation and recovery tabs.',tabs:[{id:'google-investigation',title:'Investigation',url:'https://docs.google.com/document/d/demo/edit?tab=investigation',body:''},{id:'google-recovery',title:'Recovery',url:'https://docs.google.com/document/d/demo/edit?tab=recovery',body:''}]});
      sample.items.find(i=>i.id==='validate').assets=['volume','worktree::phone-fix'];
      sample.items.find(i=>i.id==='release').assets=['ticket','prs','worktree::checkpoint'];
      sample.items.push({id:'old-notes',kind:'document',title:'Old incident notes.md',body:'# Archived notes\n\nKept for reference, outside agent context.',scope:null,tabs:[]});sample.archiveAssets=['old-notes'];
      applySlotColors();
      terminals.forEach(t=>t.logs=['Objectives demo terminal · help lists simulated commands.']);
      const fresh = JSON.parse(JSON.stringify(snapshot()));

      function snapshot() {return {version:1,objectives,terminals,config,focused,selected,activeTerminal,serial,recentMode,openFolders:[...openFolders]};}
      function persist() {if(hydrated&&window.parent!==window)window.parent.postMessage({channel,type:'save',state:snapshot()},'*');}
      function dateOffset(offset) {const day=new Date();day.setDate(day.getDate()+offset);return localDate(day);}
      function localDate(day=new Date()) {return day.getFullYear()+'-'+String(day.getMonth()+1).padStart(2,'0')+'-'+String(day.getDate()).padStart(2,'0');}
      function dayNumber(value) {if(!/^\d{4}-\d{2}-\d{2}$/.test(value||''))return null;return Date.parse(value+'T00:00:00Z')/86400000;}
      function taskStatus(task) {
        if(task.status==='in_progress')return 'in_progress';
        if(task.checks?.length)return task.checks.every(c=>c.done)?'done':task.checks.some(c=>c.done||c.status==='in_progress')?'in_progress':'todo';
        return task.done?'done':'todo';
      }
      function taskComplete(task) {return taskStatus(task)==='done';}
      function setTaskStatus(o,task,status) {
        const set=(t,s)=>Object.assign(t,{status:s,done:s==='done'});
        set(task,status);if(status!=='in_progress')task.checks?.forEach(c=>set(c,status));
        const parent=parentTask(o,task);
        if(parent&&parent!==task)set(parent,parent.checks.every(c=>c.done)?'done':parent.checks.some(c=>c.done||c.status==='in_progress')?'in_progress':'todo');
      }
      function setTaskComplete(task,done) {setTaskStatus(objective(),task,done?'done':'todo');render();}
      function taskStatusIcon(task,className='') {
        const status=taskStatus(task),glyph=element('span',className+' ob-task-status-icon',taskStatuses[status].icon);
        glyph.dataset.taskStatus=status;return glyph;
      }
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
        o.view ||= 'tasks';o.selectedTab ||= null;o.tabShelf ||= {};o.palette ||= [];o.activeTask ||= null;o.expandedTask ||= null;
        o.objectiveAssets=Array.isArray(o.objectiveAssets)?o.objectiveAssets:[];o.archiveAssets=Array.isArray(o.archiveAssets)?o.archiveAssets:[];o.assetShelf=Array.isArray(o.assetShelf)?o.assetShelf:[];
        o.items.filter(i=>i.kind==='document'||i.kind==='assistant'||i.kind==='file'&&i.title.endsWith('.md')).forEach(i=>{
          if(!Array.isArray(i.tabs))i.tabs=i.id==='incident'?[{id:'timeline',title:'Timeline',body:'# Incident timeline\n\n## Detection\nPhone verification failures increased after the rollout.\n\n## Recovery\nThe parsing fix restores the fallback flow.'},{id:'recovery-plan',title:'Recovery plan',body:'# Recovery plan\n\n- Reproduce the malformed input.\n- Verify the fallback.\n- Check verification volume.'}]:i.kind==='assistant'?[{id:'analysis',title:'Analysis',body:'# Investigation — Analysis\n\nSimulated reference to an Assistant subtab. The original document remains owned by Assistant.'},{id:'follow-up',title:'Follow-up',body:'# Follow-up\n\nReview the findings with the recovery team.'}]:[];
        });
        o.items.filter(i=>i.kind==='task').forEach(task=>{
          task.done=task.done===true;task.checks ||= [];task.due ||= '';task.assets=Array.isArray(task.assets)?task.assets:[];
          ensureDetails(o,task);
          task.checks.forEach((c,index)=>{c.id ||= task.id+'-todo-'+index;c.due ||= '';c.assets=Array.isArray(c.assets)?c.assets:[];ensureDetails(o,task,c);});
        });
        o.items.filter(i=>i.kind==='notebook').forEach(seedNotebook);
        if(o.activeTask)o.expandedTask=parentTask(o,activeTask(o))?.id||null;
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
        if(state?.version!==1||!Array.isArray(state.objectives)||!state.objectives.length||state.objectives.length>100||!Array.isArray(state.terminals)||!Array.isArray(state.focused)||state.focused.length>focusSlots||!state.focused.length)return false;
        const ids=new Set();
        for(const o of state.objectives){
          if(typeof o.id!=='string'||ids.has(o.id)||typeof o.name!=='string'||typeof o.color!=='string'||!Array.isArray(o.worktrees)||!Array.isArray(o.items)||!Array.isArray(o.files)||!Array.isArray(o.recent))return false;
          ids.add(o.id);const treeIds=new Set(o.worktrees.map(t=>t.id));
          if(o.worktrees.some(t=>typeof t.name!=='string'||typeof t.color!=='string'||typeof t.repo!=='string')||o.selected&&!treeIds.has(o.selected))return false;
          if(o.items.some(i=>typeof i.id!=='string'||typeof i.title!=='string'||!Object.hasOwn(iconNames,i.kind)||i.scope&&!treeIds.has(i.scope)||i.kind==='task'&&(!Array.isArray(i.checks)||i.checks.some(c=>typeof c.title!=='string'||typeof c.done!=='boolean'))))return false;
          if(o.items.some(i=>i.tabs!==undefined&&(!Array.isArray(i.tabs)||i.tabs.some(t=>typeof t.id!=='string'||typeof t.title!=='string'||typeof t.body!=='string'))||i.cells!==undefined&&(!Array.isArray(i.cells)||i.cells.some(c=>typeof c.id!=='string'||!['code','markdown'].includes(c.kind)||typeof c.source!=='string'||c.table!=null&&(!Array.isArray(c.table)||c.table.some(r=>!Array.isArray(r)||typeof r[0]!=='string'||!Number.isFinite(r[1])))))))return false;
          if(['objectiveAssets','archiveAssets','assetShelf'].some(key=>o[key]!==undefined&&(!Array.isArray(o[key])||o[key].some(ref=>typeof ref!=='string')))||o.items.filter(i=>i.kind==='task').flatMap(t=>[t,...t.checks]).some(t=>t.assets!==undefined&&(!Array.isArray(t.assets)||t.assets.some(ref=>typeof ref!=='string'))))return false;
          if(o.tabShelf!==undefined&&(!o.tabShelf||typeof o.tabShelf!=='object'||Array.isArray(o.tabShelf)||Object.values(o.tabShelf).some(s=>!s||!Number.isFinite(s.until)||!Array.isArray(s.pinned)||s.pinned.some(id=>typeof id!=='string'))))return false;
        }
        if(new Set(state.focused).size!==state.focused.length||state.focused.some(id=>!ids.has(id))||!ids.has(state.selected))return false;
        return state.terminals.every(t=>typeof t.id==='string'&&typeof t.name==='string'&&state.objectives.some(o=>o.id===t.objective&&(t.tree==='objective'||o.worktrees.some(tree=>tree.id===t.tree))));
      }
      function restore(state) {if(!validState(state))return false;documentEditors.forEach(d=>d.input.destroy());documentEditors.clear();objectives.splice(0,objectives.length,...state.objectives);terminals.splice(0,terminals.length,...state.terminals);config.terminalVisibility=state.config?.terminalVisibility==='selected'?'selected':'all';focused=[...state.focused];selected=state.selected;activeTerminal=state.activeTerminal;serial=Number.isSafeInteger(state.serial)?state.serial:100;recentMode=state.recentMode||'Uncommitted';openFolders.clear();(state.openFolders||[]).forEach(id=>openFolders.add(id));objectives.forEach(normalizeObjective);applySlotColors();return true;}
      window.addEventListener('message',event=>{if(event.source!==window.parent||event.data?.channel!==channel||event.data.type!=='hydrate'||hydrated)return;restore(event.data.state);hydrated=true;render();});
      const objective = () => objectives.find(item => item.id === selected);
      function element(tag, className, content) { const el=document.createElement(tag); if(className) el.className=className; if(content!==undefined) el.textContent=content; return el; }
      function icon(name) { const el=element('span','ob-icon',({'target':'◎','git-branch':'⑂','file-text':'▤','files':'▥','notebook':'▦','terminal':'›_','external-link':'↗','square-check':'☑','file-code':'◇','folder':'▸'})[name]||'◇');el.setAttribute('aria-hidden','true');return el; }
      function button(label, className, action) { const el=element('button',className,label); el.type='button'; el.onclick=action; return el; }
      function message(text) { find('message').textContent=text; }
      function refreshIcons() {}
      function todoCount(o) { return o.items.filter(i=>i.kind==='task').reduce((n,i)=>n+(i.checks.length?i.checks.filter(c=>!c.done).length:Number(!taskComplete(i))),0); }
      function showTasks(o=objective()) {o.view='tasks';o.activeTask=null;o.selectedTab=null;render();}
      function switchObjective(id) { selected=id; const o=objective();o.view='tasks';o.activeTask=null;o.selectedTab=null; const t=terminals.find(t=>t.objective===id&&t.tree===o.selected)||terminals.find(t=>t.objective===id); activeTerminal=t?t.id:null; find('dialog').hidden=true; render(); message(o.name+' · '+todoCount(o)+' open to-dos · '+o.worktrees.length+' associated worktrees'); }
      function attachDrop(el, type, action) {
        const handlers=el._dropHandlers ||= new Map();handlers.set(type,action);
        const accepts=m=>m!=='application/x-objective-terminal'||!!el.closest('.ob-overview');
        el.ondragover=e=>{if([...handlers.keys()].some(m=>accepts(m)&&e.dataTransfer.types.includes(m))){e.preventDefault();e.stopPropagation();e.dataTransfer.dropEffect=e.dataTransfer.types.includes('application/x-objective-id')?'move':'link';el.classList.add('ob-drop');}};
        el.ondragleave=()=>el.classList.remove('ob-drop');
        el.ondrop=e=>{el.classList.remove('ob-drop');for(const [mime,run] of handlers){if(!accepts(mime))continue;const ref=e.dataTransfer.getData(mime);if(!ref)continue;e.preventDefault();e.stopPropagation();const source=e.dataTransfer.getData('application/x-objective-source');if(source&&source!==objective().id){message('Choose an asset in the current objective.');return;}run(ref,e.dataTransfer);return;}};
      }
      function applySlotColors() {objectives.forEach(o=>{const slot=focused.indexOf(o.id);o.palette=palettes[slot]||[];o.color=o.palette[0]||'#8b949e';o.worktrees.forEach((t,i)=>{t.color=o.palette[i%4]||'#8b949e';});});}
      function insertObjective(id,slot) {focused=focused.filter(ref=>ref!==id);focused.splice(slot,0,id);focused=focused.slice(0,focusSlots);applySlotColors();render();message('Inserted into slot '+(slot+1)+' · the fifth objective returns to the library.');}
      function showAll() {objective().activeTask=null;objective().view='all';render();}
      function renderFocus() {
        const host=find('focus'),o=objective();host.replaceChildren();
        const all=button('Objectives','ob-nav-tab',showAll);all.setAttribute('aria-pressed',o.view==='all');all.dataset.allObjectives='';
        const task=activeTask(o),current=button('','ob-nav-tab ob-current',()=>switchObjective(o.id));current.style.setProperty('--objective-color',o.color);current.setAttribute('aria-pressed',o.view!=='all');current.setAttribute('aria-haspopup','menu');current.setAttribute('aria-expanded','false');current.dataset.currentObjective='';
        current.append(task?taskGlyph(o,task):element('span','ob-objective-dot'),element('span','ob-label',task?.title||o.name),element('span','ob-muted','▾'));
        const menu=element('div','ob-switch-menu');menu.hidden=true;menu.setAttribute('role','menu');
        Array.from({length:focusSlots},(_,slot)=>{const p=objectives.find(p=>p.id===focused[slot]),b=button('','',()=>p?switchObjective(p.id):focusDialog(slot));b.setAttribute('role','menuitem');b.append(element('span','ob-muted',String(slot+1)),element('span','ob-objective-dot'),element('span','ob-label',p?.name||'Choose objective…'));b.style.setProperty('--objective-color',palettes[slot][0]);menu.append(b);});
        const reveal=()=>{menu.hidden=false;current.setAttribute('aria-expanded','true');};current.onmouseenter=reveal;current.onfocus=reveal;
        host.onmouseleave=()=>{menu.hidden=true;current.setAttribute('aria-expanded','false');};current.onkeydown=e=>{if(e.key==='ArrowDown'){e.preventDefault();reveal();menu.firstElementChild.focus();}else if(e.key==='Escape'){menu.hidden=true;current.setAttribute('aria-expanded','false');}};
        host.append(all,current,menu);
      }
      function renderLibrary(host,o) {
        const top=element('div','ob-reader-head');top.append(element('h2','','All objectives'),button('+ Objective','ob-action',()=>focusDialog()));host.append(top);
        heading(host,'FOCUS SLOTS');const slots=element('div','ob-library-slots');
        Array.from({length:focusSlots},(_,slot)=>{const p=objectives.find(p=>p.id===focused[slot]),b=button('','ob-library-slot',()=>focusDialog(slot));b.dataset.slot=String(slot);b.style.setProperty('--objective-color',palettes[slot][0]);b.append(element('span','ob-muted','Slot '+(slot+1)),element('strong','',p?.name||'Empty'));attachDrop(b,'application/x-objective-id',id=>insertObjective(id,slot));slots.append(b);});host.append(slots,element('p','ob-muted','Drop into a slot to insert. Following objectives move down; the fifth stays in this list.'));
        const search=element('input','ob-search');search.type='search';search.placeholder='Name or outcome';search.setAttribute('aria-label','Search objectives');search.value=config.search||'';host.append(search);const list=element('div','ob-library-list');host.append(list);
        function paint(){list.replaceChildren();objectives.filter(p=>(p.name+' '+p.purpose).toLowerCase().includes(search.value.toLowerCase())).forEach(p=>{const row=element('div','ob-library-row'),open=button('','ob-library-name',()=>switchObjective(p.id));open.append(element('strong','',p.name),element('span','ob-muted',p.purpose));row.draggable=true;row.dataset.objective=p.id;row.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-id',p.id);e.dataTransfer.effectAllowed='move';};row.append(open,progressBadge(p),element('span','ob-muted',focused.includes(p.id)?'Slot '+(focused.indexOf(p.id)+1):'Parked'),button('Focus…','ob-action',()=>focusDialog(null,p.id)));list.append(row);});}
        search.oninput=()=>{config.search=search.value;paint();persist();};paint();
      }
      function heading(host,label,action) {const row=element('div','ob-section-heading');row.append(element('span','',label));if(action){const add=button('+','ob-quiet',action);add.setAttribute('aria-label','Add to '+label.toLowerCase());row.append(add);}host.append(row);}
      function taskEntries(o) {return o.items.filter(i=>i.kind==='task').flatMap(t=>[t,...t.checks]);}
      function activeTask(o) {return taskEntries(o).find(t=>t.id===o.activeTask);}
      function parentTask(o,entry) {return entry&&o.items.find(t=>t.kind==='task'&&(t.id===entry.id||t.checks.some(c=>c.id===entry.id)));}
      function detailsRef(t) {return t.detail+'::'+t.tab;}
      function taskAssetRefs(t) {return [...new Set([detailsRef(t),...(t.assets||[])])];}
      function taskContextRefs(o,task) {const parent=parentTask(o,task);return [...new Set([...o.objectiveAssets,...(parent&&parent!==task?taskAssetRefs(parent):[]),...taskAssetRefs(task)])].filter(ref=>!o.archiveAssets.includes(ref));}
      function assetInfo(o,ref) {
        if(typeof ref!=='string')return null;
        const [id,child,path]=ref.split('::');
        if(id==='worktree'){const tree=o.worktrees.find(t=>t.id===child);return tree?{ref,tree,title:tree.name,kind:'worktree',reference:'/demo/'+tree.repo+'/worktrees/'+tree.name}:null;}
        if(id==='folder'){const tree=o.worktrees.find(t=>t.id===child),base=child==='root'?'/demo/workspace':child==='objective'?'/demo/workspace/objectives/'+o.id:tree?'/demo/'+tree.repo+'/worktrees/'+tree.name:null;return base?{ref,tree,title:path|| (child==='root'?'Root':child==='objective'?'Objective':tree.name),kind:'folder',reference:base+(path?'/'+path.replace(/\/$/,''):'')}:null;}
        const task=taskEntries(o).find(t=>t.id===ref);if(task)return {ref,task,objective:o,title:task.title,kind:'task'};
        const target=resourceTarget(o,ref);if(!target||target.item.kind==='task')return null;
        const {item,tab}=target,tree=o.worktrees.find(t=>t.id===item.scope);
        const reference=item.kind==='link'?(tab?.url||item.url):'/demo/'+(tree?tree.repo+'/worktrees/'+tree.name+'/'+item.title:'workspace/'+(item.kind==='assistant'?'assistant/': 'objectives/'+o.id+'/')+item.title)+(tab?'#tab='+encodeURIComponent(tab.id):'');
        return {ref,item,tab,tree,title:tab?item.title+' · '+tab.title:item.title,kind:item.kind,reference};
      }
      function taskGlyph(o,task,customOnly=false) {const info=task.iconAsset&&assetInfo(o,task.iconAsset);if(info&&info.kind!=='task')return assetIcon(info);if(customOnly)return document.createDocumentFragment();const glyph=taskStatusIcon(task,'ob-task-default-icon');glyph.setAttribute('aria-hidden','true');return glyph;}
      function assetIcon(info) {
        if(!info)return icon('file-text');
        if(info.kind==='task')return taskGlyph(info.objective,info.task);
        if(info.kind==='link'){let service;try{const host=new URL(info.reference).hostname;service=host.endsWith('slack.com')?'slack':host==='github.com'?'github':host.endsWith('atlassian.net')?'jira':host==='docs.google.com'?'google-docs':host.includes('observe')||host.includes('grafana')?'grafana':null;}catch{}const glyph=element('span','scope-link-icon');glyph.setAttribute('aria-hidden','true');if(service)glyph.dataset.linkService=service;else glyph.textContent='↗';return glyph;}
        const ext=(info.item?.title||'').split('.').pop().toLowerCase(),type=info.kind==='notebook'||ext==='ipynb'?'nb':info.kind==='document'||ext==='md'?'md':ext==='sql'?'sql':null;
        if(type){const glyph=element('span','ft-icon ft-'+type);glyph.setAttribute('aria-hidden','true');return glyph;}
        return icon(info.kind==='worktree'?'git-branch':iconNames[info.kind]||'file-text');
      }
      function catalog(o) {return [...new Set([...o.worktrees.map(t=>'worktree::'+t.id),...o.items.filter(i=>i.kind!=='task'&&i.listed!==false&&!i.taskDocument).map(i=>i.id),...o.assetShelf,...o.objectiveAssets,...o.archiveAssets,...taskEntries(o).flatMap(t=>t.assets||[])])].filter(ref=>assetInfo(o,ref));}
      function taskContext(o,task) {
        const parent=parentTask(o,task);
        function assets(refs,owner) {return refs.filter(ref=>!o.archiveAssets.includes(ref)).map(ref=>{
          const info=assetInfo(o,ref),path=info?.item?.title||'';
          const type=owner&&ref===detailsRef(owner)?'Task specification':info?.kind==='worktree'?'Worktree':info?.kind==='folder'?'Folder':
            info?.kind==='link'?(info.tab?'Sublink':'Link'):info?.kind==='assistant'?(info.tab?'Assistant document tab':'Assistant document'):
            info?.tab?'Document tab':info?.kind==='notebook'||/\.ipynb$/i.test(path)?'Notebook':info?.kind==='document'||/\.md$/i.test(path)?'Document':/\.sql$/i.test(path)?'SQL file':'File';
          return {title:info?.title||'',type,reference:info?.reference};
        });}
        return {version:1,objective:{title:o.name,purpose:o.purpose||'',assets:assets(o.objectiveAssets)},parents:parent&&parent!==task?[{title:parent.title,assets:assets(taskAssetRefs(parent),parent)}]:[],task:{title:task.title,assets:assets(taskAssetRefs(task),task)}};
      }
      function dragAsset(node,o,ref) {node.draggable=true;node.ondragstart=e=>{
        try{
          const info=assetInfo(o,ref),payload=info?.task?taskContext(o,info.task):null,refs=payload?LabTaskContext.references(payload):[info?.reference].filter(Boolean);
          if(!refs.length){e.preventDefault();return;}
          e.dataTransfer.setData('application/x-objective-item',ref);e.dataTransfer.setData('application/x-objective-source',o.id);
          e.dataTransfer.setData('application/x-lab-reference',JSON.stringify(refs));
          if(payload)e.dataTransfer.setData(LabTaskContext.mime,JSON.stringify(payload));
          e.dataTransfer.setData('text/plain',payload?LabTaskContext.format(payload):refs.join('\n'));e.dataTransfer.effectAllowed='copyLink';
        }catch{e.preventDefault();message('Some task references are unavailable. Check the task assets.');}
      };node.ondragend=()=>root.querySelectorAll('.ob-drop').forEach(n=>n.classList.remove('ob-drop'));}

      function openTask(o,entry) {const doc=o.items.find(i=>i.id===entry.detail),tab=doc?.tabs.find(t=>t.id===entry.tab);if(!doc||!tab)return;o.activeTask=entry.id;o.expandedTask=parentTask(o,entry)?.id||null;openResource(o,doc,tab);}
      function attachAsset(o,task,ref) {const info=assetInfo(o,ref);if(!info||info.task){message('Drop a document, link, file, folder or worktree onto a task.');return;}task.assets ||= [];if(!taskAssetRefs(task).includes(ref))task.assets.push(ref);o.archiveAssets=o.archiveAssets.filter(r=>r!==ref);if(!o.assetShelf.includes(ref))o.assetShelf.push(ref);render();message(info.title+' attached to '+task.title);}
      function classifyAsset(o,ref,bucket,task) {
        const info=assetInfo(o,ref);if(!info||info.task)return;
        if(taskEntries(o).some(t=>detailsRef(t)===ref)&&bucket!=='objective'&&bucket!=='task'){message('Task details remain associated with their task.');return;}
        if(bucket==='task'){if(task)attachAsset(o,task,ref);return;}
        o.objectiveAssets=o.objectiveAssets.filter(r=>r!==ref);o.archiveAssets=o.archiveAssets.filter(r=>r!==ref);
        if(bucket==='objective')o.objectiveAssets.push(ref);
        else {taskEntries(o).forEach(t=>{t.assets=(t.assets||[]).filter(r=>r!==ref);if(t.iconAsset===ref)t.iconAsset=null;});if(bucket==='archive')o.archiveAssets.push(ref);}
        if(!o.assetShelf.includes(ref))o.assetShelf.push(ref);render();message(info.title+' moved to '+({objective:'Objective · pinned',archive:'Archive',unassigned:'Unassigned'}[bucket]));
      }
      function assetBucketDialog(o,ref) {const info=assetInfo(o,ref),form=dialog('Classify '+info.title),destination=field(form,'Bucket',select([{id:'unassigned',name:'Unassigned'},{id:'objective',name:'Objective · shared across tasks'},{id:'task',name:'Task'},{id:'archive',name:'Archive'}]));destination.value=o.archiveAssets.includes(ref)?'archive':o.objectiveAssets.includes(ref)?'objective':'unassigned';const task=field(form,'Task',select(taskEntries(o).map(t=>({id:t.id,name:t.title}))));task.value=o.activeTask||task.options[0]?.value||'';const sync=()=>{task.parentElement.hidden=destination.value!=='task';};destination.onchange=sync;sync();submit(form,'Move',()=>classifyAsset(o,ref,destination.value,taskEntries(o).find(t=>t.id===task.value)));}
      function starButton(o,ref) {
        const shared=o.objectiveAssets.includes(ref),title=assetInfo(o,ref)?.title||ref;
        const star=button(shared?'★':'☆','ob-quiet ob-star',()=>{
          if(o.objectiveAssets.includes(ref))o.objectiveAssets=o.objectiveAssets.filter(r=>r!==ref);
          else {o.objectiveAssets.push(ref);o.archiveAssets=o.archiveAssets.filter(r=>r!==ref);}
          if(!o.assetShelf.includes(ref))o.assetShelf.push(ref);render();message(title+(shared?' removed from shared context · task associations kept':' shared across the objective'));
        });
        star.setAttribute('aria-label',(shared?'Unstar ':'Star ')+title);star.setAttribute('aria-pressed',shared);star.title=shared?'Unstar · keep task associations':'Star · share across all tasks';return star;
      }
      function terminalDrop(node,o,ref) {attachDrop(node,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id&&t.objective===o.id),info=assetInfo(o,ref);if(!t||!info){message('Choose a terminal in '+o.name);return;}t.linked=ref;t.linkedTab=null;render();message('Linked '+t.name+' to '+info.title+' · launch folder kept');});}
      function assetRow(o,ref,task=null,controls=true) {
        const info=assetInfo(o,ref),line=element('div','ob-asset-line');line.dataset.asset=ref;if(!info)return line;
        const main=info.item?documentRow(info.item,o):button('','ob-resource',()=>{if(info.tree)o.selected=info.tree.id;renderOverview();message(info.title+' · '+info.reference);});
        if(ref==='folder::root'||ref==='folder::objective')line.classList.add('ob-fixed-root');
        if(!info.item)main.append(assetIcon(info),element('span','ob-label',info.title),element('span','ob-kind',info.kind==='worktree'?'Worktree':'Folder'));
        if(info.tab){line.replaceChildren(resourceRow(info.item,o,info.tab));}else line.append(main);
        const target=line.querySelector('.ob-resource')||main;dragAsset(target,o,ref);terminalDrop(target,o,ref);
        if(!controls)return line;
        const tools=element('div','ob-asset-tools');const menu=button('⋯','ob-quiet',()=>assetBucketDialog(o,ref));menu.setAttribute('aria-label','Classify '+info.title);tools.append(starButton(o,ref),menu);
        if(task&&ref!==detailsRef(task)){const remove=button('×','ob-quiet',()=>{task.assets=task.assets.filter(r=>r!==ref);if(task.iconAsset===ref)task.iconAsset=null;render();message('Detached '+info.title+' · source kept');});remove.setAttribute('aria-label','Detach '+info.title+' from '+task.title);tools.append(remove);}else if(task)tools.append(element('span','ob-required','Details'));
        (line.querySelector('.ob-resource-head')||line).append(tools);return line;
      }
      function renderBucket(host,o,id,label,refs,add,task) {const section=element('section','ob-bucket');section.dataset.bucket=id;section.setAttribute('aria-label',label);heading(section,label,add);if(id==='unassigned'){const title=section.querySelector('.ob-section-heading span');title.replaceWith(button(label,'ob-bucket-title',()=>showTasks(o)));}const list=element('div','ob-list');refs.forEach(ref=>{if(assetInfo(o,ref))list.append(assetRow(o,ref,task));});if(!refs.length)list.append(element('p','ob-empty',id==='unassigned'?'All assets are assigned.':id==='objective'?'Drop shared context here.':id==='archive'?'Drop assets here to set them aside.':''));section.append(list);attachDrop(section,'application/x-objective-item',ref=>id==='task'?task&&attachAsset(o,task,ref):classifyAsset(o,ref,id));host.append(section);}
      function sidebarTask(o,task,child=false) {
        const line=element('div','ob-sidebar-task'+(child?' child':''));line.dataset.task=task.id;
        const status=taskStatusIcon(task,'ob-task-status');status.dataset.done=taskComplete(task);status.setAttribute('aria-label',taskStatuses[taskStatus(task)].label);status.title=taskStatuses[taskStatus(task)].label+' · Secondary-click to change status';
        const name=button('','ob-task-name',()=>openTask(o,task)),glyph=element('span','ob-task-icon');glyph.dataset.taskIcon=task.id;glyph.title='Drop an asset here to use its icon';glyph.setAttribute('aria-label','Icon for '+task.title);glyph.append(taskGlyph(o,task,true));
        attachDrop(glyph,'application/x-objective-item',ref=>{const info=assetInfo(o,ref);if(!info||info.task)return;task.iconAsset=ref;attachAsset(o,task,ref);message('Using '+info.title+' icon for '+task.title);});
        name.append(element('span','ob-label',task.title));name.setAttribute('aria-pressed',o.activeTask===task.id);if(task.checks?.length)name.setAttribute('aria-expanded',o.expandedTask===task.id);dragAsset(name,o,task.id);
        line.oncontextmenu=event=>showTaskStatusMenu(event,o,task,line);
        line.onkeydown=event=>{if(event.key==='ContextMenu'||event.shiftKey&&event.key==='F10')showTaskStatusMenu(event,o,task,line);};
        line.append(status,name,element('span','ob-muted',String(taskAssetRefs(task).length)),glyph);dragAsset(glyph,o,task.id);attachDrop(line,'application/x-objective-item',ref=>attachAsset(o,task,ref));terminalDrop(line,o,task.id);return line;
      }
      function closeTaskStatusMenu() {taskStatusMenu?.remove();taskStatusMenu=null;}
      function showTaskStatusMenu(event,o,task,line) {
        event.preventDefault();event.stopPropagation();closeTaskStatusMenu();
        const menu=element('div','ob-task-status-menu'),anchor=line.querySelector('.ob-task-name');taskStatusMenu=menu;
        menu.setAttribute('role','menu');menu.setAttribute('aria-label','Status for '+task.title);menu.append(element('div','ob-task-status-menu-title',task.title));
        for(const status of ['done','todo','in_progress']){
          const option=button('','',()=>{closeTaskStatusMenu();setTaskStatus(o,task,status);render();});
          option.dataset.setTaskStatus=status;option.setAttribute('role','menuitemradio');option.setAttribute('aria-checked',taskStatus(task)===status);
          const icon=element('span','ob-task-status-icon',taskStatuses[status].icon);icon.dataset.taskStatus=status;option.append(icon,element('span','','Set to '+taskStatuses[status].label.toLowerCase()));menu.append(option);
        }
        menu.onkeydown=e=>{
          if(e.key==='Escape'){e.preventDefault();closeTaskStatusMenu();anchor?.focus();return;}
          const options=[...menu.querySelectorAll('button')],index=options.indexOf(document.activeElement);
          if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();options[e.key==='Home'?0:e.key==='End'?options.length-1:(index+(e.key==='ArrowDown'?1:-1)+options.length)%options.length].focus();}
          if(e.key==='Tab')closeTaskStatusMenu();
        };
        root.append(menu);const box=line.getBoundingClientRect(),bounds=menu.getBoundingClientRect();
        menu.style.left=Math.max(8,Math.min(event.clientX||box.left,innerWidth-bounds.width-8))+'px';menu.style.top=Math.max(8,Math.min(event.clientY||box.bottom,innerHeight-bounds.height-8))+'px';
        menu.querySelector('[aria-checked=true]').focus();
      }
      document.addEventListener('pointerdown',event=>{if(taskStatusMenu&&!taskStatusMenu.contains(event.target))closeTaskStatusMenu();});
      document.addEventListener('scroll',event=>{if(taskStatusMenu&&!taskStatusMenu.contains(event.target))closeTaskStatusMenu();},true);
      window.addEventListener('resize',closeTaskStatusMenu);
      function resourceTarget(o,ref) {const [id,tabId]=ref.split('::');const item=o.items.find(i=>i.id===id);if(tabId&&!item?.tabs?.some(t=>t.id===tabId))return null;return item?{item,tab:item.tabs?.find(t=>t.id===tabId)}:null;}
      function openResource(o,item,tab=null) {if(item.kind==='task'){openTask(o,item);return;}o.expandedResource=item.tabs?.length?item.id:null;o.view='resource';o.selectedItem=item.id;o.selectedTab=tab?.id||null;if(item.scope)o.selected=item.scope;if(tab&&!o.activeTask)retainTabs(o,item);if(o.activeTask&&tab)o.expandedResource=null;render();}
      function resourceRow(item,o,tab=null) {
        const row=button('','ob-resource'+(tab?' ob-subtab':''),e=>{if(item.kind==='link'&&!e.metaKey&&!e.ctrlKey){message('Would open '+(tab?.url||item.url)+' · demo keeps external sites closed');return;}openResource(o,item,tab);});row.dataset.item=item.id;if(tab)row.dataset.tab=tab.id;row.dataset.selected=o.view==='resource'&&o.selectedItem===item.id&&(o.selectedTab||null)===(tab?.id||null);row.draggable=true;row.setAttribute('aria-label',tab?'Open subtab '+tab.title+' in '+item.title:item.title+' · '+item.kind);row.title=tab?item.title+' / '+tab.title:'Drag onto a task or asset bucket';
        dragAsset(row,o,item.id+(tab?'::'+tab.id:''));
        row.append(assetIcon(assetInfo(o,item.id+(tab?'::'+tab.id:''))),element('span','ob-label',tab?tab.title:item.title));
        if(item.kind==='assistant'&&!tab)row.append(element('span','ob-kind','Assistant'));
        attachDrop(row,'application/x-objective-terminal',id=>{const t=terminals.find(t=>t.id===id);if(t&&t.objective===o.id){t.linked=item.id;t.linkedTab=tab?.id||null;render();message('Linked '+t.name+' to '+(tab?.title||item.title)+' · launch folder kept');}else{message('Choose a terminal in '+o.name+' to link this resource');}});
        return row;
      }
      function retainTabs(o,item) {const state=o.tabShelf[item.id] ||= {until:0,pinned:[]};o.expandedResource=item.id;state.until=0;state.pinned ||= [];}
      function subtabList(wrapper,item,o) {
        let list=wrapper.querySelector('.ob-subtabs');if(!list){list=element('div','ob-subtabs');wrapper.append(list);}list.replaceChildren();
        const state=o.tabShelf[item.id]||{until:0,pinned:[]},visible=item.tabs.filter(tab=>o.expandedResource===item.id||state.pinned?.includes(tab.id));
        visible.forEach(tab=>{const line=element('div','ob-subtab-line'),pin=button(state.pinned.includes(tab.id)?'◆':'◇','ob-pin',()=>{const shelf=o.tabShelf[item.id] ||= {until:0,pinned:[]};if(shelf.pinned.includes(tab.id))shelf.pinned=shelf.pinned.filter(id=>id!==tab.id);else shelf.pinned.push(tab.id);subtabList(wrapper,item,o);persist();});pin.setAttribute('aria-label','Pin subtab '+tab.title);pin.setAttribute('aria-pressed',state.pinned.includes(tab.id));pin.title=state.pinned.includes(tab.id)?'Pinned · click to unpin':'Keep this subtab in the sidebar';line.append(resourceRow(item,o,tab),starButton(o,item.id+'::'+tab.id),pin);list.append(line);});
      }
      function documentRow(item,o) {
        if(!item.tabs?.length)return resourceRow(item,o);
        const wrapper=element('div','ob-document-group'),head=element('div','ob-resource-head'),expand=button('⌄','ob-expand',()=>{o.expandedResource=o.expandedResource===item.id?null:item.id;subtabList(wrapper,item,o);persist();});expand.setAttribute('aria-label','Show subtabs for '+item.title);expand.title='Hover for 1.5 seconds, or click to show subtabs';head.append(resourceRow(item,o),expand);wrapper.append(head);subtabList(wrapper,item,o);
        wrapper.onmouseenter=()=>{clearTimeout(hoverTimers.get(wrapper));hoverTimers.set(wrapper,setTimeout(()=>{hoverTimers.delete(wrapper);if(!wrapper.isConnected||selected!==o.id)return;retainTabs(o,item);subtabList(wrapper,item,o);persist();message('Subtabs revealed. Pin a subtab to keep it.');},item.kind==='link'?1000:hoverDelay));};
        wrapper.onmouseleave=()=>{clearTimeout(hoverTimers.get(wrapper));hoverTimers.delete(wrapper);};return wrapper;
      }
      function renderOverview() {
        const host=find('overview'),o=objective();host.replaceChildren();hoverTimers.forEach(clearTimeout);hoverTimers.clear();
        renderBucket(host,o,'unassigned','UNASSIGNED',catalog(o).filter(ref=>!o.objectiveAssets.includes(ref)&&!o.archiveAssets.includes(ref)&&!taskEntries(o).some(t=>taskAssetRefs(t).includes(ref))),()=>itemDialog());
        renderBucket(host,o,'objective','OBJECTIVE · PINNED',o.objectiveAssets,settingsDialog);
        const section=element('section','ob-sidebar-tasks');section.dataset.bucket='tasks';heading(section,'TASKS');section.querySelector('.ob-section-heading').append(progressBadge(o));section.append(button('All tasks','ob-quiet',()=>showTasks(o)));
        const tasks=o.items.filter(i=>i.kind==='task'),list=element('div','ob-sidebar-task-list');list.style.setProperty('--ob-task-rows',Math.max(1,tasks.length+Math.max(0,...tasks.map(t=>t.checks.length))));
        tasks.forEach(t=>{list.append(sidebarTask(o,t));if(o.expandedTask===t.id)t.checks.forEach(c=>list.append(sidebarTask(o,c,true)));});section.append(list);host.append(section);
        const task=activeTask(o);renderBucket(host,o,'task','TASK ASSETS'+(task?' · '+task.title.toUpperCase():''),task?taskAssetRefs(task):[],null,task);
        if(!task)host.querySelector('[data-bucket=task]').append(element('p','ob-empty','Select a task to see its assets.'));
        const archive=element('details','ob-archive');archive.open=o.archiveOpen===true;archive.ontoggle=()=>{o.archiveOpen=archive.open;persist();};const summary=element('summary','','Archive · '+o.archiveAssets.length);archive.append(summary);attachDrop(archive,'application/x-objective-item',ref=>classifyAsset(o,ref,'archive'));renderBucket(archive,o,'archive','ARCHIVED ASSETS',o.archiveAssets);host.append(archive);
        const scopes=element('section','ob-worktree-roots');heading(scopes,'WORKTREES',worktreeDialog);['folder::root','folder::objective'].forEach(ref=>scopes.append(assetRow(o,ref,null,false)));host.append(scopes);
        const explorer=element('details','ob-explorer');explorer.open=o.explorerOpen===true;explorer.ontoggle=()=>{o.explorerOpen=explorer.open;persist();};explorer.append(element('summary','','Files'));
        const tree=o.worktrees.find(t=>t.id===o.selected);if(tree){heading(explorer,'RECENTLY UPDATED');o.items.filter(i=>i.scope===tree.id&&i.listed===false).slice(0,2).forEach(i=>explorer.append(fileButton(i.title,o,tree)));heading(explorer,'FILES · '+tree.name,()=>itemDialog('file',tree.id));const files=o.items.filter(i=>i.scope===tree.id&&i.listed===false);const folders=[...new Set(files.filter(i=>i.title.includes('/')).map(i=>i.title.split('/')[0]+'/'))].sort();folders.forEach(folder=>{const id=o.id+'/'+tree.id+'/'+folder,b=button('','ob-file',()=>{openFolders.has(id)?openFolders.delete(id):openFolders.add(id);renderOverview();persist();});b.setAttribute('aria-expanded',openFolders.has(id));b.append(icon('folder'),element('span','',folder));const ref='folder::'+tree.id+'::'+folder;dragAsset(b,o,ref);terminalDrop(b,o,ref);explorer.append(b);if(openFolders.has(id))files.filter(i=>i.title.startsWith(folder)).forEach(i=>explorer.append(fileButton(i.title,o,tree)));});files.filter(i=>!i.title.includes('/')).forEach(i=>explorer.append(fileButton(i.title,o,tree)));}host.append(explorer);
      }
      function fileButton(path,o,tree) {
        const getItem=()=>o.items.find(i=>i.title===path&&i.scope===tree.id&&i.listed===false);
        const row=resourceRow(getItem(),o);row.className='ob-file';return row;
      }
      function renderReader() {
        const host=find('reader'),o=objective();host.replaceChildren();
        if(o.view==='all'){renderLibrary(host,o);return;}
        if(o.view==='tasks'){renderTasks(host,o);return;}
        const task=activeTask(o);if(task){
          const close=button('×','ob-close-task',()=>showTasks(o));close.setAttribute('aria-label','Close task mode');
          const top=element('div','ob-task-mode-head'),title=element('h2'),open=button('','ob-task-mode-title',()=>openTask(o,task));open.append(taskGlyph(o,task),element('span','',task.title));title.append(open);
          const complete=element('label','ob-task-completion'),toggle=element('input');toggle.type='checkbox';toggle.checked=taskComplete(task);toggle.setAttribute('aria-label','Complete '+task.title);toggle.onchange=()=>setTaskComplete(task,toggle.checked);complete.append(toggle,element('span','',toggle.checked?'Completed':'Mark complete'));
          top.append(title,complete,button('Edit task','ob-quiet',()=>taskEditDialog(parentTask(o,task),task)));host.append(close,top);
        }
        const item=o.items.find(i=>i.id===o.selectedItem)||o.items.find(i=>i.kind!=='task');if(!item){host.append(element('p','ob-muted','Choose or create a document, notebook, or link.'));return;}
        if(item.kind==='task'){o.view='tasks';renderTasks(host,o);return;}
        const tab=item.tabs?.find(t=>t.id===o.selectedTab),content=tab||item,taskDetails=task&&detailsRef(task)===item.id+'::'+tab?.id;
        if(!taskDetails){const top=element('div','ob-reader-head');top.append(element('h2','',content.title));top.append(button(tab?'Rename subtab':'Rename','ob-quiet',()=>tab?renameSubtabDialog(item,tab):renameDialog(item)));host.append(top);}
        const trail=element('div','ob-breadcrumb');trail.append(button('← Tasks','ob-quiet',()=>showTasks(o)),element('span','ob-muted',o.name+' / '+(item.scope?o.worktrees.find(t=>t.id===item.scope).name:'Objective')+(tab?' / '+item.title:'')));host.append(trail);
        if(item.kind==='notebook')renderNotebook(host,item);
        else if(item.kind==='link'){const url=field(host,'URL',element('input')),tldr=field(host,'TL;DR',element('textarea','ob-editor'));url.type='url';url.value=content.url||item.url;tldr.value=content.tldr||item.tldr||'';url.oninput=()=>{content.url=url.value;persist();};tldr.oninput=()=>{content.tldr=tldr.value;persist();};host.append(button('Open ↗','ob-action',()=>message('Would open '+url.value+' · demo only')));}
        else {
          const preview=element('article','ob-document-preview');if(item.kind==='file'&&!item.title.endsWith('.md')&&!tab)preview.append(element('pre','',content.body||''));else renderMarkdown(preview,content.body||'No notes yet.');host.append(preview);
          if(item.kind==='assistant')host.append(element('p','ob-muted','Simulated Assistant reference · original content stays in Assistant.'));
          else if((item.kind==='document'||item.kind==='file'&&item.title.endsWith('.md'))&&window.LabMarkdownEditor){
            preview.remove();const key=o.id+'::'+item.id+'::'+(tab?.id||'');let draft=documentEditors.get(key);if(!draft){const node=element('div','assistant-note-editor ob-native-editor');draft={node,input:window.LabMarkdownEditor.create(node,{body:content.body||'',onChange:text=>{content.body=text;item.updated=Date.now();persist();},onSave:()=>{persist();message('Saved simulated document');}})};documentEditors.set(key,draft);}host.append(draft.node);host.append(element('p','ob-muted','Click to edit · / for commands · saved in this demo'));
          } else {
            const edit=button(content.editing?'Done editing':'Edit content','ob-action',()=>{content.editing=!content.editing;renderReader();persist();});host.append(edit);
            if(content.editing){const editor=element('textarea','ob-editor');editor.setAttribute('aria-label',tab?'Edit simulated subtab content':'Edit simulated file content');editor.value=content.body||'';editor.oninput=()=>{content.body=editor.value;item.updated=Date.now();persist();};host.append(editor);}
          }

        }
        const linked=terminals.filter(t=>t.objective===o.id&&(t.linked===task?.id||t.linked===item.id&&(t.linkedTab||null)===(tab?.id||null)||t.linked===item.id+(tab?'::'+tab.id:''))); if(linked.length){host.append(element('h3','','Linked terminals'));linked.forEach(t=>host.append(button(t.name,'ob-resource',()=>selectTerminal(t))));}
        const actions=element('div','ob-reader-actions');actions.append(button(taskDetails?'Link task to terminal':'Link terminal','ob-action',()=>linkTerminalDialog(taskDetails?task:item,taskDetails?null:tab))); if((item.kind==='document'||item.kind==='file'&&item.title.endsWith('.md'))&&!tab)actions.append(button('+ Subtab','ob-action',()=>subtabDialog(item)));if(!tab)actions.append(button('Delete item','ob-quiet',()=>deleteDialog(item)));host.append(actions);
      }
      function renderTasks(host,o) {
        const top=element('div','ob-reader-head');top.append(element('h2','','Tasks'),button('+ Task','ob-action',()=>itemDialog('task')));host.append(top,element('p','ob-muted',o.name+' · '+(o.purpose||'Define the outcome for this objective.')));
        const summary=element('div','ob-task-summary');summary.append(progressBadge(o),element('span','',taskProgress(o).label));host.append(summary);
        const list=element('div','ob-task-list');o.items.filter(i=>i.kind==='task').forEach(task=>{list.append(taskLine(o,task,task));if(o.expandedTask===task.id)task.checks.forEach(check=>list.append(taskLine(o,task,check)));});host.append(list);
        if(!list.childElementCount)host.append(element('p','ob-muted','Add a task to start. Its details document and subtab are created with it.'));
        host.append(element('p','ob-task-legend','▤ opens the task’s document subtab. Dates apply to unfinished work; subtasks inherit their parent’s deadline until you set one.'));
      }
      function taskLine(o,task,entry) {
        const child=entry!==task,row=element('div','ob-task-row'+(child?' ob-task-child':'')),check=element('input');row.dataset.task=entry.id;check.type='checkbox';check.checked=child?entry.done:taskComplete(task);check.setAttribute('aria-label','Complete '+(child?'subtask ':'task ')+entry.title);check.onchange=()=>{setTaskStatus(o,entry,check.checked?'done':'todo');render();};
        const title=button(entry.title,'ob-task-title',()=>openTask(o,entry));title.title=entry.title;title.dataset.done=check.checked;dragAsset(title,o,entry.id);
        const doc=o.items.find(i=>i.id===entry.detail),tab=doc?.tabs.find(t=>t.id===entry.tab),details=button('▤','ob-task-doc',()=>openTask(o,entry));details.setAttribute('aria-label','Open details for '+entry.title);details.title=doc.title+' / '+tab.title;
        const due=element('input','ob-task-due');due.type='date';due.value=entry.due||'';due.setAttribute('aria-label','Due date for '+entry.title);due.title=child&&!entry.due&&task.due?'Inherits '+task.due:'Due date';due.onchange=()=>{entry.due=due.value;render();};const days=dayNumber(entry.due||task.due);if(!check.checked&&days!==null)due.dataset.status=days<dayNumber(localDate())?'overdue':days<=dayNumber(localDate())+2?'risk':'track';
        const actions=element('div','ob-task-actions'),edit=button('⋯','ob-quiet',()=>taskEditDialog(task,entry));edit.setAttribute('aria-label','Edit '+entry.title);actions.append(edit);if(!child){const add=button('+','ob-quiet',()=>todoDialog(task));add.setAttribute('aria-label','Add subtask to '+task.title);actions.append(add);}
        row.append(check,title,details,due,actions);attachDrop(row,'application/x-objective-item',ref=>attachAsset(o,entry,ref));return row;
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
      function selectTerminal(t) {selected=t.objective;const o=objective();if(t.tree!=='objective')o.selected=t.tree;activeTerminal=t.id;const info=assetInfo(o,t.linked+(t.linkedTab?'::'+t.linkedTab:''));if(info?.task){openTask(o,info.task);}else if(info?.item){o.activeTask=null;openResource(o,info.item,info.tab);}else {o.view='tasks';o.activeTask=null;render();}message(t.name+' · launch folder kept');}
      function renderTerminals() {
        const host=find('terminals');host.replaceChildren();const head=element('div','ob-terminal-heading');head.append(element('strong','','TERMINAL'));const mode=element('select');mode.setAttribute('aria-label','Visible terminal groups');[['all','5 objectives'],['selected','Selected objective']].forEach(([value,label])=>{const opt=element('option','',label);opt.value=value;mode.append(opt);});mode.value=config.terminalVisibility;mode.onchange=()=>{config.terminalVisibility=mode.value;renderTerminals();persist();};head.append(mode);host.append(head);
        const surface=element('div','ob-terminal-surface'),rail=element('div','ob-terminal-groups');surface.append(rail);host.append(surface);
        focused.filter(id=>config.terminalVisibility==='all'||id===selected).forEach(id=>{const o=objectives.find(o=>o.id===id),group=element('section','ob-terminal-project');group.style.setProperty('--objective-color',o.color);group.dataset.active=id===selected;const heading=element('div','ob-terminal-objective');heading.append(button(o.name,'',()=>switchObjective(id)));group.append(heading);rail.append(group);
          [{id:'objective',name:'Objective folder',color:'#8b949e'},...o.worktrees].forEach(tree=>{const sessions=terminals.filter(t=>t.objective===id&&t.tree===tree.id);sessions.forEach((t,index)=>{const info=assetInfo(o,t.linked+(t.linkedTab?'::'+t.linkedTab:'')),b=button('','ob-terminal',()=>selectTerminal(t));b.style.setProperty('--tree-color',id===selected?tree.color:'#8b949e');b.dataset.terminal=t.id;b.dataset.treeStart=index===0;b.setAttribute('aria-pressed',t.id===activeTerminal);b.setAttribute('aria-label',t.name+' terminal'+(info?' linked to '+info.title:''));b.draggable=true;b.ondragstart=e=>{e.dataTransfer.setData('application/x-objective-terminal',t.id);e.dataTransfer.effectAllowed='link';};
            attachDrop(b,'application/x-objective-item',ref=>{const target=o.id===selected&&assetInfo(o,ref);if(target){t.linked=ref;t.linkedTab=null;render();message('Linked '+t.name+' to '+target.title+' · launch folder kept');}else message('Choose an item from '+o.name);});
            b.append(info?assetIcon(info):icon('terminal'),element('span','ob-label',info?.title||t.name));const dot=element('span','ob-status-dot'+(t.state==='ready'?' ready':t.state==='idle'?' idle':''));dot.setAttribute('aria-label',t.state==='ready'?'Ready to review':t.state==='working'?'Working':'Idle');b.append(dot);group.append(b);});});
        });
        rail.append(button('+ New','ob-action ob-new-terminal',terminalDialog));
        const t=terminals.find(t=>t.id===activeTerminal);if(t){const o=objectives.find(o=>o.id===t.objective),console=element('div','ob-console');console.dataset.console=t.id;const tree=o.worktrees.find(w=>w.id===t.tree),folder=tree?'/demo/'+tree.repo+'/worktrees/'+tree.name:'/demo/workspace/objectives/'+o.id;console.append(element('strong','',t.name),element('p','ob-muted',folder),element('pre','ob-console-log',(t.logs||[]).join('\n\n')));const label=element('label','','Command or prompt'),draft=element('textarea','ob-editor');draft.value=t.draft;draft.setAttribute('aria-label','Unsent prompt for '+t.name);draft.oninput=()=>{t.draft=draft.value;persist();};label.append(draft);console.append(label,button('Run simulation','ob-action',()=>runCommand(t)),element('div','ob-console-note','Drop an asset to paste its reference. Drop a task for a prompt with Objective, parent and current-task context. Nothing is submitted until Run simulation.'));
          attachDrop(console,'application/x-objective-item',(ref,transfer)=>{
            try{
              const info=assetInfo(objective(),ref),payload=info?.task?JSON.parse(transfer.getData(LabTaskContext.mime)):null,refs=payload?LabTaskContext.references(payload):[info?.reference].filter(Boolean);
              if(!refs.length)return;
              const quote=value=>"'"+value.replace(/'/g,"'\"'\"'")+"'",prompt=payload?LabTaskContext.format(payload):refs.map(quote).join(' ');
              t.draft=(t.draft?t.draft+(payload?'\n\n':' '):'')+prompt;
              renderTerminals();persist();message(payload?'Pasted task prompt with labelled context · unsent':'Pasted '+refs.length+' references · unsent');
            }catch{message('Could not read the complete task context. Drag the task again.');}
          });

          if(t.linked)console.append(button('Unlink item','ob-quiet',()=>{t.linked=null;t.linkedTab=null;render();}));surface.append(console);}
      }
      function dialog(title) {const host=find('dialog');host.hidden=false;host.replaceChildren(element('h3','',title));const form=element('form');host.append(form);form.append(button('Cancel','ob-quiet',()=>{host.hidden=true;}));return form;}
      function field(form,labelText,control) {const label=element('label','',labelText);control.setAttribute('aria-label',labelText);label.append(control);form.insertBefore(label,form.lastChild);return control;}
      function select(options) {const el=element('select');options.forEach(o=>{const opt=element('option','',o.name);opt.value=o.id;el.append(opt);});return el;}
      function submit(form,label,action) {const b=button(label,'ob-action');b.type='submit';form.insertBefore(b,form.lastChild);form.onsubmit=e=>{e.preventDefault();action();find('dialog').hidden=true;render();};}
      function focusDialog(position=null,choice=null) {
        const form=dialog('Bring an objective into focus'),pick=field(form,'Objective',select([...objectives,{id:'__new',name:'Create a new objective…'}]));if(choice)pick.value=choice;const name=field(form,'New objective name',element('input'));name.type='text';const sync=()=>{name.parentElement.hidden=pick.value!=='__new';name.required=pick.value==='__new';};pick.onchange=sync;sync();const slot=field(form,'Insert at slot',select(Array.from({length:focusSlots},(_,i)=>({id:String(i),name:'Slot '+(i+1)}))));slot.value=String(position??0);submit(form,'Insert',()=>{let o=objectives.find(o=>o.id===pick.value);if(pick.value==='__new'){o={id:'objective-'+serial++,name:name.value.trim(),purpose:'Define an outcome',color:'#8b949e',selected:null,selectedItem:null,worktrees:[],items:[],recent:[],files:[]};normalizeObjective(o);objectives.push(o);}if(o)insertObjective(o.id,Number(slot.value));});
      }
      function itemDialog(kind='document',scope=null) {
        const form=dialog(kind==='file'?'Create a simulated worktree file':'Add an objective resource');const kinds=kind==='file'?['file','notebook','document']:['document','notebook','task','link','assistant'];const type=field(form,'Type',select(kinds.map(id=>({id,name:id==='assistant'?'Assistant document reference':id[0].toUpperCase()+id.slice(1)}))));type.value=kind;const input=field(form,'Name',element('input'));input.type='text';input.required=true;if(kind==='file')input.placeholder='notes/findings.md';const url=field(form,'URL for a link',element('input'));url.type='text';const due=field(form,'Due date',element('input'));due.type='date';type.onchange=()=>{url.parentElement.hidden=type.value!=='link';due.parentElement.hidden=type.value!=='task';};type.onchange();
        submit(form,'Create',()=>{const o=objective(),k=type.value;let title=input.value.trim();if(k==='notebook'&&!title.endsWith('.ipynb'))title+='.ipynb';const item={id:'item-'+serial++,kind:k,title,scope,body:k==='assistant'?'Simulated reference to an existing Assistant document.':'',source:'',url:url.value,listed:kind==='file'?false:true,updated:Date.now(),checks:k==='task'?[]:undefined,done:false,due:due.value};o.items.push(item);normalizeObjective(o);o.selectedItem=item.id;o.selectedTab=null;o.activeTask=null;o.view=k==='task'?'tasks':'resource';message('Created '+title+(k==='task'?' with a details document subtab':'')+' in '+o.name+' · demo data');});
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
      function settingsDialog() {const form=dialog('Objective settings'),o=objective(),input=field(form,'Objective name',element('input'));input.type='text';input.value=o.name;input.required=true;const goal=field(form,'Outcome',element('input'));goal.type='text';goal.value=o.purpose||'';submit(form,'Save',()=>{o.name=input.value.trim();o.purpose=goal.value;message('Objective settings updated');});}
      function todoDialog(item) {const form=dialog('Add a subtask'),input=field(form,'Subtask',element('input'));input.type='text';input.required=true;const due=field(form,'Due date (optional)',element('input'));due.type='date';submit(form,'Add',()=>{const entry={id:'subtask-'+serial++,title:input.value.trim(),done:false,due:due.value};item.checks.push(entry);ensureDetails(objective(),item,entry);message('Subtask created with its own document subtab');});}
      function taskEditDialog(task,entry) {
        const o=objective(),form=dialog('Edit '+(entry===task?'task':'subtask')),name=field(form,'Name',element('input'));name.type='text';name.required=true;name.value=entry.title;
        const due=field(form,'Due date',element('input'));due.type='date';due.value=entry.due||'';
        const doc=field(form,'Details document',select(o.items.filter(i=>i.kind==='document').map(i=>({id:i.id,name:i.title}))));doc.value=entry.detail;
        const tab=field(form,'Document subtab',select([]));doc.onchange=()=>{tab.replaceChildren();[{id:'__new',title:'Create a subtab for this task'},...(o.items.find(i=>i.id===doc.value)?.tabs||[])].forEach(t=>{const option=element('option','',t.title);option.value=t.id;tab.append(option);});tab.value=doc.value===entry.detail?entry.tab:'__new';};doc.onchange();
        const remove=button(entry===task?'Delete task':'Delete subtask','ob-quiet',()=>{if(entry===task)deleteDialog(task);else {const complete=taskComplete(task);task.checks.splice(task.checks.indexOf(entry),1);if(!task.checks.length)task.done=complete;find('dialog').hidden=true;render();}});form.insertBefore(remove,form.lastChild);
        submit(form,'Save',()=>{const oldTitle=entry.title;entry.title=name.value.trim();entry.due=due.value;entry.detail=doc.value;entry.tab=tab.value==='__new'?null:tab.value;ensureDetails(o,task,entry);const details=o.items.find(i=>i.id===entry.detail).tabs.find(t=>t.id===entry.tab);if(details.title===oldTitle)details.title=entry.title;message('Task details and deadline updated');});
      }
      function subtabDialog(item) {const form=dialog('New document subtab'),name=field(form,'Subtab name',element('input'));name.type='text';name.required=true;submit(form,'Create',()=>{const tab={id:'tab-'+serial++,title:name.value.trim(),body:'# '+name.value.trim()+'\n\nAdd your notes here.'};item.tabs ||= [];item.tabs.push(tab);const o=objective();o.selectedItem=item.id;o.selectedTab=tab.id;o.view='resource';retainTabs(o,item);message('Created a document subtab · tabs live in the left menu');});}
      function renameSubtabDialog(item,tab) {const form=dialog('Rename document subtab'),name=field(form,'Name',element('input'));name.type='text';name.required=true;name.value=tab.title;submit(form,'Rename',()=>{tab.title=name.value.trim();message('Renamed subtab · task and terminal links remain intact');});}
      function linkTerminalDialog(item,tab=null) {const form=dialog('Link an existing simulated terminal'),pick=field(form,'Terminal',select(terminals.filter(t=>t.objective===selected).map(t=>({id:t.id,name:t.name}))));if(!pick.options.length){form.insertBefore(element('p','ob-muted','Create a terminal with + Terminal first.'),form.lastChild);return;}submit(form,'Link',()=>{const terminal=terminals.find(t=>t.id===pick.value);terminal.linked=item.id;terminal.linkedTab=tab?.id||null;message('Item linked · terminal launch folder kept');});}
      function deleteDialog(item) {const o=objective(),form=dialog('Delete '+item.title+' from the demo?');if(o.items.filter(i=>i.kind==='task').some(t=>t.detail===item.id||t.checks.some(c=>c.detail===item.id))){form.insertBefore(element('p','ob-muted','This document describes a task. Choose a different details document in the task’s edit menu before deleting it.'),form.lastChild);return;}submit(form,'Delete',()=>{o.items.splice(o.items.indexOf(item),1);const kept=ref=>ref!==item.id&&!ref.startsWith(item.id+'::');o.objectiveAssets=o.objectiveAssets.filter(kept);o.archiveAssets=o.archiveAssets.filter(kept);o.assetShelf=o.assetShelf.filter(kept);taskEntries(o).forEach(t=>{t.assets=(t.assets||[]).filter(kept);if(t.iconAsset&&!kept(t.iconAsset))t.iconAsset=null;});if(o.activeTask===item.id)o.activeTask=null;terminals.filter(t=>t.objective===o.id&&t.linked===item.id).forEach(t=>{t.linked=null;t.linkedTab=null;});delete o.tabShelf[item.id];o.selectedItem=o.items.find(i=>i.listed!==false)?.id||null;o.selectedTab=null;if(item.kind==='task')o.view='tasks';message('Deleted simulated item · linked sessions remain');});}
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
        else if(command==='done'){const item=taskEntries(o).find(i=>i.id===t.linked);if(item){setTaskStatus(o,item,'done');output='Linked task complete.';}else output='Link this terminal to a task first.';}
        else output='Simulated agent completed: '+command;
        t.logs=[...(t.logs||[]),'$ '+command,output].slice(-40);t.draft='';t.state='ready';render();message(t.name+' · simulated result ready to review');
      }
      function render() {closeTaskStatusMenu();renderFocus();renderOverview();renderReader();renderTerminals();persist();}
      render();
      let currentDay=localDate();setInterval(()=>{if(localDate()!==currentDay){currentDay=localDate();renderFocus();renderOverview();if(objective().view==='tasks')renderReader();}},60000);
      find('reset').onclick=()=>{const form=dialog('Reset all simulated changes?');submit(form,'Reset demo',()=>{restore(JSON.parse(JSON.stringify(fresh)));message('Demo reset to its sample data');});};
      if(window.parent!==window)window.parent.postMessage({channel,type:'ready'},'*');else hydrated=true;
    })();
