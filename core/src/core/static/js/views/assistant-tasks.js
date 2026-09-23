(function () {
  'use strict';
  const state = {doc:null,options:null,host:null,scope:null,tab:'dashboard',busy:false,showAll:false,wipOnly:false,form:null,highlightId:null};
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const key = name => 'lab.assistant.tasks.v1:' + state.options.database + ':' + name;
  const get = (name, fallback) => { try { return JSON.parse(localStorage.getItem(key(name))) ?? fallback; } catch (_) { return fallback; } };
  const put = (name, value) => { try { localStorage.setItem(key(name), JSON.stringify(value)); } catch (_) {} };
  const children = (doc, id) => doc.tasks.filter(task => task.parent_id === id);
  const statusLabels = {not_started:'Pendiente', in_progress:'En progreso · WIP', blocked:'Bloqueada', done:'Completada', skipped:'Omitida', cancelled:'Cancelada'};
  const taskStatus = task => task.status || (task.done ? 'done' : 'not_started');
  const statusOptions = selected => Object.entries(statusLabels).map(([value,label]) => `<option value="${value}"${selected === value ? ' selected' : ''}>${label}</option>`).join('');
  const hasWip = (doc, tabId) => doc.tasks.some(task => linkedTab(doc, task) === tabId && taskStatus(task) === 'in_progress');
  function done(doc, task) { return ['done','skipped'].includes(taskStatus(task)); }

  function partial(doc, task) {
    return !done(doc, task) && children(doc, task.id).some(child => done(doc, child) || partial(doc, child));
  }
  function linkedTab(doc, task) {
    if (task.tab_id) return task.tab_id;
    const parent = doc.tasks.find(row => row.id === task.parent_id);
    return parent ? linkedTab(doc, parent) : null;
  }
  function progress(doc, tasks = doc.tasks) {
    const leaves = tasks.filter(task => !children(doc, task.id).length);
    return {done:leaves.filter(task => done(doc, task)).length, total:leaves.length};
  }
  const priorityOptions = selected => ['P0','P1','P2','P3'].map(value => `<option value="${value}"${selected === value ? ' selected' : ''}>${value} · ${{P0:'Urgent',P1:'Important',P2:'Normal',P3:'Someday'}[value]}</option>`).join('');
  const tabOptions = (doc, selected, inherited = false) => `<option value="">${inherited ? 'Follow parent tab' : 'No linked tab'}</option>` + doc.tabs.map(tab => `<option value="${esc(tab.id)}"${selected === tab.id ? ' selected' : ''}>${esc(tab.title)}</option>`).join('');

  function highlightedBranch(doc, task) {
    let row = doc.tasks.find(item => item.id === state.highlightId);
    const seen = new Set();
    while (row && !seen.has(row.id)) {
      if (row.id === task.id) return true;
      seen.add(row.id); row = doc.tasks.find(item => item.id === row.parent_id);
    }
    return false;
  }

  function taskRow(doc, task, scope, depth = 0) {
    const nested = children(doc, task.id).filter(child => scope.has(child.id));
    const completed = done(doc, task), tab = doc.tabs.find(tab => tab.id === linkedTab(doc, task));
    const collapsed = get(doc.id + ':collapsed', []), expanded = highlightedBranch(doc,task) || state.showAll && !collapsed.includes(task.id);
    const allChildren = children(doc, task.id);
    const label = task.title;
    return `<li class="assistant-tasks-task${completed ? ' is-done' : ''}${state.highlightId === task.id ? ' is-terminal-target' : ''}" tabindex="-1" data-task="${esc(task.id)}" data-terminal-document="${esc(doc.id)}" data-terminal-task="${esc(task.id)}">
      <div class="assistant-tasks-task-row">
        ${nested.length && (state.showAll || highlightedBranch(doc,task)) ? `<button type="button" class="assistant-tasks-disclosure" data-collapse="${esc(task.id)}" aria-label="${expanded ? 'Hide' : 'Show'} subtasks for ${esc(label)}" aria-expanded="${expanded}">${expanded ? '▾' : '▸'}</button>` : '<span class="assistant-tasks-disclosure"></span>'}
        <input type="checkbox" data-check="${esc(task.id)}" aria-label="Complete ${esc(label)}"${completed ? ' checked' : ''}${state.busy ? ' disabled' : ''}>
        ${tab ? `<a class="assistant-tasks-task-label" href="#assistant-tasks-tab=${encodeURIComponent(tab.id)}" data-open-tab="${esc(tab.id)}" title="Open ${esc(tab.title)}">` : '<div class="assistant-tasks-task-label">'}<span>${esc(label)}</span>${allChildren.length ? `<small>${allChildren.filter(child => done(doc, child)).length}/${allChildren.length} subtasks</small>` : ''}${tab ? '</a>' : '</div>'}
        <span data-linked-terminal></span>
        ${task.due ? `<small class="assistant-tasks-task-due">${esc(task.due)}</small>` : ''}<select class="assistant-tasks-status status-${esc(taskStatus(task))}" data-status="${esc(task.id)}" aria-label="Estado de ${esc(label)}"${state.busy ? ' disabled' : ''}>${statusOptions(taskStatus(task))}</select>
        <select class="assistant-tasks-priority priority-${esc(task.priority)}" data-priority="${esc(task.id)}" aria-label="Priority for ${esc(label)}"${state.busy ? ' disabled' : ''}>${priorityOptions(task.priority)}</select>
        <details class="assistant-tasks-task-menu"><summary aria-label="Options for ${esc(label)}">⋯</summary><div>
          <label>Title<input data-task-title="${esc(task.id)}" value="${esc(task.title)}" maxlength="2000"></label><label>Due<input type="date" data-task-due="${esc(task.id)}" value="${esc(task.due || '')}"></label><label>Owner<input data-task-owner="${esc(task.id)}" value="${esc(task.owner || '')}"></label><label>Repeats<select data-task-recurrence="${esc(task.id)}">${['','weekly','monthly','yearly'].map(value => `<option value="${value}"${(task.recurrence || '') === value ? ' selected' : ''}>${value || 'Once'}</option>`).join('')}</select></label><label>Linked tab<select data-link="${esc(task.id)}" aria-label="Linked tab for ${esc(label)}"${state.busy ? ' disabled' : ''}>${tabOptions(doc, task.tab_id, !!task.parent_id)}</select></label>
          <details class="assistant-tasks-extra"><summary>More task properties</summary>${[['tldr','Summary','text'],['group','Group','text'],['scheduled','Planned','date'],['defer_until','Deferred until','date'],['waiting_on','Waiting on','text'],['follow_up_at','Follow up','date'],['reviewer','Reviewer','text'],['executor','Executor','text']].map(([field,label,type])=>`<label>${label}<input type="${type}" data-task-property="${field}" data-task-id="${esc(task.id)}" value="${esc(task[field] || '')}"></label>`).join('')}<label>Attributes<textarea data-task-attributes="${esc(task.id)}" aria-label="Task attributes">${esc(JSON.stringify(task.attributes || {},null,2))}</textarea></label></details>
          <button type="button" data-task-terminal="${esc(task.id)}">Link terminal…</button>
          <button type="button" data-add-child="${esc(task.id)}"${state.busy ? ' disabled' : ''}>+ Add subtask</button>
        ${task.recurrence ? `<button type="button" data-repeat-task="${esc(task.id)}"${taskStatus(task) !== 'done' ? ' disabled' : ''}>Create next occurrence</button>` : ''}<button type="button" data-delete-task="${esc(task.id)}">Delete task${allChildren.length ? ' and subtasks' : ''}</button></div></details>
      </div>${nested.length && expanded ? `<ul class="assistant-tasks-subtasks">${nested.map(child => taskRow(doc, child, scope, depth + 1)).join('')}</ul>` : ''}
    </li>`;
  }

  function orderedTabs(doc) {
    const result = [], seen = new Set(), ids = new Set(doc.tabs.map(tab => tab.id));
    const visit = tab => {
      if (seen.has(tab.id)) return;
      seen.add(tab.id); result.push(tab);
      doc.tabs.filter(child => child.parent_id === tab.id).sort((a,b) => (a.position || 0) - (b.position || 0)).forEach(visit);
    };
    doc.tabs.filter(tab => !ids.has(tab.parent_id)).sort((a,b) => (a.position || 0) - (b.position || 0)).forEach(visit);
    doc.tabs.forEach(visit);
    return result;
  }

  function isDescendant(doc, tab, parentId) {
    const seen = new Set();
    let current = tab;
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      if (current.parent_id === parentId) return true;
      current = doc.tabs.find(item => item.id === current.parent_id);
    }
    return false;
  }

  function taskGroup(doc, tab, visible) {
    const tasks = visible.filter(task => linkedTab(doc, task) === tab.id);
    if (!tasks.length) return '';
    const all = doc.tasks.filter(task => linkedTab(doc, task) === tab.id), p = progress(doc, all);
    const scope = new Set(tasks.map(task => task.id)), roots = tasks.filter(task => !scope.has(task.parent_id));
    const collapsed = get(doc.id + ':collapsed-groups', []);
    const expanded = tasks.some(task => highlightedBranch(doc,task)) || !collapsed.includes(tab.id);
    const parent = doc.tabs.find(item => item.id === tab.parent_id);
    return `<li class="assistant-tasks-task-group" data-task-group="${esc(tab.id)}"><div class="assistant-tasks-task-row assistant-tasks-group-row">
      <button type="button" class="assistant-tasks-disclosure" data-collapse-group="${esc(tab.id)}" aria-label="${expanded ? 'Hide' : 'Show'} tasks in ${esc(tab.title)}" aria-expanded="${expanded}">${expanded ? '▾' : '▸'}</button><span class="assistant-tasks-group-icon" aria-hidden="true">▤</span>
      <a class="assistant-tasks-task-label" href="#assistant-tasks-tab=${encodeURIComponent(tab.id)}" data-open-tab="${esc(tab.id)}"><span>${esc(tab.title)}</span><small>${p.done}/${p.total} done</small></a>${hasWip(doc, tab.id) ? '<span class="assistant-tasks-wip-badge">WIP</span>' : ''}${parent ? `<small class="assistant-tasks-group-parent">Subtab of ${esc(parent.title)}</small>` : ''}</div>
      ${expanded ? `<ul class="assistant-tasks-subtasks">${roots.map(task => taskRow(doc, task, scope)).join('')}</ul>` : ''}</li>`;
  }

  function taskPanel(doc) {
    const dashboard = state.tab === 'dashboard';
    const tabs = orderedTabs(doc).filter(tab => dashboard || state.showAll && isDescendant(doc, tab, state.tab));
    const includedTabs = new Set([state.tab, ...tabs.map(tab => tab.id)]);
    const associated = dashboard ? doc.tasks : doc.tasks.filter(task => includedTabs.has(linkedTab(doc, task)));
    let visible = associated.filter(task => highlightedBranch(doc,task) || get(doc.id + ':completed', true) || !['done','skipped','cancelled'].includes(taskStatus(task)));
    if (state.wipOnly) {
      const keep = new Set(visible.filter(task => taskStatus(task) === 'in_progress').map(task => task.id));
      for (const task of visible) {
        if (!keep.has(task.id)) continue;
        let parent = associated.find(item => item.id === task.parent_id);
        while (parent) { keep.add(parent.id); parent = associated.find(item => item.id === parent.parent_id); }
      }
      visible = visible.filter(task => keep.has(task.id));
    }
    // Tab nesting belongs to navigation. Each tab's own work is a sibling group.
    const direct = visible.filter(task => dashboard ? !linkedTab(doc, task) : linkedTab(doc, task) === state.tab);
    const directScope = new Set(direct.map(task => task.id));
    const rows = direct.filter(task => !directScope.has(task.parent_id)).map(task => taskRow(doc, task, directScope)).join('')
      + tabs.map(tab => taskGroup(doc, tab, visible)).join('');
    const hasChildWork = !dashboard && tabs.some(tab => associated.some(task => linkedTab(doc, task) === tab.id));
    const title = dashboard ? 'Todas las tareas' : hasChildWork ? 'Tareas y subtabs' : 'Tareas del tab';
    return `<section class="assistant-tasks-task-panel" aria-label="${title}">
      <header class="assistant-tasks-section-head"><h2>${title} <small>${state.showAll ? visible.length : visible.filter(task => !visible.some(parent => parent.id === task.parent_id && linkedTab(doc, parent) === linkedTab(doc, task))).length}</small></h2><div class="assistant-tasks-task-toggles">
        <button type="button" data-show-all aria-pressed="${state.showAll}">${state.showAll ? 'Mostrar menos' : 'Mostrar todo'}</button>
        <button type="button" data-wip-only aria-pressed="${state.wipOnly}">Solo WIP</button>
        <label><input type="checkbox" data-show-completed${get(doc.id + ':completed', true) ? ' checked' : ''}> Completadas</label>
        <button type="button" data-add-task${state.busy ? ' disabled' : ''}>+ Task</button></div></header>
      <ul class="assistant-tasks-task-list">${rows || `<li class="assistant-tasks-empty">${associated.length ? 'No tasks match these display options.' : 'No tasks here yet. Add a task whenever you need one.'}</li>`}</ul>
      ${state.form ? taskForm(doc) : ''}
    </section>`;
  }

  function taskForm(doc) {
    const parent = doc.tasks.find(task => task.id === state.form.parent);
    return `<form class="assistant-tasks-task-form"><div><label for="assistantTaskTitle">${parent ? 'Subtask of ' + esc(parent.title) : 'New task'}</label><input id="assistantTaskTitle" name="title" maxlength="2000" required placeholder="e.g. Call Alex" value="${esc(state.form.title || '')}"></div>
      <label>Priority<select name="priority">${priorityOptions(state.form.priority || 'P2')}</select></label>
      <label>Linked tab<select name="tab">${tabOptions(doc, state.form.tab ?? (parent || state.tab === 'dashboard' ? null : state.tab), !!parent)}</select></label>
      <button type="submit"${state.busy ? ' disabled' : ''}>Add ${parent ? 'subtask' : 'task'}</button><button type="button" data-cancel-form>Cancel</button></form>`;
  }

  function bind(host, doc) {
    host.querySelectorAll('[data-task-terminal]').forEach(button => button.onclick = () => window.LabDocumentTerminal?.choose(button.dataset.taskTerminal));
    window.LabDocumentTerminal?.decorate(host);
    host.querySelectorAll('[data-open-tab]').forEach(button => button.onclick = event => { event.preventDefault(); state.options.navigate(button.dataset.openTab); });
    host.querySelectorAll('[data-check]').forEach(input => {
      const task = doc.tasks.find(task => task.id === input.dataset.check);
      input.indeterminate = partial(doc, task);
      input.onchange = () => save({task_id:task.id, done:input.checked});
    });
    host.querySelectorAll('[data-status]').forEach(input => input.onchange = () => save({task_id:input.dataset.status, status:input.value}));
    host.querySelectorAll('[data-priority]').forEach(input => input.onchange = () => save({task_id:input.dataset.priority, priority:input.value}));
    host.querySelectorAll('[data-link]').forEach(input => input.onchange = () => save({task_id:input.dataset.link, tab_id:input.value || null}));
    host.querySelectorAll('[data-collapse]').forEach(button => button.onclick = () => {
      state.highlightId=null;
      const collapsed = new Set(get(doc.id + ':collapsed', [])), id = button.dataset.collapse;
      if (collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
      put(doc.id + ':collapsed', [...collapsed]); render();
    });
    host.querySelectorAll('[data-collapse-group]').forEach(button => button.onclick = () => {
      state.highlightId=null;
      const collapsed = new Set(get(doc.id + ':collapsed-groups', [])), id = button.dataset.collapseGroup;
      if (collapsed.has(id)) collapsed.delete(id); else collapsed.add(id);
      put(doc.id + ':collapsed-groups', [...collapsed]); render();
    });
    host.querySelector('[data-show-all]').onclick = () => {
      state.highlightId=null; state.showAll = !state.showAll;
      if (state.showAll) { put(doc.id + ':collapsed', []); put(doc.id + ':collapsed-groups', []); }
      render();
    };
    host.querySelector('[data-wip-only]').onclick = () => { state.wipOnly = !state.wipOnly; render(); };
    host.querySelector('[data-show-completed]').onchange = event => { put(doc.id + ':completed', event.target.checked); render(); };
    const openForm = parent => { state.form = {parent}; render(); document.getElementById('assistantTaskTitle')?.focus(); };
    for (const field of ['title','due','owner','recurrence']) host.querySelectorAll('[data-task-' + field + ']').forEach(input => input.onchange = () => save({task_id:input.getAttribute('data-task-' + field), [field]:input.value || null}));
    host.querySelectorAll('[data-task-property]').forEach(input=>input.onchange=()=>save({task_id:input.dataset.taskId,[input.dataset.taskProperty]:input.value || null}));
    host.querySelectorAll('[data-task-attributes]').forEach(input=>input.onchange=()=>{
      try { const attributes=JSON.parse(input.value); input.setCustomValidity(''); save({task_id:input.dataset.taskAttributes,attributes}); }
      catch (_) { input.setCustomValidity('Enter a JSON object'); input.reportValidity(); }
    });
    host.querySelectorAll('[data-repeat-task]').forEach(button => button.onclick = () => save({task_id:button.dataset.repeatTask, repeat:true}));
    host.querySelectorAll('[data-delete-task]').forEach(button => button.onclick = () => { if (window.confirm('Delete this task and its subtasks?')) save({task_id:button.dataset.deleteTask, delete:true}); });
    host.querySelector('[data-add-task]').onclick = () => openForm(null);
    host.querySelectorAll('[data-add-child]').forEach(button => button.onclick = () => openForm(button.dataset.addChild));
    const form = host.querySelector('.assistant-tasks-task-form');
    if (form) {
      form.oninput = () => Object.assign(state.form, {title:form.elements.title.value, priority:form.elements.priority.value, tab:form.elements.tab.value});
      form.onsubmit = event => {
        event.preventDefault();
        const title = form.elements.title.value.trim(); if (!title) return;
        save({title, priority:form.elements.priority.value, tab_id:form.elements.tab.value || null, parent_id:state.form.parent}, () => { state.form = null; });
      };
      host.querySelector('[data-cancel-form]').onclick = () => { state.form = null; render(); };
    }
  }

  function render() {
    const host = state.host;
    if (!host?.isConnected) return;
    const focused = host.contains(document.activeElement) ? document.activeElement : null;
    const attr = ['data-check','data-status','data-priority','data-link','data-show-all','data-wip-only'].find(name => focused?.hasAttribute(name));
    const value = attr ? focused.getAttribute(attr) : null;
    host.innerHTML = '<div class="assistant-tasks-shell assistant-tasks-task-component"><p class="assistant-tasks-error" role="alert" hidden></p>' + taskPanel(state.doc) + '<span class="assistant-tasks-save-status" role="status">' + (state.busy ? 'Saving…' : 'Saved to document') + '</span></div>';
    bind(host,state.doc);
    if (attr) [...host.querySelectorAll('[' + attr + ']')].find(input => input.getAttribute(attr) === value)?.focus({preventScroll:true});
  }
  async function save(change, onSuccess) {
    if (state.busy) return;
    const doc = state.doc, options = state.options;
    state.busy = true;
    const controls = [...state.host.querySelectorAll('input,select,button')];
    controls.forEach(input => { input.disabled = true; });
    state.host.querySelector('[role=status]').textContent = 'Saving…';
    const {task_id,delete:remove,repeat,...values} = change;
    try {
      const response = await fetch('/api/assistant/document-task' + (repeat ? '/repeat' : ''), {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({document_id:doc.id,expected:doc.revision,task_id,delete:!!remove,values})});
      const saved = await response.json();
      if (!response.ok) throw new Error(saved.detail || 'Could not save task');
      doc.tasks = saved.tasks; doc.revision = saved.revision;
      if (state.doc.id === doc.id) onSuccess?.();
      await options.changed(saved);
      state.busy = false;
      render();
    } catch (error) {
      state.busy = false;
      if (state.doc.id !== doc.id) return;
      render();
      const alert = state.host.querySelector('[role=alert]');
      if (alert) { alert.hidden = false; alert.textContent = error.message; }
      const status = state.host.querySelector('[role=status]');
      if (status) status.textContent = 'Not saved';
    }
  }
  function mount(host, options) {
    if (!document.getElementById('assistantTasksStyle')) {
      const link=document.createElement('link');link.id='assistantTasksStyle';link.rel='stylesheet';link.href='/static/css/assistant-tasks.css';document.head.appendChild(link);
    }
    const scope = options.database + ':' + options.root.path + ':' + options.tab;
    if (scope !== state.scope) { state.form=null;state.showAll=false;state.wipOnly=false;state.highlightId=null;state.scope=scope; }
    const tabs=[];
    const visit=row=>{tabs.push({id:row.id,title:row.title,parent_id:row.parent?.id,position:row.position});(row.children || []).forEach(visit)};
    visit(options.root.tree);
    const data=options.root.document_tasks;
    state.doc={id:data.document_id,tasks:data.tasks,revision:data.revision,tabs};
    state.host=host;state.options=options;state.tab=options.tab;
    render();
  }
  function reveal(taskId) {
    if (!state.doc?.tasks.some(task => task.id === taskId)) return;
    state.highlightId=taskId; state.wipOnly=false; render();
    const row=[...state.host.querySelectorAll('[data-task]')].find(row=>row.dataset.task===taskId);
    if (row) { row.scrollIntoView({block:'center'}); row.focus({preventScroll:true}); }
  }
  window.AssistantTasks={mount,reveal,busy:()=>state.busy,editing:()=>Boolean(state.form || state.host?.contains(document.activeElement) && document.activeElement.matches('input,textarea,select')),reset:()=>{state.scope=null},add:()=>{state.form={parent:null};render();document.getElementById('assistantTaskTitle')?.focus()}};
})();
