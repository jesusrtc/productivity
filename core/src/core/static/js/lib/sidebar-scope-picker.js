/* On-demand scope catalog. No polling, global workspace selection, or terminal
   creation. Captured ownership and an abort signal protect late responses. */
(function () {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  const icons = {
    worktree: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><circle cx="6" cy="4" r="2"/><circle cx="6" cy="16" r="2"/><circle cx="15" cy="5" r="2"/><path d="M6 6v8m9-7c0 5-9 3-9 7"/></svg>',
    folder: '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M2.5 6V4.5h5l2 2h8v9h-15V6Z"/></svg>',
  };
  let opened = null;

  function ranked(rows, usage, query = '') {
    const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    return rows.filter(row => words.every(word => {
      if (['branch', 'branches', 'worktree', 'worktrees'].includes(word)) return row.kind === 'worktree';
      if (word === 'main' || word === 'master') return row.kind !== 'worktree';
      return `${row.label || row.name} ${row.path} ${row.branch || ''}`.toLowerCase().includes(word);
    }))
      .sort((a, b) => (usage[b.path]?.count || 0) - (usage[a.path]?.count || 0)
        || (usage[b.path]?.lastUsed || 0) - (usage[a.path]?.lastUsed || 0)
        || String(a.label || a.name).localeCompare(String(b.label || b.name)) || a.path.localeCompare(b.path));
  }

  function close() {
    if (!opened) return;
    const old = opened; opened = null;
    old.abort.abort(); old.dialog.close(); old.dialog.remove();
    if (old.anchor.isConnected) old.anchor.focus();
  }

  function popup(anchor, className, html) {
    close();
    const dialog = document.createElement('dialog');
    dialog.className = className; dialog.innerHTML = html;
    const state = {dialog, anchor, abort: new AbortController()};
    opened = state;
    dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
    dialog.addEventListener('click', event => {if (event.target === dialog) {
      const rect = dialog.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) close();
    }});
    document.body.append(dialog); dialog.showModal();
    const box = anchor.getBoundingClientRect();
    dialog.style.left = Math.max(8, Math.min(box.left, innerWidth - dialog.offsetWidth - 8)) + 'px';
    dialog.style.top = Math.max(8, Math.min(box.bottom + 6, innerHeight - dialog.offsetHeight - 8)) + 'px';
    return state;
  }

  async function api(url, state, body) {
    const response = await fetch(url, {signal: state.abort.signal,
      ...(body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {})});
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Could not load folders. Try again.');
    return data;
  }

  async function open(anchor, bridge) {
    const state = popup(anchor, 'sidebar-scope-picker', `
      <header><strong>Add project or worktree</strong><button type="button" data-close aria-label="Close picker">×</button></header>
      <input type="search" data-search role="combobox" aria-label="Search projects, worktrees and folders" aria-controls="sidebarScopeResults" aria-expanded="true" aria-autocomplete="list" placeholder="Search projects, branches or folders…" autocomplete="off">
      <div class="sidebar-scope-results" id="sidebarScopeResults" role="listbox" aria-label="Projects, worktrees and parent folders"></div>
      <p class="sidebar-scope-search-hint">Worktrees: branch / worktree · Folders: main / master</p>
      <p data-status role="status">Loading folders…</p>
      <button type="button" class="sidebar-scope-custom" data-custom hidden>Add this folder</button>`);
    const {dialog} = state;
    const search = dialog.querySelector('[data-search]'), host = dialog.querySelector('[role=listbox]');
    const status = dialog.querySelector('[data-status]'), custom = dialog.querySelector('[data-custom]');
    let rows = [], matches = [], index = -1, busy = false;
    const current = () => opened === state && bridge.current();
    const warning = text => {status.textContent = text;};
    const highlight = () => {
      host.querySelectorAll('[role=option]').forEach((button, number) => button.setAttribute('aria-selected', String(number === index)));
      const selected = host.querySelector('[aria-selected=true]');
      if (selected) {search.setAttribute('aria-activedescendant', selected.id); selected.scrollIntoView({block:'nearest'});}
      else search.removeAttribute('aria-activedescendant');
    };
    async function select(row) {
      if (!current() || busy || row.available === false) return;
      busy = true; warning('Opening…');
      try {
        if (row.path !== bridge.root) await api('/api/projects/register', state, {projects:[{path:row.path, worktreeFolder:row.worktreeFolder || ''}]});
        if (!current()) return;
        await bridge.select(row);
        if (opened === state) close();
      } catch (error) {if (current() && error.name !== 'AbortError') warning(error.message);}
      finally {busy = false;}
    }
    function render() {
      matches = ranked(rows, bridge.usage(), search.value);
      index = matches.findIndex(row => row.available !== false);
      host.innerHTML = matches.map((row, number) => {
        const worktree = row.kind === 'worktree';
        const savedColor = bridge.color?.(row) || row.color;
        const color = /^#[\da-f]{6}$/i.test(savedColor || '') ? savedColor : worktree ? '#d2a8ff' : '#8b949e';
        return `<button type="button" role="option" id="sidebarScopeOption${number}" data-scope-option="${esc(row.path)}" data-scope-kind="${esc(row.kind || 'folder')}" style="--sidebar-scope-color:${color}" aria-selected="false" ${row.available === false ? 'disabled' : ''}><span class="sidebar-scope-kind${worktree ? ' worktree' : ''}" aria-hidden="true">${icons[worktree ? 'worktree' : 'folder']}</span><span><strong>${esc(row.label || row.name)}</strong><small>${esc(row.path)}</small></span><small class="sidebar-scope-type${worktree ? ' worktree' : ''}">${worktree ? 'Worktree' : row.kind === 'parent' ? 'Parent folder' : 'Folder'}</small></button>`;
      }).join('');
      host.querySelectorAll('[data-scope-option]').forEach(button => button.onclick = () => select(matches.find(row => row.path === button.dataset.scopeOption)));
      highlight();
      const path = search.value.trim();
      custom.hidden = !path.startsWith('/') && !path.startsWith('~/');
      custom.textContent = 'Add folder ' + path;
      warning(matches.length ? 'Most used first' : 'No matching folders. Enter a full path to add another folder.');
    }
    dialog.querySelector('[data-close]').onclick = close;
    search.oninput = render;
    search.onkeydown = event => {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const available = matches.map((row, number) => row.available === false ? -1 : number).filter(number => number >= 0);
        if (!available.length) return;
        const next = available.indexOf(index) + (event.key === 'ArrowDown' ? 1 : -1);
        index = available[(next + available.length) % available.length]; highlight();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        if (index >= 0) void select(matches[index]);
        else if (!custom.hidden) custom.click();
      }
    };
    custom.onclick = async () => {
      if (!current() || busy) return;
      busy = true; warning('Checking folder…');
      try {
        const registered = await api('/api/projects/register', state, {base:bridge.root, projects:[{path:search.value.trim()}]});
        const path = registered.projects[0].path;
        const data = await api('/api/projects/scopes', state);
        if (!current()) return;
        const row = data.scopes.find(row => row.path === path) || {path, label:path.split('/').pop(), kind:'folder'};
        await bridge.select(row);
        if (opened === state) close();
      } catch (error) {if (current() && error.name !== 'AbortError') warning(error.message);}
      finally {busy = false;}
    };
    search.focus();
    // Existing workspace folders remain useful while the live catalog loads.
    const merge = catalog => {
      const all = new Map([[bridge.root, {path:bridge.root, label:'Root', kind:'folder'}]]);
      for (const row of bridge.folders()) all.set(row.path, row);
      for (const row of catalog) all.set(row.path, {...all.get(row.path), ...row});
      rows = [...all.values()]; render();
    };
    merge([]); warning('Loading folders…');
    try {
      const data = await api('/api/projects/scopes', state);
      if (!current()) {if (opened === state) close(); return;}
      merge(data.scopes || []);
      if (data.warning) warning(data.warning);
    } catch (error) {if (current() && error.name !== 'AbortError') warning(error.message);}
  }

  function colors(anchor, palette, select) {
    const state = popup(anchor, 'sidebar-scope-palette', '<strong>Scope color</strong><div>' + palette.map(color => `<button type="button" data-color="${color}" style="background:${color}" aria-label="Use color ${color}"></button>`).join('') + '</div>');
    state.dialog.querySelectorAll('[data-color]').forEach(button => button.onclick = () => {select(button.dataset.color); close();});
  }
  window.LabSidebarScopes = {open, colors, close, ranked};
})();
