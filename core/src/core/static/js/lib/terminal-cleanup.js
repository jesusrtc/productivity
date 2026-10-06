/* Resources owns this view. Submit only reviewed, server-generated identities. */
(function () {
  'use strict';
  let container, list, tabs, notice, allButton, onBusy;
  let groups = [], busy = false, selected = 'all', generation = 0, controller;
  const identity = group => group.workspace_id === '__self__' ? 'home'
    : JSON.stringify([group.vault, group.workspace_id]);
  function workspaces() {
    const known = new Map();
    for (const group of [...(window.LabTerminalCleanupBridge?.workspaces?.() || []), ...groups])
      known.set(identity(group), {...group, sessions: group.sessions || []});
    const current = window.LabTerminalCleanupBridge?.scope() || {};
    if (current.workspace_id && !known.has(identity(current)))
      known.set(identity(current), {...current, name: current.workspace_id, sessions: []});
    return [...known.values()].sort((a, b) => a.name.localeCompare(b.name)
      || String(a.vault).localeCompare(String(b.vault)));
  }
  const sessions = () => (selected === 'all' ? groups : groups.filter(group => identity(group) === selected))
    .flatMap(group => group.sessions || []);
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action, className) {
    const node = element('button', text, className);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  function mount(host, busyChanged) {
    if (container) return;
    container = host;
    onBusy = busyChanged;
    const description = element('p', 'Cleanup can delete task terminals 24 hours after completion, with no activity or access in the last 24 hours. Other terminals qualify after 7 inactive days. Fixed main terminals, connected terminals, working or waiting agents, managed servers, and unsent document drafts are excluded. Saved agent conversations remain.');
    notice = element('div', '', 'resource-notice');
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    tabs = element('div', undefined, 'resource-workspace-tabs');
    tabs.setAttribute('role', 'tablist');
    tabs.setAttribute('aria-label', 'Cleanup workspaces');
    const panel = element('div');
    panel.id = 'resourceCleanupPanel';
    panel.setAttribute('role', 'tabpanel');
    const scroll = element('div', undefined, 'resource-table-scroll');
    const table = element('table');
    const head = element('thead');
    const headings = element('tr');
    for (const text of ['Terminal session', 'Workspace', 'Last activity / access', 'Actions']) headings.append(element('th', text));
    head.append(headings);
    list = element('tbody');
    table.append(head, list);
    scroll.append(table);
    allButton = button('Kill 0 inactive', () => kill(sessions()), 'resource-danger');
    const footer = element('footer', undefined, 'resource-cleanup-actions');
    footer.append(allButton);
    panel.append(scroll, footer);
    container.append(description, notice, tabs, panel);
    render();
  }
  function render() {
    if (!container) return;
    const catalog = [{name: 'All workspaces', id: 'all', sessions: groups.flatMap(g => g.sessions || [])},
      ...workspaces().map(group => ({...group, id: identity(group)}))];
    if (!catalog.some(group => group.id === selected)) selected = 'all';
    tabs.replaceChildren();
    catalog.forEach((group, index) => {
      const active = group.id === selected;
      const duplicate = catalog.some(other => other.id !== group.id && other.name === group.name);
      const tab = button(group.name + (duplicate ? ' · ' + group.vault : '') + ' · ' + group.sessions.length, () => {
        selected = group.id; render(); tabs.children[index]?.focus();
      });
      tab.id = 'resourceCleanupTab' + index;
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', String(active));
      tab.setAttribute('aria-controls', 'resourceCleanupPanel');
      tab.tabIndex = active ? 0 : -1;
      tab.disabled = busy;
      tab.title = group.vault ? group.name + ' · ' + group.vault : group.name;
      tab.addEventListener('keydown', event => {
        if (busy) return;
        const next = event.key === 'ArrowRight' ? (index + 1) % catalog.length
          : event.key === 'ArrowLeft' ? (index + catalog.length - 1) % catalog.length
          : event.key === 'Home' ? 0 : event.key === 'End' ? catalog.length - 1 : null;
        if (next !== null) {
          event.preventDefault(); selected = catalog[next].id; render(); tabs.children[next]?.focus();
        }
      });
      tabs.append(tab);
      if (active) container.querySelector('[role="tabpanel"]').setAttribute('aria-labelledby', tab.id);
    });
    list.replaceChildren();
    const candidates = sessions();
    for (const session of candidates) {
      const row = element('tr');
      const title = element('td');
      title.append(element('strong', session.label || session.logical_name || session.name), element('small', session.name));
      const scope = element('td', session.workspace_name || session.workspace_id);
      if (session.vault) scope.append(element('small', session.vault));
      const age = Math.floor((Date.now() / 1000 - session.last_used) / 86400);
      const activity = element('td', new Date(session.last_used * 1000).toLocaleString());
      activity.append(element('small', `Inactive ${age} days`));
      if(session.cleanup_reason==='completed_task')activity.append(element('small', 'Task completed '+new Date(session.task_completed_at*1000).toLocaleString()));
      const actions = element('td');
      const stop = button('Kill', () => kill([session]), 'resource-danger');
      stop.disabled = busy;
      actions.append(stop);
      row.append(title, scope, activity, actions);
      list.append(row);
    }
    if (!candidates.length) {
      const row = element('tr');
      const empty = element('td', busy ? 'Checking inactive sessions…'
        : 'No completed or inactive sessions eligible for cleanup' + (selected === 'all' ? '.' : ' in this workspace.'));
      empty.colSpan = 4; row.append(empty); list.append(row);
    }
    allButton.textContent = `Kill ${candidates.length} inactive`;
    allButton.disabled = busy || !candidates.length;
    list.setAttribute('aria-busy', String(busy));
  }
  function setBusy(value) { busy = value; onBusy?.(value); render(); }
  async function request(options = {}) {
    const response = await fetch('/api/term/cleanup', options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not inspect terminal sessions.');
    return data;
  }
  async function refresh(message = '') {
    if (busy) return;
    const current = ++generation;
    const active = new AbortController(); controller = active;
    const timeout = setTimeout(() => active.abort(), 15000);
    setBusy(true);
    notice.textContent = message || 'Checking terminal sessions across all workspaces…';
    try {
      const data = await request({signal: active.signal});
      if (current !== generation) return;
      groups = data.groups || [];
      notice.textContent = [message, ...(data.warnings || [])].filter(Boolean).join('\n');
    } catch (error) {
      if (current !== generation) return;
      groups = [];
      notice.textContent = [message, error.name === 'AbortError' ? 'Cleanup request timed out. Use Refresh to try again.' : error.message].filter(Boolean).join('\n');
    } finally {
      clearTimeout(timeout);
      if (current === generation) { controller = null; setBusy(false); }
    }
  }
  async function kill(targets) {
    if (busy || !targets.length) return;
    const captured = [...targets];
    const names = captured.map(s => `${s.workspace_name} (${s.vault}): ${s.label || s.logical_name}\n  ${s.name}`).join('\n');
    if (!window.confirm(`Kill these ${captured.length} inactive terminal sessions?\n\n${names}\n\nRunning processes in these sessions will stop and their tabs will stay closed. Saved agent conversations remain. Sessions used since this list was loaded will be skipped.`)) return;
    setBusy(true);
    notice.textContent = 'Rechecking inactivity and stopping confirmed sessions…';
    let message;
    try {
      const result = await request({method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({candidates: captured.map(s => s.id)})});
      message = `Stopped ${result.killed.length}. Skipped ${result.skipped.length}. Failed ${result.errors.length}.`;
      message += [...result.errors.map(e => `${e.name}: ${e.reason}`), ...(result.warnings || [])].map(s => '\n' + s).join('');
      if (result.skipped.length) message += '\nSkipped sessions changed, became active, or are no longer available.';
      await window.LabTerminalCleanupBridge?.stopped(result.killed);
    } catch (error) {
      message = error.message + ' Refresh the list before retrying.';
    } finally {
      groups = []; setBusy(false);
    }
    await refresh(message);
  }
  window.LabTerminalCleanup = {
    mount, refresh,
    show() { selected = 'all'; return refresh(); },
    cancel() { if (controller) { ++generation; controller.abort(); controller = null; setBusy(false); } },
    open() { return window.LabResources.open({cleanup: true}); },
  };
})();
