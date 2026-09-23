/* Sample only while this dialog is visible. Each action captures one identity. */
(function () {
  'use strict';
  let dialog, summary, list, scans, notice, timestamp, sort, pauseButton, refreshButton;
  let timer, controller, data, busy = false, returnFocus, generation = 0;
  const rows = new Map();
  const bytes = value => value >= 1073741824 ? (value / 1073741824).toFixed(1) + ' GB'
    : Math.round(value / 1048576) + ' MB';
  const percent = value => value == null ? 'Sampling…' : value.toFixed(1) + '%';

  function el(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function button(text, action, className) {
    const node = el('button', text, className);
    node.type = 'button';
    node.addEventListener('click', action);
    return node;
  }
  function cancelPoll() {
    clearTimeout(timer);
    controller?.abort();
    controller = null;
    generation++;
  }
  function schedule() {
    clearTimeout(timer);
    if (dialog?.open && !document.hidden && !busy) timer = setTimeout(refresh, 3000);
  }
  async function request(path, options = {}) {
    const response = await fetch('/api/resources' + path, options);
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Could not read host resources.');
    return result;
  }
  function ensureDialog() {
    if (dialog) return;
    dialog = el('dialog', undefined, 'lab-resources');
    dialog.setAttribute('aria-labelledby', 'labResourcesTitle');
    const header = el('header');
    const title = el('h2', 'Resources');
    title.id = 'labResourcesTitle';
    header.append(title, button('Close', () => dialog.close()));
    const description = el('p', 'Host usage, with processes limited to Lab, its terminals, workspace servers and Jupyter kernels.');
    summary = el('div', undefined, 'resource-summary');
    notice = el('div', '', 'resource-notice');
    notice.setAttribute('role', 'status');
    timestamp = el('span', 'Loading…');
    const toolbar = el('div', undefined, 'resource-toolbar');
    const label = el('label', 'Highest usage ');
    sort = el('select');
    for (const [value, text] of [['cpu_percent', 'CPU'], ['memory_bytes', 'Memory']]) {
      const option = el('option', text); option.value = value; sort.append(option);
    }
    sort.addEventListener('change', () => render(true));
    label.append(sort);
    refreshButton = button('Refresh', () => refresh());
    toolbar.append(label, timestamp, refreshButton);
    const scroll = el('div', undefined, 'resource-table-scroll');
    const table = el('table');
    const head = el('thead');
    const headings = el('tr');
    for (const text of ['Process', 'CPU', 'Memory', 'Actions']) headings.append(el('th', text));
    head.append(headings);
    list = el('tbody');
    table.append(head, list); scroll.append(table);
    const footnote = el('p', 'Process CPU: 100% = one core. Memory is resident RAM; shared pages can count in several processes. Stop targets only the selected process. Managed services may restart automatically.');
    const scanSection = el('section', undefined, 'resource-scans');
    const scanHeader = el('header');
    pauseButton = button('Pause file scans', toggleScans);
    scanHeader.append(el('h3', 'File scans'), pauseButton);
    scans = el('div');
    scanSection.append(scanHeader, el('p', 'Pause Files-view scans across workspaces until resumed or Lab restarts. Cached listings stay available. Other indexing continues; a scan waiting on disk may take longer to stop.'), scans);
    dialog.append(header, description, summary, toolbar, notice, scroll, footnote, scanSection);
    dialog.addEventListener('close', () => {
      cancelPoll();
      if (returnFocus?.isConnected) returnFocus.focus();
    });
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) cancelPoll();
      else if (dialog.open) refresh();
    });
    document.body.append(dialog);
  }
  function render(reorder = false) {
    refreshButton.disabled = busy;
    pauseButton.disabled = busy || !data;
    for (const row of rows.values()) row.querySelectorAll('button').forEach(b => { b.disabled = busy; });
    if (!data) return;
    const host = data.host;
    summary.replaceChildren();
    for (const [label, value, detail] of [
      ['Host CPU', percent(host.cpu_percent), host.cpu_count + ' logical cores'],
      ['Host memory', bytes(host.memory_used), 'of ' + bytes(host.memory_total) + ' · ' + percent(host.memory_percent)],
      ['Host swap', bytes(host.swap_used), data.processes.length + ' Lab-related processes'],
    ]) {
      const card = el('div');
      card.append(el('span', label), el('strong', value), el('small', detail));
      summary.append(card);
    }
    timestamp.textContent = 'Updated ' + new Date(data.sampled_at * 1000).toLocaleTimeString();
    const processes = [...data.processes].sort((a, b) => (b[sort.value] || 0) - (a[sort.value] || 0) || b.memory_bytes - a.memory_bytes || a.pid - b.pid);
    const alive = new Set();
    // Keep targets still under the pointer/keyboard while values update.
    const canReorder = reorder || (!list.matches(':hover') && !list.contains(document.activeElement));
    for (const process of processes) {
      const key = process.pid + ':' + process.created;
      alive.add(key);
      let row = rows.get(key);
      if (!row) {
        row = el('tr');
        for (let i = 0; i < 4; i++) row.append(el('td'));
        rows.set(key, row); list.append(row);
        const identity = row.children[0];
        identity.append(el('strong', process.name), el('small', process.kind + ' · PID ' + process.pid), el('small', process.scope));
        const actions = row.children[3];
        if (process.protected) {
          const protectedLabel = el('span', 'Protected'); protectedLabel.title = process.protected;
          actions.append(protectedLabel);
        } else {
          actions.append(button('Stop', () => stop(process, false)), button('Force kill', () => stop(process, true), 'resource-danger'));
        }
      }
      row.children[1].textContent = percent(process.cpu_percent);
      row.children[2].textContent = bytes(process.memory_bytes);
      row.querySelectorAll('button').forEach(b => { b.disabled = busy; });
      if (canReorder) list.append(row);
    }
    for (const [key, row] of rows) if (!alive.has(key)) { row.remove(); rows.delete(key); }
    pauseButton.textContent = data.files.paused ? 'Resume file scans' : 'Pause file scans';
    scans.replaceChildren();
    scans.append(el('p', data.files.paused ? 'Paused. New file scans will wait.' : data.files.scans.length ? data.files.scans.length + ' scans active or queued' : 'No file scans running.'));
    for (const scan of data.files.scans) {
      const line = el('div', undefined, 'resource-scan');
      line.append(el('strong', scan.root), el('small', `${scan.state} · ${scan.visited} entries · ${scan.elapsed_seconds.toFixed(1)}s`), el('small', scan.operation + ': ' + scan.path));
      scans.append(line);
    }
  }
  async function refresh() {
    if (busy || !dialog?.open || document.hidden || controller) return;
    const current = generation;
    const active = new AbortController(); controller = active;
    // A stalled request must not leave monitoring permanently stuck.
    const timeout = setTimeout(() => active.abort(), 10000);
    try {
      const result = await request('', {signal: active.signal});
      if (current !== generation || !dialog.open) return;
      data = result;
      notice.textContent = (result.warnings || []).join(' ');
      render();
    } catch (error) {
      if (current === generation && dialog.open) {
        notice.textContent = error.name === 'AbortError' ? 'Resource request timed out. Retrying…' : error.message;
        timestamp.textContent = 'Update failed · values may be stale';
      }
    } finally {
      clearTimeout(timeout);
      if (controller === active) controller = null;
      if (current === generation) schedule();
    }
  }
  async function mutate(path, body) {
    busy = true; cancelPoll(); render();
    try {
      await request(path, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      return true;
    } catch (error) {
      notice.textContent = error.message;
      return false;
    } finally {
      busy = false; render(); schedule();
    }
  }
  async function stop(process, force) {
    if (busy) return;
    if (!window.confirm(`${force ? 'Force kill' : 'Stop'} ${process.name} (PID ${process.pid})?\n\n${process.scope}\n\nThis can interrupt running work and lose unsaved state, including notebook variables. Only this process will receive the signal.`)) return;
    if (await mutate('/stop', {pid: process.pid, created: process.created, action: force ? 'kill' : 'stop'})) {
      await refresh();
      notice.textContent = `${force ? 'Kill' : 'Stop'} signal sent to PID ${process.pid}. A process that remains running may need Force kill.`;
    }
  }
  async function toggleScans() {
    if (busy || !data) return;
    if (await mutate('/scans', {paused: !data.files.paused})) await refresh();
  }
  window.LabResources = {
    async open() {
      ensureDialog();
      if (dialog.open) return;
      returnFocus = document.activeElement;
      dialog.showModal();
      dialog.querySelector('button').focus();
      await refresh();
    },
  };
})();
