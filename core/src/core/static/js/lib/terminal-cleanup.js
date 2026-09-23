/* Review a server-generated snapshot; never send a broad workspace kill. */
(function () {
  'use strict';
  let dialog, list, notice, refreshButton, allButton, closeButton, returnFocus;
  let groups = [], busy = false;

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

  function ensureDialog() {
    if (dialog) return;
    dialog = element('dialog', undefined, 'terminal-cleanup');
    dialog.setAttribute('aria-labelledby', 'terminalCleanupTitle');
    dialog.setAttribute('aria-describedby', 'terminalCleanupDescription');
    const header = element('header');
    const title = element('h2', 'Clean up inactive terminals');
    title.id = 'terminalCleanupTitle';
    closeButton = button('Close', () => dialog.close());
    header.append(title, closeButton);
    const description = element('p', 'Review sessions with no recorded activity or access for more than 7 days. Connected terminals, known working or waiting agents, and managed servers are excluded. Stopping a session closes its tab; saved agent conversations remain.');
    description.id = 'terminalCleanupDescription';
    notice = element('div', '', 'terminal-cleanup-notice');
    notice.setAttribute('role', 'status');
    notice.setAttribute('aria-live', 'polite');
    list = element('div', undefined, 'terminal-cleanup-list');
    const footer = element('footer');
    refreshButton = button('Refresh', () => refresh());
    allButton = button('Kill all inactive', () => kill(groups.flatMap(group => group.sessions)), 'terminal-cleanup-danger');
    footer.append(refreshButton, allButton);
    dialog.append(header, description, notice, list, footer);
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { if (returnFocus?.isConnected) returnFocus.focus(); });
    document.body.append(dialog);
  }

  function render() {
    list.replaceChildren();
    const current = window.LabTerminalCleanupBridge?.scope() || {};
    const isCurrent = group => group.workspace_id === current.workspace_id
      && (group.workspace_id === '__self__' || group.vault === current.vault);
    const sorted = [...groups].sort((a, b) => Number(isCurrent(b)) - Number(isCurrent(a)));
    for (const group of sorted) {
      const section = element('section');
      const header = element('div', undefined, 'terminal-cleanup-group-header');
      const label = group.name + (['__self__', '__assistant__'].includes(group.workspace_id) ? '' : ' · ' + group.vault);
      const heading = element('h3', label + (isCurrent(group) ? ' · current' : ''));
      const stop = button(`Kill ${group.sessions.length} inactive`, () => kill(group.sessions), 'terminal-cleanup-danger');
      stop.disabled = busy;
      header.append(heading, stop);
      const sessions = element('ul');
      for (const session of group.sessions) {
        const item = element('li');
        const title = element('strong', session.label || session.logical_name || session.name);
        const name = element('code', session.name);
        const age = Math.floor((Date.now() / 1000 - session.last_used) / 86400);
        const date = new Date(session.last_used * 1000).toLocaleString();
        const details = element('span', `Inactive ${age} days · Last activity/access ${date}`, 'terminal-cleanup-date');
        item.append(title, name, details);
        sessions.append(item);
      }
      section.append(header, sessions);
      list.append(section);
    }
    if (!groups.length && !busy) list.append(element('p', 'No inactive sessions older than 7 days.'));
    const count = groups.reduce((total, group) => total + group.sessions.length, 0);
    allButton.textContent = `Kill all ${count} inactive`;
    allButton.disabled = busy || !count;
    refreshButton.disabled = busy;
    closeButton.disabled = busy;
    list.setAttribute('aria-busy', String(busy));
  }

  async function request(options) {
    const response = await fetch('/api/term/cleanup', options);
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not inspect terminal sessions.');
    return data;
  }

  async function refresh(message = '') {
    if (busy) return;
    busy = true;
    notice.textContent = message || 'Checking terminal sessions across all workspaces…';
    render();
    try {
      const data = await request();
      groups = data.groups || [];
      notice.textContent = [message, ...(data.warnings || [])].filter(Boolean).join('\n');
    } catch (error) {
      groups = [];
      notice.textContent = [message, error.message].filter(Boolean).join('\n');
    } finally {
      busy = false;
      render();
    }
  }

  async function kill(sessions) {
    if (busy || !sessions.length) return;
    const captured = [...sessions];
    const names = captured.map(s => `${s.workspace_name}: ${s.label || s.logical_name}\n  ${s.name}`).join('\n');
    if (!window.confirm(`Kill these ${captured.length} inactive terminal sessions?\n\n${names}\n\nRunning processes in these sessions will stop and their tabs will stay closed. Saved agent conversations remain. Sessions used since this list was loaded will be skipped.`)) return;
    busy = true;
    notice.textContent = 'Rechecking inactivity and stopping confirmed sessions…';
    render();
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
      busy = false;
    }
    await refresh(message);
  }

  window.LabTerminalCleanup = {
    async open() {
      ensureDialog();
      if (dialog.open) return;
      returnFocus = document.activeElement;
      dialog.showModal();
      closeButton.focus();
      await refresh();
    },
  };
})();
