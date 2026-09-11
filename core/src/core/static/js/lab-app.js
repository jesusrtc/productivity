  let currentRepo = null;
  const LAB_USER = window.LAB_USER || {};
  const LAB_IS_ADMIN = window.LAB_IS_ADMIN === true;

  async function labLogout() {
    try { await fetch('/api/auth/logout', {method: 'POST'}); } catch {}
    location.replace('/login');
  }
  window.labLogout = labLogout;

  // Framework self-update and verified process restart.
  let _labUpdateRestartBusy = false;

  function _labUpdateWait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  async function _labWaitForNewBoot(previousBootId, timeoutMs = 90000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      await _labUpdateWait(1000);
      try {
        const response = await fetch('/api/git/runtime', {cache: 'no-store'});
        if (!response.ok) continue;
        const runtime = await response.json();
        if (runtime.boot_id && runtime.boot_id !== previousBootId) return runtime;
      } catch {
        // The connection dropping is the expected middle of a restart.
      }
    }
    throw new Error('Lab did not come back within 90 seconds');
  }

  async function labUpdateAndRestart() {
    if (_labUpdateRestartBusy) return;
    if (!confirm('Pull origin/main with rebase/autostash and restart Lab now?')) return;
    const button = document.getElementById('updateRestartBtn');
    const icon = button && button.querySelector('.framework-update-icon');
    _labUpdateRestartBusy = true;
    if (button) {
      button.disabled = true;
      button.classList.add('is-busy');
      button.title = 'Pulling origin/main…';
    }
    try {
      const response = await fetch('/api/git/update-restart', {method: 'POST'});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || 'update failed');
      if (button) button.title = 'Restarting Lab…';
      await _labWaitForNewBoot(result.boot_id);
      if (button) {
        button.classList.remove('is-busy');
        button.title = `Updated to ${result.revision}; reloading`;
      }
      if (icon) icon.textContent = '✓';
      explorerToast(`Lab updated to ${result.revision}. Reloading…`);
      setTimeout(() => location.reload(), 500);
    } catch (error) {
      _labUpdateRestartBusy = false;
      if (button) {
        button.disabled = false;
        button.classList.remove('is-busy');
        button.title = 'Pull origin/main, then restart Lab';
      }
      if (icon) icon.textContent = '↻';
      explorerToast(String(error && error.message || error), true);
    }
  }
  window.labUpdateAndRestart = labUpdateAndRestart;

  let currentDiffTab = 'uncommitted';
  let viewMode = 'split';
  let diffCache = { uncommitted: null, branch: null };

  let commitsList = [];
  let workspacesList = [];
  let currentWorkspace = null;
  let currentRepoInWorkspace = null;
  let vaultCatalog = [];
  let _vaultCatalogInFlight = null;

  const urlRepo = new URLSearchParams(location.search).get('repo');

  // Global catalog: every registered vault and its workspaces.  It is the
  // key to keeping tabs from several vaults alive at once; selecting a
  // vault no longer mutates the backend's process-wide root.
  let _reposInFlight = null;
  function fetchVaultCatalog() {
    if (_vaultCatalogInFlight) return _vaultCatalogInFlight;
    const p = fetch('/api/vaults/workspaces')
      .then(r => r.ok ? r.json() : {vaults: []})
      .then(data => {
        vaultCatalog = Array.isArray(data.vaults) ? data.vaults : [];
        currentVaultId = data.active || currentVaultId;
        return data;
      })
      .catch(() => ({vaults: vaultCatalog || []}));
    _vaultCatalogInFlight = p;
    p.finally(() => { if (_vaultCatalogInFlight === p) _vaultCatalogInFlight = null; });
    return p;
  }

  function fetchRepos() {
    if (_reposInFlight) return _reposInFlight;
    const p = fetchVaultCatalog()
      .then(data => (data.vaults || []).flatMap(vault => vault.workspace_rows || []))
      .catch(() => []);
    _reposInFlight = p;
    p.finally(() => { if (_reposInFlight === p) _reposInFlight = null; });
    return p;
  }

  // Workspace ids remain stable for paths, terminal sessions, and API calls.
  // Only this helper should decide what human-facing label to render.
  function _workspaceDisplayName(workspace) {
    // The detail request may be newer than an in-flight catalog poll. Keep
    // the active tab aligned with the Overview heading in that short window.
    const activeDisplayName = currentWorkspace && workspace
      && currentWorkspace.path === workspace.path && currentWorkspace.display_name;
    return String(activeDisplayName || (workspace && (workspace.display_name || workspace.name)) || 'Workspace');
  }

  let currentVaultId = null;
  async function vaultRefresh() {
    try {
      const data = await fetchVaultCatalog();
      currentVaultId = data.active || currentVaultId;
      if (typeof renderRepoTabs === 'function' && currentWorkspace) renderRepoTabs();
    } catch {}
  }

  function afterFirstPaint(fn) {
    const run = () => {
      try {
        const ret = fn && fn();
        if (ret && typeof ret.catch === 'function') ret.catch(() => {});
      } catch {}
    };
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => setTimeout(run, 0));
    } else {
      setTimeout(run, 0);
    }
  }

  function afterPageQuiet(fn, delayMs = 750) {
    const run = () => {
      try {
        const ret = fn && fn();
        if (ret && typeof ret.catch === 'function') ret.catch(() => {});
      } catch {}
    };
    if (document.readyState === 'complete' && performance.now() > 2000) {
      run();
      return;
    }
    const schedule = () => setTimeout(() => {
      run();
    }, delayMs);
    if (document.readyState === 'complete') schedule();
    else window.addEventListener('load', schedule, { once: true });
  }

  function afterColdPageQuiet(fn, delayMs = 750) {
    if (document.readyState !== 'complete' || performance.now() < 2000) {
      afterPageQuiet(fn, delayMs);
      return;
    }
    const ret = fn && fn();
    if (ret && typeof ret.catch === 'function') ret.catch(() => {});
  }

  const _assetPromises = new Map();
  function loadScriptOnce(src) {
    if (_assetPromises.has(src)) return _assetPromises.get(src);
    const p = new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${src}"]`);
      if (existing) {
        if (existing.dataset.loaded === '1') return resolve();
        existing.addEventListener('load', () => resolve(), { once: true });
        existing.addEventListener('error', () => reject(new Error('failed to load ' + src)), { once: true });
        return;
      }
      const s = document.createElement('script');
      s.src = src;
      s.async = false;
      s.onload = () => { s.dataset.loaded = '1'; resolve(); };
      s.onerror = () => reject(new Error('failed to load ' + src));
      document.head.appendChild(s);
    });
    _assetPromises.set(src, p);
    return p;
  }

  function loadStyleOnce(href) {
    if (_assetPromises.has(href)) return _assetPromises.get(href);
    const p = new Promise((resolve, reject) => {
      const existing = document.querySelector(`link[rel="stylesheet"][href="${href}"]`);
      if (existing) return resolve();
      const l = document.createElement('link');
      l.rel = 'stylesheet';
      l.href = href;
      l.onload = () => resolve();
      l.onerror = () => reject(new Error('failed to load ' + href));
      document.head.appendChild(l);
    });
    _assetPromises.set(href, p);
    return p;
  }

  function ensureTerminalLibs() {
    loadStyleOnce('/static/vendor/xterm@5.3.0/xterm.min.css').catch(() => {});
    return loadScriptOnce('/static/vendor/xterm@5.3.0/xterm.min.js')
      .then(() => loadScriptOnce('/static/vendor/xterm-addon-fit@0.8.0/xterm-addon-fit.min.js'))
      .then(() => loadScriptOnce('/static/vendor/xterm-addon-webgl@0.16.0/xterm-addon-webgl.min.js'));
  }

  function ensurePlotly() {
    if (window.Plotly) return Promise.resolve();
    return loadScriptOnce('/static/vendor/plotly@2.27.0/plotly.min.js');
  }

  function ensureMarked() {
    return Promise.all([
      window.marked ? Promise.resolve() : loadScriptOnce('/static/vendor/marked@12.0.1/marked.min.js'),
      window.DOMPurify ? Promise.resolve() : loadScriptOnce('/static/vendor/dompurify@3.4.15/purify.min.js'),
      ensureHighlight().catch(() => {}),
    ]);
  }

  let _mermaidReady;
  let _mermaidId = 0;
  async function renderMermaidBlocks(root) {
    const blocks = Array.from(root.querySelectorAll('pre > code.language-mermaid'))
      .filter(code => !code.dataset.mermaidState);
    if (!blocks.length) return;
    blocks.forEach(code => { code.dataset.mermaidState = 'pending'; });
    try {
      if (!_mermaidReady) {
        _mermaidReady = loadScriptOnce('/static/vendor/mermaid@11.17.2/mermaid.lab.min.js')
          .then(() => window.mermaid.initialize({
            startOnLoad: false, theme: 'dark', securityLevel: 'strict',
            suppressErrorRendering: true,
          }));
      }
      await _mermaidReady;
    } catch (error) {
      blocks.forEach(code => { delete code.dataset.mermaidState; });
      console.warn('Could not load Mermaid', error);
      return;
    }
    for (const code of blocks) {
      if (!code.isConnected) continue;
      try {
        const { svg } = await window.mermaid.render(`lab-mermaid-${++_mermaidId}`, code.textContent);
        if (!code.isConnected) continue;
        const diagram = document.createElement('div');
        diagram.className = 'lab-mermaid';
        diagram.style.cssText = 'overflow:auto;margin:16px 0;text-align:center';
        diagram.innerHTML = svg;
        if (code.parentElement.parentElement.classList.contains('markdown-code-block')) {
          // Keep the original source available to the code-copy button.
          code.parentElement.hidden = true;
          code.parentElement.after(diagram);
        } else {
          code.parentElement.replaceWith(diagram);
        }
      } catch (error) {
        code.dataset.mermaidState = 'error';
        const notice = document.createElement('div');
        notice.style.cssText = 'color:var(--text-secondary);font-size:13px';
        notice.textContent = 'Could not render Mermaid diagram. Check the syntax below.';
        code.parentElement.before(notice);
        console.warn('Could not render Mermaid diagram', error);
      }
    }
  }

  function ensureHighlight() {
    if (window.hljs && window.hljs.getLanguage && window.hljs.getLanguage('scala')) {
      return Promise.resolve();
    }
    loadStyleOnce('/static/vendor/highlightjs@11.9.0/github-dark.min.css').catch(() => {});
    return loadScriptOnce('/static/vendor/highlightjs@11.9.0/highlight.min.js')
      .then(() => loadScriptOnce('/static/vendor/highlightjs@11.9.0/languages/scala.min.js'))
      .then(() => loadScriptOnce('/static/vendor/highlightjs@11.9.0/languages/groovy.min.js'))
      .then(() => loadScriptOnce('/static/vendor/highlightjs@11.9.0/languages/protobuf.min.js'));
  }

  async function loadRepos() {
    try {
      workspacesList = await fetchRepos();
      const sel = document.getElementById('repoSelect');
      sel.innerHTML = '<option value="">Select workspace...</option>';
      workspacesList.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.path;
        opt.textContent = (p.is_workspace ? '\u{1F4E6} ' : '') + _workspaceDisplayName(p);
        if (p.is_workspace) opt.style.color = '#58a6ff';
        if (p.name === (currentWorkspace && currentWorkspace.name)) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (err) {}
  }

  async function selectRepo(workspaceKey) {
    if (!workspaceKey) return;
    currentWorkspace = workspacesList.find(p => p.path === workspaceKey)
      || workspacesList.find(p => p.name === workspaceKey);
    if (!currentWorkspace) return;
    _sidebarActivateFileConfig();

    _contextSubView = 'overview';

    if (currentWorkspace.is_workspace) workspaceTabsSetOpen(currentWorkspace.path, true);

    document.title = _workspaceDisplayName(currentWorkspace);
    // replaceState (not pushState): the caller (goToWorkspace / popstate
    // handler / initial-load dispatch) has already settled the URL. A
    // pushState here would create a duplicate history entry, breaking
    // the back button. replaceState normalizes (e.g., ?repo= → ?workspace=)
    // without adding to history.
    const url = new URL(window.location);
    url.searchParams.set('workspace', currentWorkspace.path);
    url.searchParams.delete('repo');
    history.replaceState(null, '', url);

    renderRepoTabs();

    if (currentWorkspace.is_workspace) {
      // Restore the last-viewed doc for this workspace (if any). Switching
      // between workspaces should land the user where they left off, not
      // force them through Dashboard every time.
      currentRepo = null;
      currentRepoInWorkspace = null;
      document.getElementById('diffTabs').style.display = 'none';
      document.body.classList.remove('has-diff-tabs');
      // A real workspace is active — reveal the attrs bar.
      document.body.classList.add('workspace-active');
      const hydrateWorkspaceChrome = () => {
        refreshAttrsBar();
        // The workspace shell (or a remembered document) is already painted.
        // Sidebar/dashboard hydration must never replace it with a dashboard
        // loading spinner; showWorkspaceInfo's final race guard will paint the
        // dashboard only when no document owns the content area.
        showWorkspaceInfo({keepShell: true});
      };
      // Decide synchronously whether a doc or the dashboard will paint
      // the content area. On cold full-page loads, keep the server-rendered
      // shell isolated from sidebar/dashboard fetches; warm in-app switches
      // hydrate immediately.
      // Set `_workspaceDocPath` up-front so showWorkspaceInfo's dashboard-paint
      // race guard knows a doc is on its way and doesn't stomp the doc
      // render. If no remembered doc, _workspaceDocPath is null and
      // showWorkspaceInfo paints the dashboard as usual.
      const remembered = getLastWorkspaceDoc(currentWorkspace.path);
      _workspaceDocPath = remembered || null;
      if (!remembered) paintWorkspaceShell();
      afterColdPageQuiet(hydrateWorkspaceChrome);
      if (remembered) openWorkspaceDoc(remembered);
      // Workspace-scoped terminal panel: auto-open + attach latest session (if any).
      // Skip under ?ui_check=1 so headless validator reaches network idle.
      if (!(new URLSearchParams(location.search).get('ui_check') === '1')) {
        const terminalWorkspaceId = currentWorkspace.name;
        afterPageQuiet(() => {
          if (typeof _termIsScopeActive === 'function' && !_termIsScopeActive(terminalWorkspaceId)) return;
          termOpenForWorkspace(terminalWorkspaceId);
        });
      }
      // Re-render workspace tabs so the active highlight tracks the selection.
      if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
    } else {
      // Single repo — go straight to diff. Not a real workspace, so hide
      // the attrs bar (matches the else-branch below the workspace init).
      document.body.classList.remove('workspace-active');
      currentRepoInWorkspace = currentWorkspace.repos[0];
      currentRepo = currentRepoInWorkspace.path;
      document.getElementById('diffTabs').style.display = 'flex';
      document.body.classList.add('has-diff-tabs');
      diffCache = { uncommitted: null, branch: null };
      loadCommitTabs();
      loadDiff();
    }
  }

  async function loadDiff() {
    if (!currentRepo) return;
    const repoAtStart = currentRepo;
    const tabAtStart = currentDiffTab;
    document.getElementById('content').innerHTML = '<div class="loading">Loading diff...</div>';

    try {
      const res = await fetch(`/api/diff?repo=${encodeURIComponent(currentRepo)}&type=${currentDiffTab}`);
      const data = await res.json();
      // Race guard: the user may have clicked Overview (currentRepo=null) or
      // swapped to a different repo / diff tab while the fetch was in flight.
      // Don't stomp whatever they're looking at now.
      if (!currentRepo || currentRepo !== repoAtStart || currentDiffTab !== tabAtStart) return;
      diffCache[currentDiffTab] = data;
      if (data.branch) {
        const repoName = currentRepoInWorkspace ? currentRepoInWorkspace.name : '';
        document.getElementById('branchLabel').textContent = repoName ? `${repoName} @ ${data.branch}` : data.branch;
      }
      renderDiff(data);

      const otherTab = currentDiffTab === 'uncommitted' ? 'branch' : 'uncommitted';
      if (!diffCache[otherTab]) {
        fetch(`/api/diff?repo=${encodeURIComponent(currentRepo)}&type=${otherTab}`)
          .then(r => r.json())
          .then(d => {
            diffCache[otherTab] = d;
            const el = document.getElementById(`count${cap(otherTab)}`);
            if (el) el.textContent = d.files.length;
            if (d.base_branch) {
              const lbl = document.getElementById('branchTabLabel');
              if (lbl) lbl.textContent = `vs ${d.base_branch}`;
            }
          });
      }
    } catch (err) {
      if (!currentRepo || currentRepo !== repoAtStart) return;
      document.getElementById('content').innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
    }
  }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  async function loadCommitTabs() {
    if (!currentRepo) return;
    try {
      const res = await fetch(`/api/commits?repo=${encodeURIComponent(currentRepo)}&count=20`);
      commitsList = await res.json();
      renderCommitTabs();
    } catch (err) { commitsList = []; }
  }

  function commitLabel(c) {
    const msg = c.message.length > 30 ? c.message.substring(0, 30) + '...' : c.message;
    return msg;
  }

  function renderCommitTabs() {
    const container = document.getElementById('commitTabs');
    if (!commitsList.length) { container.innerHTML = ''; return; }
    const visible = commitsList.slice(0, 4);
    const rest = commitsList.slice(4);

    let html = visible.map(c => {
      const active = currentDiffTab === `commit:${c.sha}` ? ' active' : '';
      return `<button class="diff-tab commit-tab${active}" onclick="switchDiffTab('commit:${c.sha}')" title="${esc(c.message)}\n${c.author} · ${c.date}">${commitLabel(c)}</button>`;
    }).join('');

    if (rest.length) {
      const activeInRest = rest.some(c => currentDiffTab === `commit:${c.sha}`);
      html += `<select class="commit-dropdown${activeInRest ? ' active' : ''}" onchange="if(this.value) switchDiffTab('commit:'+this.value); this.blur();">
        <option value="">+${rest.length} more commits...</option>
        ${rest.map(c => `<option value="${c.sha}" ${currentDiffTab === 'commit:'+c.sha ? 'selected' : ''} title="${esc(c.message)}">${commitLabel(c)}</option>`).join('')}
      </select>`;
    }

    container.innerHTML = html;
  }

  async function loadCommitDiff(sha) {
    if (!currentRepo) return;
    document.getElementById('content').innerHTML = '<div class="loading">Loading commit diff...</div>';
    try {
      const res = await fetch(`/api/commit-diff?repo=${encodeURIComponent(currentRepo)}&sha=${sha}`);
      const data = await res.json();
      diffCache[`commit:${sha}`] = data;
      renderDiff(data);
    } catch (err) {
      document.getElementById('content').innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
    }
  }

  function renderSidebar(files) {
    const sb = document.getElementById('sidebar');
    const fileItems = files.map((f, i) => {
      const fn = f.filename.replace(/'/g, "\\'");
      return `<a class="sidebar-file" onclick="scrollToFile(${i})" title="${f.filename}">
        <span class="sidebar-badge ${f.status}"></span>
        <span class="sidebar-fname">${f.filename.split('/').pop()}</span>
        <span class="sidebar-actions">
          <button title="View" onclick="event.stopPropagation(); openViewModal('${fn}')">&#128065;</button>
        </span>
      </a>`;
    }).join('');
    sb.innerHTML = `<div class="sidebar-title">Files</div>
      ${fileItems}
      <div class="sidebar-create"><button onclick="openCreateModal()">+ New File</button></div>`;
  }

  function scrollToFile(idx) {
    const el = document.getElementById(`file-${idx}`);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    document.querySelectorAll('.sidebar-file').forEach((f, i) => f.classList.toggle('active', i === idx));
  }

  function renderDiff(data) {
    const content = document.getElementById('content');
    const countEl = document.getElementById(`count${cap(currentDiffTab)}`);
    if (countEl) countEl.textContent = data.files.length;
    if (data.base_branch) {
      const lbl = document.getElementById('branchTabLabel');
      if (lbl) lbl.textContent = `vs ${data.base_branch}`;
    }

    renderSidebar(data.files);

    if (data.files.length === 0) {
      content.innerHTML = '<div class="empty-diff">No changes</div>';
      return;
    }

    const totalAdds = data.files.reduce((s, f) => s + (f.additions || 0), 0);
    const totalDels = data.files.reduce((s, f) => s + (f.deletions || 0), 0);
    const summaryRows = data.files.map(f =>
      `<div class="file-summary-row">
        <span class="fname">${esc(f.filename)}</span>
        <span class="stat">${(f.additions||0)+(f.deletions||0)} <span class="adds">${'+'.repeat(Math.min(f.additions||0,20))}</span><span class="dels">${'-'.repeat(Math.min(f.deletions||0,20))}</span></span>
      </div>`
    ).join('');

    const summaryHtml = `<div class="file-summary">
      <div class="file-summary-header" onclick="document.getElementById('summaryBody').classList.toggle('collapsed')">
        ${data.files.length} files changed, <span class="adds">+${totalAdds}</span>, <span class="dels">-${totalDels}</span>
      </div>
      <div class="file-summary-body" id="summaryBody">${summaryRows}</div>
    </div>`;

    const diffsHtml = data.files.map((file, i) => {
      let bodyContent;
      if (isNotebook(file.filename)) {
        const fn = file.filename.replace(/'/g, "\\'");
        const dt = currentDiffTab === 'workspace' ? 'uncommitted' : currentDiffTab;
        bodyContent = `<div style="padding:12px;text-align:center">
          <button onclick="renderNotebookDiff('${fn}','${dt}')" style="background:#388bfd26;color:#58a6ff;border:1px solid #388bfd;padding:6px 16px;border-radius:6px;cursor:pointer;font-size:13px">View Notebook Diff</button>
        </div>`;
      } else {
        bodyContent = viewMode === 'unified' ? renderUnified(file) : renderSplit(file);
      }
      return `<div class="file-diff" id="file-${i}">
        <div class="file-header" onclick="toggleFile(${i})">
          <span class="badge badge-${file.status}">${file.status}</span>
          <span class="filename">${esc(file.filename)}</span>
          <span class="file-stats"><span class="adds">+${file.additions||0}</span> <span class="dels">-${file.deletions||0}</span></span>
          <button style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer;margin-left:4px" onclick="event.stopPropagation(); openViewModal('${file.filename.replace(/'/g, "\\'")}')">View</button>
          <span class="chevron" id="chev-${i}">&#9660;</span>
        </div>
        <div class="file-body" id="fb-${i}">${bodyContent}</div>
      </div>`;
    }).join('');

    content.innerHTML = summaryHtml + diffsHtml;

    // Code comments behave exactly like doc comments: anchored to the
    // SELECTED TEXT (not a line number). We wire a context-menu handler
    // so right-clicking a text selection wraps it and opens a composer,
    // and we highlight every saved comment's text in the diff so the
    // note appears where the code still lives.
    wireDiffCodeCommentSelection(content);
    renderDiffComments(content);
  }

  // Render a saved .diff/.patch document with the same tables used by the
  // live Git changes view. The toggle is local to the document so opening a
  // patch never changes the user's preferred mode for repository diffs.
  function renderStoredDiffDocument(filepath, data, container) {
    const files = Array.isArray(data.files) ? data.files : [];
    if (!files.length) {
      const raw = data.raw || '';
      container.innerHTML = `<div class="stored-diff-document">
        <div class="stored-diff-toolbar"><span class="stored-diff-path">${esc(filepath)}</span><span class="stored-diff-totals">No parseable file changes</span></div>
        <pre style="padding:16px;border:1px solid var(--border);border-radius:6px;background:var(--bg-secondary);overflow:auto;white-space:pre-wrap">${esc(raw)}</pre>
      </div>`;
      return;
    }
    let mode = localStorage.getItem('labStoredDiffView') === 'split' ? 'split' : 'unified';
    const totalAdds = files.reduce((sum, file) => sum + (file.additions || 0), 0);
    const totalDels = files.reduce((sum, file) => sum + (file.deletions || 0), 0);
    container.innerHTML = `<div class="stored-diff-document">
      <div class="stored-diff-toolbar">
        <span class="stored-diff-path" title="${escAttr(filepath)}">${esc(filepath)}</span>
        <span class="stored-diff-totals">${files.length} file${files.length === 1 ? '' : 's'} · <span style="color:var(--green)">+${totalAdds}</span> <span style="color:var(--red)">−${totalDels}</span></span>
        <span class="stored-diff-toggle" role="group" aria-label="Diff layout">
          <button type="button" data-stored-mode="unified">Unified</button>
          <button type="button" data-stored-mode="split">Split</button>
        </span>
      </div>
      <div class="stored-diff-body"></div>
    </div>`;
    const paint = () => {
      const body = container.querySelector('.stored-diff-body');
      if (!body) return;
      container.querySelectorAll('[data-stored-mode]').forEach(button => {
        button.classList.toggle('active', button.getAttribute('data-stored-mode') === mode);
      });
      body.innerHTML = files.map(file => `
        <div class="file-diff">
          <div class="file-header">
            <span class="badge badge-${file.status}">${esc(file.status)}</span>
            <span class="filename">${esc(file.filename)}</span>
            <span class="file-stats"><span class="adds">+${file.additions || 0}</span> <span class="dels">-${file.deletions || 0}</span></span>
          </div>
          <div class="file-body">${mode === 'split' ? renderSplit(file) : renderUnified(file)}</div>
        </div>`).join('');
    };
    container.querySelectorAll('[data-stored-mode]').forEach(button => {
      button.addEventListener('click', () => {
        mode = button.getAttribute('data-stored-mode');
        try { localStorage.setItem('labStoredDiffView', mode); } catch {}
        paint();
      });
    });
    paint();
  }

  // ─── Diff code comments (text-anchored, like doc comments) ───
  // Store shape (shared with doc comments in comments.json):
  //   {file, text, comment, kind:'code', repo, created,
  //    scope, sha}  ← scope/sha are REFERENCE labels only
  //
  // The comment is anchored to `text`. On render we scan each file's
  // code cells and wrap matches in <mark>, then stack comment cards
  // inline below the row containing the match. Scope/SHA are shown
  // in the card header as "written while viewing @abc1234".

  function currentDiffScope() {
    if (!currentDiffTab) return {scope: 'uncommitted', sha: null};
    if (currentDiffTab.startsWith('commit:')) {
      return {scope: 'commit', sha: currentDiffTab.slice('commit:'.length)};
    }
    if (currentDiffTab === 'branch') return {scope: 'branch', sha: null};
    return {scope: 'uncommitted', sha: null};
  }

  function currentRepoRelativeToWorkspace() {
    if (!currentRepo) return null;
    if (!currentWorkspace || !currentWorkspace.path) return currentRepo;
    const p = currentWorkspace.path.endsWith('/') ? currentWorkspace.path : currentWorkspace.path + '/';
    return currentRepo.startsWith(p) ? currentRepo.slice(p.length) : currentRepo;
  }

  // Resolve which file a selection started in by walking up to the
  // enclosing diff table and reading its data-file attribute. Returns
  // null if the selection isn't inside a diff.
  function fileForSelectionAnchor(node) {
    if (!node) return null;
    const el = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    if (!el) return null;
    const table = el.closest('table.diff-table, table.split-table');
    return table ? table.getAttribute('data-file') : null;
  }

  function wireDiffCodeCommentSelection(container) {
    // Right-click on a selection inside any diff table → wrap selection
    // in a pending <mark> and open the composer near it. Mirrors the
    // pattern used in workspaceDocBody for doc comments.
    container.addEventListener('contextmenu', (e) => {
      const sel = window.getSelection();
      const text = sel ? sel.toString() : '';
      if (!text || !text.trim()) return;
      // Bail if the selection didn't originate in a code cell.
      const anchorNode = sel.anchorNode;
      const file = fileForSelectionAnchor(anchorNode);
      if (!file) return;
      e.preventDefault();
      removePendingCommentMark();
      let markRect = null;
      try {
        const range = sel.getRangeAt(0);
        markRect = range.getBoundingClientRect();
        const mark = document.createElement('mark');
        mark.setAttribute('data-comment-pending', '1');
        mark.style.cssText = 'background:#5c4b00;color:inherit;border-radius:2px';
        try { range.surroundContents(mark); }
        catch (_) {
          const frag = range.extractContents();
          mark.appendChild(frag);
          range.insertNode(mark);
        }
        _pendingCommentMark = mark;
        sel.removeAllRanges();
      } catch (_) { return; }
      openDiffCommentPopover({
        file,
        text: text.trim(),
        rect: markRect || {top: e.clientY, bottom: e.clientY, left: e.clientX},
      });
    });
  }

  let _cmtPopoverCloser = null;
  function openDiffCommentPopover(ctx) {
    closeDiffCommentPopover({keepPendingMark: true});
    const pop = document.getElementById('cmtPopover');
    if (!pop) return;
    const {scope, sha} = currentDiffScope();
    const repo = currentRepoRelativeToWorkspace();
    const repoLabel = repo ? repo.split('/').pop() : '(no repo)';
    const scopeLabel = scope === 'commit' ? `commit ${(sha || '').slice(0, 7)}` : scope;
    const preview = ctx.text.length > 120 ? ctx.text.slice(0, 120) + '…' : ctx.text;
    pop.innerHTML = `
      <div class="cp-title">New comment on highlighted text</div>
      <div class="cp-ctx">${escapeHtml(repoLabel)} · ${escapeHtml(ctx.file)} · <span style="color:var(--accent)">${escapeHtml(scopeLabel)}</span></div>
      <div class="cp-ctx" style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--text-secondary);white-space:pre-wrap;background:var(--bg-tertiary);padding:6px 8px;border-radius:4px;max-height:80px;overflow:auto">${escapeHtml(preview)}</div>
      <textarea id="cmtText" placeholder="Your note on this code… (⌘/Ctrl+Enter to save)"></textarea>
      <div class="cp-err" data-err></div>
      <div class="cp-row">
        <button type="button" class="secondary" data-act="cancel">Cancel</button>
        <button type="button" data-act="save">Save</button>
      </div>`;
    // Anchor to the selection's bounding rect so the composer opens next
    // to the highlight. Clamp to the viewport on the right.
    const top = (ctx.rect.bottom || ctx.rect.top || 0) + window.scrollY + 6;
    const left = (ctx.rect.left || 0) + window.scrollX;
    pop.style.top = `${top}px`;
    pop.style.left = `${left}px`;
    pop.classList.add('open');
    requestAnimationFrame(() => {
      const pr = pop.getBoundingClientRect();
      if (pr.right > window.innerWidth - 8) {
        pop.style.left = `${Math.max(8, window.innerWidth - pr.width - 8) + window.scrollX}px`;
      }
    });

    const textArea = pop.querySelector('#cmtText');
    textArea.focus();
    const err = pop.querySelector('[data-err]');
    pop.querySelector('[data-act="cancel"]').addEventListener('click', () => closeDiffCommentPopover());
    pop.querySelector('[data-act="save"]').addEventListener('click', async () => {
      const comment = textArea.value.trim();
      if (!comment) { err.textContent = 'write something first'; return; }
      const ok = await saveDiffComment({file: ctx.file, text: ctx.text}, comment, err);
      if (ok) {
        closeDiffCommentPopover({keepPendingMark: false});
        await renderDiffComments(document.getElementById('content'));
      }
    });
    textArea.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closeDiffCommentPopover();
      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) pop.querySelector('[data-act="save"]').click();
    });
    _cmtPopoverCloser = (e) => { if (!pop.contains(e.target)) closeDiffCommentPopover(); };
    setTimeout(() => document.addEventListener('click', _cmtPopoverCloser), 0);
  }

  function closeDiffCommentPopover(opts) {
    const pop = document.getElementById('cmtPopover');
    if (!pop) return;
    pop.classList.remove('open');
    pop.innerHTML = '';
    if (_cmtPopoverCloser) {
      document.removeEventListener('click', _cmtPopoverCloser);
      _cmtPopoverCloser = null;
    }
    if (!opts || !opts.keepPendingMark) removePendingCommentMark();
  }

  async function saveDiffComment(ctx, comment, errEl) {
    if (!currentWorkspace || !currentWorkspace.path) {
      if (errEl) errEl.textContent = 'no workspace loaded';
      return false;
    }
    const {scope, sha} = currentDiffScope();
    const body = {
      path: currentWorkspace.path,
      file: ctx.file,
      text: ctx.text,          // the highlighted code snippet — anchors the comment
      comment,
      kind: 'code',
      repo: currentRepoRelativeToWorkspace(),
      // Reference labels only; NOT used to filter where the comment renders.
      scope,
      sha: sha || undefined,
    };
    try {
      const r = await fetch('/api/workspace-comments', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        if (errEl) errEl.textContent = j.detail || ('error ' + r.status);
        return false;
      }
      return true;
    } catch (e) {
      if (errEl) errEl.textContent = e.message || String(e);
      return false;
    }
  }

  async function renderDiffComments(container) {
    if (!currentWorkspace || !currentWorkspace.path) return;
    let comments = [];
    try {
      const r = await fetch('/api/workspace-comments?path=' + encodeURIComponent(currentWorkspace.path));
      comments = r.ok ? await r.json() : [];
    } catch { return; }
    const repo = currentRepoRelativeToWorkspace();
    // Anchor by text, not by line/scope. Match comments that belong to
    // this repo and this file — scope/sha survive as metadata labels
    // shown in each card, not as filters.
    const match = comments.filter(c => {
      if (c.kind !== 'code') return false;
      if (c.repo && repo && c.repo !== repo) return false;
      return true;
    });

    // Wipe prior overlays so we don't accumulate on re-render.
    container.querySelectorAll('tr.cmt-row').forEach(tr => tr.remove());
    container.querySelectorAll('mark[data-comment-id]').forEach(m => {
      const parent = m.parentNode;
      while (m.firstChild) parent.insertBefore(m.firstChild, m);
      parent.removeChild(m);
      try { parent.normalize(); } catch {}
    });

    if (match.length === 0) return;

    // Group by file for targeted lookup inside each diff table.
    const byFile = new Map();
    for (const c of match) {
      if (!byFile.has(c.file)) byFile.set(c.file, []);
      byFile.get(c.file).push(c);
    }

    container.querySelectorAll('table.diff-table, table.split-table').forEach(table => {
      const fname = table.getAttribute('data-file');
      const cmts = byFile.get(fname);
      if (!cmts || cmts.length === 0) return;
      const isSplit = table.classList.contains('split-table');

      for (const c of cmts) {
        // Try each code cell in turn; wrap the first match. Splitting by
        // cell keeps the mark contained inside a single <td>, so highlight
        // doesn't blow up row boundaries.
        let matchedCell = null;
        const cells = table.querySelectorAll('td.code');
        for (const td of cells) {
          if (highlightCommentInNode(td, c.text, c.id)) { matchedCell = td; break; }
        }
        // Insert a comment card below whichever row got highlighted. If
        // the text didn't match anywhere in the current view (e.g. we're
        // looking at a different commit), still surface the card at the
        // top of the table so the user sees that there's a comment.
        const targetRow = matchedCell
          ? matchedCell.closest('tr')
          : table.querySelector('tbody tr, tr');
        if (!targetRow) continue;
        const colspan = isSplit ? 6 : 4;
        const scopeLabel = c.scope === 'commit'
          ? `@${(c.sha || '').slice(0,7)}`
          : (c.scope || 'uncommitted');
        const notMatched = matchedCell ? '' : ' <span title="text no longer present in current view" style="color:var(--yellow)">(orphaned)</span>';
        const existingRow = targetRow.nextElementSibling && targetRow.nextElementSibling.classList.contains('cmt-row')
          ? targetRow.nextElementSibling : null;
        const cardHtml = `
          <div class="cmt-box">
            <div class="cmt-head">
              <span class="cmt-scope" title="where it was written">${escapeHtml(scopeLabel)}${notMatched}</span>
              <span>${escapeHtml(c.created || '')}</span>
              <button class="cmt-rm" type="button" data-cmt-id="${c.id}" title="Delete comment">✕</button>
            </div>
            <div class="cmt-body">${escapeHtml(c.comment || '')}</div>
          </div>`;
        if (existingRow) {
          existingRow.firstElementChild.insertAdjacentHTML('beforeend', cardHtml);
        } else {
          const tr = document.createElement('tr');
          tr.className = 'cmt-row';
          tr.innerHTML = `<td colspan="${colspan}">${cardHtml}</td>`;
          targetRow.parentNode.insertBefore(tr, targetRow.nextSibling);
        }
      }
    });

    container.querySelectorAll('.cmt-rm').forEach(btn => {
      btn.addEventListener('click', async () => {
        const id = parseInt(btn.getAttribute('data-cmt-id'), 10);
        if (!id) return;
        if (!confirm('Delete this comment?')) return;
        try {
          await fetch('/api/workspace-comments', {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: currentWorkspace.path, comment_id: id}),
          });
        } catch {}
        await renderDiffComments(container);
      });
    });
  }

  function renderUnified(file) {
    if (!file.hunks.length) return '<div class="empty-diff">Empty file</div>';
    const lang = filenameLang(file.filename);
    let rows = '';
    file.hunks.forEach((h, hi) => {
      rows += `<tr class="hunk-sep"><td colspan="4">@@ -${h.old_start},${h.old_count} +${h.new_start},${h.new_count} @@</td></tr>`;
      const lines = h.lines;
      let i = 0;
      while (i < lines.length) {
        const l = lines[i];
        if (l.type === 'context') {
          rows += `<tr class="context"><td class="ln">${l.old_num}</td><td class="ln">${l.new_num}</td><td class="gutter"></td><td class="code">${hlLine(l.content, lang)}</td></tr>`;
          i++;
        } else if (l.type === 'delete') {
          const dels = []; while (i < lines.length && lines[i].type === 'delete') { dels.push(lines[i]); i++; }
          const adds = []; while (i < lines.length && lines[i].type === 'add') { adds.push(lines[i]); i++; }
          for (let j = 0; j < dels.length; j++) {
            const d = dels[j], a = adds[j];
            if (a) {
              const [dh] = wordDiff(d.content, a.content);
              rows += `<tr class="delete"><td class="ln">${d.old_num}</td><td class="ln"></td><td class="gutter"></td><td class="code">${dh}</td></tr>`;
            } else {
              rows += `<tr class="delete"><td class="ln">${d.old_num}</td><td class="ln"></td><td class="gutter"></td><td class="code">${hlLine(d.content, lang)}</td></tr>`;
            }
          }
          for (let j = 0; j < adds.length; j++) {
            const a = adds[j], d = dels[j];
            if (d) {
              const [, ah] = wordDiff(d.content, a.content);
              rows += `<tr class="add"><td class="ln"></td><td class="ln">${a.new_num}</td><td class="gutter"></td><td class="code">${ah}</td></tr>`;
            } else {
              rows += `<tr class="add"><td class="ln"></td><td class="ln">${a.new_num}</td><td class="gutter"></td><td class="code">${hlLine(a.content, lang)}</td></tr>`;
            }
          }
        } else if (l.type === 'add') {
          rows += `<tr class="add"><td class="ln"></td><td class="ln">${l.new_num}</td><td class="gutter"></td><td class="code">${hlLine(l.content, lang)}</td></tr>`;
          i++;
        } else { i++; }
      }
    });
    return `<table class="diff-table" data-file="${file.filename.replace(/"/g,'&quot;')}"><colgroup><col class="ln"><col class="ln"><col class="gutter"><col class="content"></colgroup>${rows}</table>`;
  }

  function renderSplit(file) {
    if (!file.hunks.length) return '<div class="empty-diff">Empty file</div>';
    const lang = filenameLang(file.filename);
    let rows = '';
    file.hunks.forEach((h, hi) => {
      rows += `<tr class="hunk-sep"><td colspan="6">@@ -${h.old_start},${h.old_count} +${h.new_start},${h.new_count} @@</td></tr>`;
      const lines = h.lines;
      let i = 0;
      while (i < lines.length) {
        const l = lines[i];
        if (l.type === 'context') {
          const hl = hlLine(l.content, lang);
          rows += `<tr><td class="ln">${l.old_num}</td><td class="gutter"></td><td class="code ctx-code">${hl}</td><td class="ln">${l.new_num}</td><td class="gutter"></td><td class="code ctx-code">${hl}</td></tr>`;
          i++;
        } else if (l.type === 'delete') {
          const dels = []; while (i < lines.length && lines[i].type === 'delete') { dels.push(lines[i]); i++; }
          const adds = []; while (i < lines.length && lines[i].type === 'add') { adds.push(lines[i]); i++; }
          const max = Math.max(dels.length, adds.length);
          for (let j = 0; j < max; j++) {
            const d = dels[j], a = adds[j];
            const lln = d ? d.old_num : '', lcls = d ? 'del' : 'empty';
            const rln = a ? a.new_num : '', rcls = a ? 'add' : 'empty';
            let lc, rc;
            if (d && a) {
              const [dh, ah] = wordDiff(d.content, a.content);
              lc = dh; rc = ah;
            } else {
              lc = d ? hlLine(d.content, lang) : '';
              rc = a ? hlLine(a.content, lang) : '';
            }
            rows += `<tr><td class="ln ${lcls}-ln">${lln}</td><td class="gutter ${lcls}-gutter"></td><td class="code ${lcls}-code">${lc}</td><td class="ln ${rcls}-ln">${rln}</td><td class="gutter ${rcls}-gutter"></td><td class="code ${rcls}-code">${rc}</td></tr>`;
          }
        } else if (l.type === 'add') {
          rows += `<tr><td class="ln empty"></td><td class="gutter"></td><td class="code empty"></td><td class="ln add-ln">${l.new_num}</td><td class="gutter add-gutter"></td><td class="code add-code">${hlLine(l.content, lang)}</td></tr>`;
          i++;
        } else { i++; }
      }
    });
    return `<table class="split-table" data-file="${file.filename.replace(/"/g,'&quot;')}"><colgroup><col class="ln"><col class="gutter"><col class="half"><col class="ln"><col class="gutter"><col class="half"></colgroup>${rows}</table>`;
  }

  function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

  // Escape for use inside an HTML attribute value (double-quoted). Used by
  // sidebar trees that put folder paths into data-* attributes.
  function escAttr(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function symlinkMarker(node) {
    if (!node || !node.is_symlink) return '';
    const target = node.symlink_target ? ` -> ${node.symlink_target}` : '';
    return `<span class="symlink-mark" title="${escAttr('Symlink' + target)}">&#x21AA;</span>`;
  }

  function symlinkClass(node) {
    return node && node.is_symlink ? ' is-symlink' : '';
  }

  function symlinkTitle(node) {
    if (!node || !node.is_symlink) return '';
    const target = node.symlink_target ? ` -> ${node.symlink_target}` : '';
    return ` title="${escAttr('Symlink' + target)}"`;
  }

  function symlinkLegendHtml() {
    return '<div class="symlink-legend"><span class="symlink-mark">&#x21AA;</span><span>symlink</span></div>';
  }

  // ─── File-type icons (VS Code Explorer-style) ───────────────────────────
  // One shared extension → icon mapping for every sidebar/tree file row.
  // Inline SVGs styled after the familiar logos (Python snakes, Jupyter
  // moons, JS/TS squares, markdown mark…) so types read at a glance — no
  // external assets. The markup is a fixed-size span so rows align
  // regardless of icon shape. Symlinked entries get a small corner-arrow
  // overlay (`ft-ln`), mirroring VS Code's symlink icon decoration.
  const _FT_FONT = "-apple-system,'Segoe UI',Roboto,sans-serif";
  const _ftDoc = (stroke) => `<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="${stroke}" stroke-width="1.2"><path d="M4 1.5h5.5L13 5v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V2.5a1 1 0 0 1 1-1z"/><path d="M9.5 1.5V5H13"/></svg>`;
  const _ftBadge = (bg, label, fg) => `<svg viewBox="0 0 16 16" width="14" height="14"><rect width="16" height="16" rx="3" fill="${bg}"/><text x="8" y="11.8" text-anchor="middle" font-size="8.5" font-weight="700" font-family="${_FT_FONT}" fill="${fg}">${label}</text></svg>`;
  const _ftText = (label, color, size) => `<svg viewBox="0 0 16 16" width="14" height="14"><text x="8" y="12" text-anchor="middle" font-size="${size || 10}" font-weight="700" font-family="${_FT_FONT}" fill="${color}">${label}</text></svg>`;
  const _FT_SVGS = {
    // Python: the two interlocked snakes (blue over yellow, white eyes).
    py: '<svg viewBox="0 0 24 24" width="14" height="14"><path fill="#3776AB" d="M11.9 2c-5 0-4.6 2.2-4.6 2.2v2.3h4.7v.7H5.3S2 6.8 2 11.9c0 5 2.9 4.9 2.9 4.9h1.7v-2.4s-.1-2.9 2.8-2.9h4.7s2.7.1 2.7-2.6V4.7S17.2 2 11.9 2zM9.3 3.4a.9.9 0 1 1 0 1.8.9.9 0 0 1 0-1.8z"/><path fill="#FFD43B" d="M12.1 22c5 0 4.6-2.2 4.6-2.2v-2.3H12v-.7h6.7s3.3.4 3.3-4.7c0-5-2.9-4.9-2.9-4.9h-1.7v2.4s.1 2.9-2.8 2.9h-4.7s-2.7-.1-2.7 2.6v4.2S6.8 22 12.1 22zm2.6-1.4a.9.9 0 1 1 0-1.8.9.9 0 0 1 0 1.8z"/></svg>',
    // Jupyter: orange top/bottom crescents plus the two grey moons.
    ipynb: '<svg viewBox="0 0 16 16" width="14" height="14"><path fill="#F37726" d="M8 12.1c-2.1 0-3.9-.9-5-2.2a5.4 5.4 0 0 0 10 0c-1.1 1.3-2.9 2.2-5 2.2zM8 3.9c2.1 0 3.9.9 5 2.2a5.4 5.4 0 0 0-10 0c1.1-1.3 2.9-2.2 5-2.2z"/><circle cx="13" cy="13.2" r="1" fill="#989798"/><circle cx="2.8" cy="2.6" r=".8" fill="#6f7070"/></svg>',
    // Markdown: rounded box with the M-and-arrow mark.
    md: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#519ABA" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="3.2" width="14" height="9.6" rx="1.5"/><path d="M3.4 10.3V5.7l1.9 2.2 1.9-2.2v4.6"/><path d="M11.6 5.9v3M10.2 7.6l1.4 1.7 1.4-1.7"/></svg>',
    sh: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><rect x="1" y="2.2" width="14" height="11.6" rx="1.8" stroke="#4EAA25" stroke-width="1.1"/><path d="M3.8 6l2.1 2-2.1 2M8.4 10.4h3.4" stroke="#4EAA25" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    csv: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#8BC34A" stroke-width="1.1"><rect x="1.5" y="2.5" width="13" height="11" rx="1"/><path d="M1.5 6h13M1.5 9.5h13M6 2.5v11M10.5 2.5v11"/></svg>',
    // SQL: a compact database cylinder, the common visual shorthand for SQL.
    sql: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none"><path d="M2 4v8c0 1.1 2.7 2 6 2s6-.9 6-2V4" fill="#4479A1"/><ellipse cx="8" cy="4" rx="6" ry="2.3" fill="#69A7D0"/><path d="M2 8c0 1.1 2.7 2 6 2s6-.9 6-2M2 11c0 1.1 2.7 2 6 2s6-.9 6-2" stroke="#C7E9FF" stroke-width=".9"/></svg>',
    // Scala: the language's three stacked red ribbon forms.
    scala: '<svg viewBox="0 0 16 16" width="14" height="14"><path fill="#DE3423" d="M3 1.5c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1V1.5zm0 5.1c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1V6.6zm0 5.1c3.4 1 6.5-.1 10-1v4.1c-3.3.9-6.6 2-10 1v-4.1z"/></svg>',
    git: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#F05033" stroke-width="1.2"><circle cx="4.5" cy="3.8" r="1.5"/><circle cx="4.5" cy="12.2" r="1.5"/><circle cx="11.5" cy="8" r="1.5"/><path d="M4.5 5.3v5.4M6 8h4" stroke-linecap="round"/></svg>',
    vid: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#A074C4" stroke-width="1.2"><rect x="1.5" y="3" width="13" height="10" rx="1.5"/><path d="M6.5 6l3.5 2-3.5 2z" fill="#A074C4" stroke="none"/></svg>',
    conf: '<svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="#A074C4" stroke-width="1.2" stroke-linecap="round"><path d="M2.5 5.2h11M2.5 10.8h11"/><circle cx="6.2" cy="5.2" r="1.5" fill="var(--bg-primary,#111)"/><circle cx="10" cy="10.8" r="1.5" fill="var(--bg-primary,#111)"/></svg>',
    img: '<svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.2"><rect x="2" y="3" width="12" height="10" rx="1"/><circle cx="5.5" cy="6.5" r="1" fill="currentColor" stroke="none"/><path d="M2.5 11.5l3-2.8 2.8 2.3 2.7-2.5 2.5 2.5"/></svg>',
  };
  function fileIconHtml(name, node) {
    const base = String(name || '').split('/').pop();
    const lower = base.toLowerCase();
    const ext = lower.includes('.') ? lower.slice(lower.lastIndexOf('.') + 1) : '';
    let cls, glyph;
    if ((node && node.type === 'image') || ['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp', 'ico', 'bmp'].includes(ext)) { cls = 'ft-img'; glyph = _FT_SVGS.img; }
    else if (['mp4', 'webm', 'mov', 'm4v'].includes(ext)) { cls = 'ft-vid'; glyph = _FT_SVGS.vid; }
    else if (ext === 'ipynb') { cls = 'ft-nb'; glyph = _FT_SVGS.ipynb; }
    else if (ext === 'md' || ext === 'markdown' || ext === 'rst') { cls = 'ft-md'; glyph = _FT_SVGS.md; }
    else if (ext === 'py') { cls = 'ft-py'; glyph = _FT_SVGS.py; }
    else if (['js', 'mjs', 'cjs', 'jsx'].includes(ext)) { cls = 'ft-js'; glyph = _ftBadge('#F7DF1E', 'JS', '#222'); }
    else if (ext === 'ts' || ext === 'tsx') { cls = 'ft-ts'; glyph = _ftBadge('#3178C6', 'TS', '#fff'); }
    else if (ext === 'json' || ext === 'lock') { cls = 'ft-json'; glyph = _ftText('{}', '#CBCB41'); }
    else if (['toml', 'yaml', 'yml', 'ini', 'cfg'].includes(ext)) { cls = 'ft-json'; glyph = _FT_SVGS.conf; }
    else if (['html', 'htm', 'xml'].includes(ext)) { cls = 'ft-html'; glyph = _ftText('&lt;&gt;', '#E44D26', 9); }
    else if (['css', 'scss', 'less'].includes(ext)) { cls = 'ft-css'; glyph = _ftText('#', '#2965F1', 11); }
    else if (['sh', 'bash', 'zsh', 'fish'].includes(ext) || lower === 'makefile' || lower === 'dockerfile') { cls = 'ft-sh'; glyph = _FT_SVGS.sh; }
    else if (ext === 'pdf') { cls = 'ft-pdf'; glyph = _ftDoc('#E5252A'); }
    else if (ext === 'sql') { cls = 'ft-sql'; glyph = _FT_SVGS.sql; }
    else if (ext === 'scala') { cls = 'ft-scala'; glyph = _FT_SVGS.scala; }
    else if (['csv', 'tsv', 'parquet'].includes(ext)) { cls = 'ft-csv'; glyph = _FT_SVGS.csv; }
    else if (lower.startsWith('.git')) { cls = 'ft-git'; glyph = _FT_SVGS.git; }
    else { cls = 'ft-generic'; glyph = _ftDoc('currentColor'); }
    const ln = node && node.is_symlink ? ' ft-ln' : '';
    return `<span class="ft-icon ${cls}${ln}" aria-hidden="true">${glyph}</span>`;
  }

  function buildSidebarTree(entries) {
    const tree = {};
    const ensureDir = (path, meta = null) => {
      const parts = String(path || '').split('/').filter(Boolean);
      let node = tree;
      let fullPath = '';
      parts.forEach((part, idx) => {
        fullPath = fullPath ? `${fullPath}/${part}` : part;
        if (!node[part]) node[part] = {};
        if (meta && idx === parts.length - 1) {
          node[part].__entry__ = { ...meta, name: part, path: fullPath, type: 'dir' };
        }
        node = node[part];
      });
      return node;
    };
    (entries || []).filter(e => e && e.type === 'dir').forEach(d => ensureDir(d.path || d.name, d));
    (entries || []).filter(e => e && e.type !== 'dir').forEach(f => {
      const path = String(f.path || f.name || '');
      const parts = path.split('/').filter(Boolean);
      if (!parts.length) return;
      const parent = ensureDir(parts.slice(0, -1).join('/'));
      parent.__files__ = parent.__files__ || [];
      parent.__files__.push(f);
    });
    return tree;
  }

  function _sidebarEntryName(entry) {
    return String(entry && (entry.path || entry.name) || '').split('/').pop();
  }

  function _sidebarCompareNames(a, b) {
    return String(a || '').localeCompare(String(b || ''), undefined, {
      numeric: true,
      sensitivity: 'base',
    });
  }

  function _sidebarCompareFiles(a, b, mode = 'name') {
    const nameA = _sidebarEntryName(a);
    const nameB = _sidebarEntryName(b);
    if (mode === 'updated') {
      const updated = Number(b && b.mtime || 0) - Number(a && a.mtime || 0);
      if (updated) return updated;
    } else if (mode === 'type') {
      const type = _sidebarCompareNames(_sidebarFileExtension(nameA), _sidebarFileExtension(nameB));
      if (type) return type;
    }
    return _sidebarCompareNames(nameA, nameB)
      || _sidebarCompareNames(a && (a.path || a.name), b && (b.path || b.name));
  }

  function _sidebarTreeLatestMtime(node) {
    let latest = 0;
    ((node && node.__files__) || []).forEach(file => {
      latest = Math.max(latest, Number(file && file.mtime || 0));
    });
    Object.keys(node || {})
      .filter(key => key !== '__files__' && key !== '__entry__')
      .forEach(key => { latest = Math.max(latest, _sidebarTreeLatestMtime(node[key])); });
    return latest;
  }

  function treeFolderNames(node, mode = 'name') {
    const folders = Object.keys(node || {}).filter(k => k !== '__files__' && k !== '__entry__');
    if (mode !== 'updated') return folders.sort(_sidebarCompareNames);
    const latest = new Map(folders.map(folder => [folder, _sidebarTreeLatestMtime(node[folder])]));
    return folders.sort((a, b) => Number(latest.get(b)) - Number(latest.get(a))
      || _sidebarCompareNames(a, b));
  }

  function treeFolderEntry(node, folder, fullPath) {
    return (node && node[folder] && node[folder].__entry__) || { name: folder, path: fullPath, type: 'dir' };
  }

  function treeFiles(node, mode = 'name') {
    return [...((node && node.__files__) || [])]
      .sort((a, b) => _sidebarCompareFiles(a, b, mode));
  }

  // ─── Explorer secondary-click menu ────────────────────────────────────
  // One delegated menu serves the workspace, vault, framework, and repo
  // trees. Rows opt in with data-entry-kind/path; virtual rows (servers,
  // external links, Overview) deliberately do not expose filesystem actions.
  let _explorerContext = null;
  let _explorerEntryState = null;
  let _explorerDeleteState = null;
  let _explorerHistoryState = null;
  let _explorerHistoryRequest = 0;
  let _explorerToastTimer = null;
  const _notebookFoldersByRoot = new Map();

  function _rememberNotebookFolders(root, entries) {
    if (!root) return;
    const folders = new Set();
    (entries || []).forEach(entry => {
      if (!entry) return;
      const path = String(entry.path || entry.name || '').replace(/^\/+|\/+$/g, '');
      if (!path) return;
      const parts = path.split('/').filter(Boolean);
      const folderParts = entry.type === 'dir' ? parts : parts.slice(0, -1);
      for (let depth = 1; depth <= folderParts.length; depth += 1) {
        folders.add(folderParts.slice(0, depth).join('/'));
      }
    });
    _notebookFoldersByRoot.set(root, ['', ...folders].sort((a, b) => {
      if (!a) return -1;
      if (!b) return 1;
      return a.localeCompare(b);
    }));
  }

  function _canCreateExecutableNotebook(root) {
    if (!root || !currentWorkspace || root !== currentWorkspace.path) return false;
    return _vaultRelativeNotebookPathOrNull(root, '__lab_notebook_probe__.ipynb') !== null;
  }

  function openNewFileAtRoot(root, surface = 'workspace') {
    const fileRoot = String(root || '').trim();
    if (!fileRoot) {
      explorerToast('No file root is available.', true);
      return;
    }
    openExplorerEntryDialog('create-file', {
      kind: 'folder',
      path: '',
      root: fileRoot,
      surface: surface === 'repo' ? 'repo' : 'workspace',
    });
  }
  window.openNewFileAtRoot = openNewFileAtRoot;

  function _sidebarFilesTitle(root, surface = 'workspace') {
    const safeSurface = surface === 'repo' ? 'repo' : 'workspace';
    const createFile = `<button class="sidebar-title-action" type="button" data-new-file-root="${escAttr(root || '')}" data-new-file-surface="${safeSurface}" onclick="event.stopPropagation();openNewFileAtRoot(this.dataset.newFileRoot,this.dataset.newFileSurface)" title="Create a file at this Files root">＋ File</button>`;
    const createNotebook = _canCreateExecutableNotebook(root)
      ? '<button class="sidebar-title-action" type="button" onclick="event.stopPropagation();openNewNotebookDialog()" title="Choose a repository folder and create a notebook">＋ Notebook</button>'
      : '';
    return `<div class="sidebar-title sidebar-title-with-action"><span>Files</span><span class="sidebar-title-actions">${_sidebarSortSelectHtml('files')}${createFile}${createNotebook}</span></div>`;
  }

  function _explorerContextFromRow(row) {
    if (!row) return null;
    const kind = row.getAttribute('data-entry-kind');
    const path = row.getAttribute('data-entry-path');
    if (!kind || !path) return null;
    const isRepoTree = row.classList.contains('tree-file') || row.classList.contains('tree-dir');
    const root = row.getAttribute('data-entry-root')
      || (isRepoTree ? currentRepo : (currentWorkspace && currentWorkspace.path));
    if (!root) return null;
    return {kind, path, root, row, surface: isRepoTree ? 'repo' : 'workspace'};
  }

  function closeExplorerContextMenu() {
    const menu = document.getElementById('explorerContextMenu');
    if (menu) {
      menu.classList.remove('open');
      menu.setAttribute('aria-hidden', 'true');
      menu.innerHTML = '';
    }
    document.querySelectorAll('.explorer-context-target').forEach(el => el.classList.remove('explorer-context-target'));
    _explorerContext = null;
  }
  window.closeExplorerContextMenu = closeExplorerContextMenu;

  function _explorerMenuButton(action, icon, label, shortcut, danger) {
    return `<button type="button" role="menuitem" data-explorer-action="${escAttr(action)}"${danger ? ' class="danger"' : ''}>
      <span class="ecm-icon" aria-hidden="true">${icon}</span><span>${label}</span><span class="ecm-shortcut">${shortcut || ''}</span>
    </button>`;
  }

  function openExplorerContextMenu(event, row) {
    const ctx = _explorerContextFromRow(row);
    if (!ctx) return;
    event.preventDefault();
    event.stopPropagation();
    closeExplorerContextMenu();
    _explorerContext = ctx;
    row.classList.add('explorer-context-target');
    const menu = document.getElementById('explorerContextMenu');
    if (!menu) return;
    const folderOpen = ctx.kind === 'folder' && (
      row.querySelector('.folder-arrow.open')
      || (row.nextElementSibling
          && row.nextElementSibling.classList.contains('tree-dir-children')
          && !row.nextElementSibling.classList.contains('collapsed'))
    );
    const firstLabel = ctx.kind === 'folder' ? (folderOpen ? 'Collapse' : 'Expand') : 'Open';
    const firstIcon = ctx.kind === 'folder' ? (folderOpen ? '▾' : '▸') : '↗';
    const notebookAction = ctx.surface === 'workspace' && _canCreateExecutableNotebook(ctx.root)
      ? _explorerMenuButton('new-notebook', '◉', 'New notebook here', '')
      : '';
    const linkedSessions = _termSessionsLinkedToContext(ctx);
    const linkTerminalAction =
      _explorerMenuButton('link-active-terminal', '⇄', 'Link to active terminal', '') +
      (ctx.kind === 'file' ? _explorerMenuButton('link-terminal', '⇄', 'Link terminal…', '') : '') +
      linkedSessions.map(session => _explorerMenuButton(
        'unlink-terminal:' + encodeURIComponent(session.name), '×',
        linkedSessions.length === 1 ? 'Unlink from terminal' : `Unlink from ${esc(_termSessionDisplay(session))}`, '')).join('');
    menu.innerHTML = `
      <div class="ecm-label" title="${escAttr(ctx.path)}">${esc(ctx.path)}</div>
      ${_explorerMenuButton('open', firstIcon, firstLabel, ctx.kind === 'file' ? 'Enter' : '')}
      ${_explorerMenuButton('history', '⑂', 'View Git history', '')}
      ${_explorerMenuButton('copy-path', '⧉', 'Copy relative path', '')}
      ${linkTerminalAction}
      <div class="ecm-sep" role="separator"></div>
      ${notebookAction}
      ${_explorerMenuButton('new-file', '+', 'New file here', '')}
      ${_explorerMenuButton('new-folder', '▢', 'New folder here', '')}
      <div class="ecm-sep" role="separator"></div>
      ${_explorerMenuButton('rename', '✎', 'Rename', '')}
      ${_explorerMenuButton('delete', '⌫', `Delete ${ctx.kind}`, '', true)}`;
    menu.classList.add('open');
    menu.setAttribute('aria-hidden', 'false');
    menu.style.left = Math.max(8, event.clientX) + 'px';
    menu.style.top = Math.max(8, event.clientY) + 'px';
    // Measure after display and clamp both edges to the viewport.
    const rect = menu.getBoundingClientRect();
    if (rect.right > window.innerWidth - 8) menu.style.left = Math.max(8, window.innerWidth - rect.width - 8) + 'px';
    if (rect.bottom > window.innerHeight - 8) menu.style.top = Math.max(8, window.innerHeight - rect.height - 8) + 'px';
    const first = menu.querySelector('button');
    if (first) first.focus({preventScroll: true});
  }

  function _explorerParentForCreate(ctx) {
    if (ctx.kind === 'folder') return ctx.path;
    const slash = ctx.path.lastIndexOf('/');
    return slash >= 0 ? ctx.path.slice(0, slash) : '';
  }

  async function _explorerMenuAction(action) {
    const ctx = _explorerContext;
    if (!ctx) return;
    if (action === 'open') {
      const row = ctx.row;
      closeExplorerContextMenu();
      if (ctx.kind === 'file') {
        if (ctx.surface === 'repo') openWorkspaceFile(ctx.path);
        else openWorkspaceDoc(ctx.path, {root: ctx.root});
      } else if (row && row.isConnected) {
        row.click();
      }
      return;
    }
    if (action === 'copy-path') {
      const copied = await _copyToClipboard(ctx.path, null);
      closeExplorerContextMenu();
      explorerToast(copied ? `Copied ${ctx.path}` : 'Could not copy path', !copied);
      return;
    }
    closeExplorerContextMenu();
    if (action === 'link-active-terminal') return termLinkTarget(ctx, termCurrentSession);
    if (action.startsWith('unlink-terminal:')) return termUnlinkTarget(
      decodeURIComponent(action.slice('unlink-terminal:'.length)), ctx.kind === 'file' ? 'file' : 'scope');
    if (action === 'link-terminal') return termOpenLinkModal(ctx);
    if (action === 'history') return openExplorerHistory(ctx);
    if (action === 'rename') return openExplorerEntryDialog('rename', ctx);
    if (action === 'new-notebook') return openNewNotebookDialog(ctx);
    if (action === 'new-file') return openExplorerEntryDialog('create-file', ctx);
    if (action === 'new-folder') return openExplorerEntryDialog('create-folder', ctx);
    if (action === 'delete') return openExplorerDeleteDialog(ctx);
  }

  function explorerToast(message, error = false) {
    const toast = document.getElementById('explorerToast');
    if (!toast) return;
    if (_explorerToastTimer) clearTimeout(_explorerToastTimer);
    toast.textContent = message;
    toast.classList.toggle('error', !!error);
    toast.classList.add('show');
    _explorerToastTimer = setTimeout(() => toast.classList.remove('show'), 1800);
  }

  function openExplorerEntryDialog(action, ctx) {
    const modal = document.getElementById('explorerEntryModal');
    const input = document.getElementById('explorerEntryName');
    const error = document.getElementById('explorerEntryError');
    const parentLabel = document.getElementById('explorerEntryParentLabel');
    const hint = document.getElementById('explorerEntryHint');
    if (!modal || !input || !ctx) return;
    const isRename = action === 'rename';
    const kind = action === 'create-folder' ? 'folder' : 'file';
    const parent = isRename ? '' : _explorerParentForCreate(ctx);
    _explorerEntryState = {action, ctx, kind, parent};
    document.getElementById('explorerEntryTitle').textContent = isRename
      ? `Rename ${ctx.kind}` : `New ${kind}`;
    document.getElementById('explorerEntryLabel').firstChild.textContent = isRename
      ? 'New name ' : `Name in ${parent || 'vault root'} `;
    document.getElementById('explorerEntrySubmit').textContent = isRename ? 'Rename' : 'Create';
    input.value = isRename ? ctx.path.split('/').pop() : '';
    input.placeholder = kind === 'folder' ? 'folder-name' : 'filename.ext';
    if (parentLabel) parentLabel.hidden = true;
    if (hint) hint.hidden = true;
    error.textContent = '';
    modal.classList.add('active');
    requestAnimationFrame(() => {
      input.focus();
      if (isRename) {
        const dot = input.value.lastIndexOf('.');
        input.setSelectionRange(0, dot > 0 ? dot : input.value.length);
      }
    });
  }
  window.openExplorerEntryDialog = openExplorerEntryDialog;

  function openNewNotebookDialog(ctx = null) {
    const root = (ctx && ctx.root) || (currentWorkspace && currentWorkspace.path);
    if (!_canCreateExecutableNotebook(root)) {
      explorerToast('Open a repository inside the active vault to create an executable notebook.', true);
      return;
    }
    const modal = document.getElementById('explorerEntryModal');
    const input = document.getElementById('explorerEntryName');
    const error = document.getElementById('explorerEntryError');
    const parentLabel = document.getElementById('explorerEntryParentLabel');
    const parentSelect = document.getElementById('explorerEntryParent');
    const hint = document.getElementById('explorerEntryHint');
    if (!modal || !input || !parentSelect) return;

    const folders = [...(_notebookFoldersByRoot.get(root) || [''])];
    let parent = ctx ? _explorerParentForCreate(ctx) : (folders.includes('notebooks') ? 'notebooks' : '');
    if (parent && !folders.includes(parent)) folders.push(parent);
    parentSelect.innerHTML = folders.map(folder => {
      const label = folder || '. (repository root)';
      return `<option value="${escAttr(folder)}">${esc(label)}</option>`;
    }).join('');
    parentSelect.value = parent;

    const createContext = ctx || {kind: 'folder', path: parent, root, surface: 'workspace'};
    _explorerEntryState = {action: 'create-notebook', ctx: createContext, kind: 'notebook', parent};
    document.getElementById('explorerEntryTitle').textContent = 'New notebook';
    document.getElementById('explorerEntryLabel').firstChild.textContent = 'Notebook name ';
    document.getElementById('explorerEntrySubmit').textContent = 'Create notebook';
    input.value = 'analysis.ipynb';
    input.placeholder = 'analysis.ipynb';
    if (parentLabel) parentLabel.hidden = false;
    if (hint) hint.hidden = false;
    if (error) error.textContent = '';
    modal.classList.add('active');
    requestAnimationFrame(() => {
      input.focus();
      input.setSelectionRange(0, input.value.lastIndexOf('.'));
    });
  }
  window.openNewNotebookDialog = openNewNotebookDialog;

  function closeExplorerEntryDialog() {
    const modal = document.getElementById('explorerEntryModal');
    if (modal) modal.classList.remove('active');
    _explorerEntryState = null;
  }
  window.closeExplorerEntryDialog = closeExplorerEntryDialog;

  async function _explorerResponseError(response, fallback) {
    const payload = await response.json().catch(() => ({}));
    return payload.detail || fallback || `Request failed (${response.status})`;
  }

  async function submitExplorerEntryDialog(event) {
    event.preventDefault();
    const state = _explorerEntryState;
    if (!state) return false;
    const input = document.getElementById('explorerEntryName');
    const error = document.getElementById('explorerEntryError');
    const submit = document.getElementById('explorerEntrySubmit');
    const isNotebook = state.action === 'create-notebook';
    let name = (input.value || '').trim();
    if (!name) return false;
    if (isNotebook && !name.toLowerCase().endsWith('.ipynb')) name += '.ipynb';
    submit.disabled = true;
    error.textContent = '';
    try {
      const isRename = state.action === 'rename';
      const parent = isNotebook
        ? (document.getElementById('explorerEntryParent').value || '')
        : state.parent;
      const response = await fetch('/api/workspace-entry', {
        method: isRename ? 'PATCH' : 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(isRename ? {
          path: state.ctx.root,
          entry: state.ctx.path,
          new_name: name,
        } : {
          path: state.ctx.root,
          parent,
          name,
          kind: isNotebook ? 'notebook' : state.kind,
        }),
      });
      if (!response.ok) throw new Error(await _explorerResponseError(response));
      const result = await response.json();
      const savedState = isNotebook
        ? {...state, action: 'create-file', kind: 'file', parent}
        : state;
      closeExplorerEntryDialog();
      await _explorerAfterMutation(savedState, result);
      explorerToast(isRename ? `Renamed to ${result.renamed_to}` : (isNotebook ? `Notebook created at ${result.entry}` : `Created ${result.entry}`));
    } catch (e) {
      error.textContent = e.message || String(e);
    } finally {
      submit.disabled = false;
    }
    return false;
  }
  window.submitExplorerEntryDialog = submitExplorerEntryDialog;

  function openExplorerDeleteDialog(ctx) {
    const modal = document.getElementById('explorerDeleteModal');
    if (!modal || !ctx) return;
    _explorerDeleteState = ctx;
    document.getElementById('explorerDeleteTitle').textContent = `Delete ${ctx.kind}?`;
    document.getElementById('explorerDeleteMessage').innerHTML = ctx.kind === 'folder'
      ? `Delete <code>${esc(ctx.path)}</code> and everything inside it? This cannot be undone.`
      : `Delete <code>${esc(ctx.path)}</code>? This cannot be undone.`;
    document.getElementById('explorerDeleteError').textContent = '';
    document.getElementById('explorerDeleteSubmit').disabled = false;
    modal.classList.add('active');
    requestAnimationFrame(() => document.getElementById('explorerDeleteSubmit').focus());
  }
  window.openExplorerDeleteDialog = openExplorerDeleteDialog;

  function closeExplorerDeleteDialog() {
    const modal = document.getElementById('explorerDeleteModal');
    if (modal) modal.classList.remove('active');
    _explorerDeleteState = null;
  }
  window.closeExplorerDeleteDialog = closeExplorerDeleteDialog;

  async function confirmExplorerDelete() {
    const ctx = _explorerDeleteState;
    if (!ctx) return;
    const button = document.getElementById('explorerDeleteSubmit');
    const error = document.getElementById('explorerDeleteError');
    button.disabled = true;
    error.textContent = '';
    try {
      const response = await fetch('/api/workspace-entry', {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: ctx.root, entry: ctx.path}),
      });
      if (!response.ok) throw new Error(await _explorerResponseError(response));
      closeExplorerDeleteDialog();
      await _explorerAfterMutation({action: 'delete', ctx, kind: ctx.kind}, {entry: ctx.path});
      explorerToast(`Deleted ${ctx.path}`);
    } catch (e) {
      error.textContent = e.message || String(e);
      button.disabled = false;
    }
  }
  window.confirmExplorerDelete = confirmExplorerDelete;

  function _explorerPathAffected(activePath, targetPath, kind) {
    return !!activePath && (
      activePath === targetPath
      || (kind === 'folder' && activePath.startsWith(targetPath + '/'))
    );
  }

  function _explorerRenamedActivePath(activePath, oldPath, newPath, kind) {
    if (!_explorerPathAffected(activePath, oldPath, kind)) return activePath;
    return activePath === oldPath ? newPath : newPath + activePath.slice(oldPath.length);
  }

  function _explorerClearDocCache(root, path, kind) {
    if (typeof _workspaceDocCache === 'undefined') return;
    const prefix = root + '|';
    for (const key of _workspaceDocCache.keys()) {
      if (!key.startsWith(prefix)) continue;
      const cachedPath = key.slice(prefix.length);
      if (_explorerPathAffected(cachedPath, path, kind)) _workspaceDocCache.delete(key);
    }
  }

  async function _explorerAfterMutation(state, result) {
    const {action, ctx} = state;
    const kind = state.kind || ctx.kind;
    const oldPath = ctx.path;
    const newPath = action === 'rename' ? result.renamed_to : result.entry;
    _explorerClearDocCache(ctx.root, oldPath, ctx.kind);
    if (typeof _workspaceSidebarCache !== 'undefined') _workspaceSidebarCache.delete(ctx.root);

    if (ctx.surface === 'repo' && currentRepo === ctx.root) {
      const previous = workspaceOpenFile;
      const wasAffected = _explorerPathAffected(previous, oldPath, ctx.kind);
      let reopen = previous;
      if (action === 'rename' && wasAffected) reopen = _explorerRenamedActivePath(previous, oldPath, newPath, ctx.kind);
      if (action === 'delete' && wasAffected) reopen = null;
      if (action.startsWith('create') && kind === 'file') reopen = newPath;
      await loadWorkspaceView();
      if (reopen) await openWorkspaceFile(reopen);
      else if (action === 'delete' && wasAffected) {
        workspaceOpenFile = null;
        document.getElementById('content').innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
      }
      return;
    }

    if (!currentWorkspace || !currentWorkspace.path) return;
    const activeFileRoot = _sidebarScopedRoot(currentWorkspace.path);
    if (currentWorkspace.path !== ctx.root && activeFileRoot !== ctx.root) return;
    const previous = _workspaceDocPath;
    const wasAffected = _explorerPathAffected(previous, oldPath, ctx.kind);
    let reopen = previous;
    if (action === 'rename' && wasAffected) reopen = _explorerRenamedActivePath(previous, oldPath, newPath, ctx.kind);
    if (action === 'delete' && wasAffected) reopen = null;
    if (action.startsWith('create') && kind === 'file') reopen = newPath;

    if (document.body.classList.contains('self-active')) await selfPopulateSidebar();
    else if (document.body.classList.contains('vault-active')) await vaultPopulateSidebar();
    else await _refreshWorkspaceSidebar();

    if (reopen && reopen !== previous) await openWorkspaceDoc(reopen, {root: ctx.root});
    else if (action === 'delete' && wasAffected) {
      setLastWorkspaceDoc(ctx.root, null);
      if (document.body.classList.contains('self-active')) selfShowWorkbench();
      else if (document.body.classList.contains('vault-active')) vaultShowOverview();
      else showWorkspaceDashboard();
    }
  }

  function _explorerHistoryShell(title, loadingMessage) {
    const modal = document.getElementById('explorerHistoryModal');
    const files = document.getElementById('explorerHistoryFiles');
    const list = document.getElementById('explorerHistoryList');
    const diff = document.getElementById('explorerHistoryDiff');
    if (!modal || !files || !list || !diff) return null;
    document.getElementById('explorerHistoryTitle').textContent = title;
    files.innerHTML = '<div class="explorer-history-column-title">Changed files</div><div class="explorer-history-empty">Select a revision.</div>';
    list.innerHTML = `<div class="explorer-history-column-title">Revisions</div><div class="explorer-history-empty">${esc(loadingMessage)}</div>`;
    diff.innerHTML = '<div class="explorer-history-empty">Select a revision to view its changes.</div>';
    modal.classList.add('active');
    return {modal, files, list, diff};
  }

  function _explorerHistoryRenderCommits(summary) {
    const state = _explorerHistoryState;
    const list = document.getElementById('explorerHistoryList');
    if (!state || !list) return;
    if (!state.commits.length) {
      list.innerHTML = '<div class="explorer-history-column-title">Revisions</div><div class="explorer-history-empty">No commits found.</div>';
      return;
    }
    list.innerHTML = `<div class="explorer-history-column-title">Revisions</div><div class="explorer-history-summary">${esc(summary)}</div>` + state.commits.map(commit => {
      const workingTree = commit.kind === 'working-tree';
      const branchDiff = commit.kind === 'branch';
      const states = (commit.states || []).join(' + ') || 'uncommitted';
      const title = workingTree
        ? `Working tree · ${states}`
        : (branchDiff ? `${commit.branch || ''} vs ${commit.base_branch || 'base'}` : `${commit.author || ''} · ${commit.date || ''}`);
      const meta = workingTree
        ? `<code>WORKTREE</code><span>${esc(states)}</span><span>·</span><span>not committed</span>`
        : (branchDiff
          ? `<code>BASE</code><span>${esc(commit.base_branch || 'main/master')}</span><span>·</span><span>${commit.file_count || 0} files</span>`
          : `<code>${esc(commit.short_sha || commit.sha.slice(0, 7))}</code><span>${esc(commit.author || '')}</span><span>·</span><span>${esc(commit.relative_date || commit.date || '')}</span>`);
      return `<button class="explorer-history-commit${workingTree ? ' working-tree' : ''}${branchDiff ? ' branch-diff' : ''}" type="button" data-sha="${escAttr(commit.sha)}" title="${escAttr(title)}">
        <span class="eh-message">${esc(commit.message)}</span>
        <span class="eh-meta">${meta}</span>
      </button>`;
    }).join('');
    list.querySelectorAll('.explorer-history-commit').forEach(button => {
      button.addEventListener('click', () => explorerHistorySelect(button.getAttribute('data-sha'), button));
    });
    const first = list.querySelector('.explorer-history-commit');
    if (first) explorerHistorySelect(first.getAttribute('data-sha'), first);
  }

  function explorerHistoryScrollFile(index, button) {
    const target = document.getElementById(`explorer-history-file-${index}`);
    if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
    document.querySelectorAll('#explorerHistoryFiles .explorer-history-file').forEach(row => row.classList.toggle('active', row === button));
  }
  window.explorerHistoryScrollFile = explorerHistoryScrollFile;

  function _explorerHistoryRenderFiles(data, head, emptyMessage) {
    const filesRail = document.getElementById('explorerHistoryFiles');
    const diff = document.getElementById('explorerHistoryDiff');
    if (!filesRail || !diff) return;
    const selectedFile = String(data.selected_file || '');
    const revisionFiles = Array.isArray(data.files) ? [...data.files] : [];
    if (data.notebook && selectedFile && !revisionFiles.some(file => file.filename === selectedFile)) {
      revisionFiles.unshift({filename: selectedFile, status: 'modified', additions: 0, deletions: 0});
    }
    if (!revisionFiles.length) {
      filesRail.innerHTML = '<div class="explorer-history-column-title">Changed files</div><div class="explorer-history-empty">No changed files.</div>';
      diff.innerHTML = head + `<div class="explorer-history-empty">${esc(emptyMessage)}</div>`;
      return;
    }
    filesRail.innerHTML = '<div class="explorer-history-column-title">Changed files</div>' + revisionFiles.map((file, index) => {
      const total = (file.additions || 0) + (file.deletions || 0);
      return `<button class="explorer-history-file${index === 0 ? ' active' : ''}" type="button" onclick="explorerHistoryScrollFile(${index},this)" title="${escAttr(file.filename)}"><span class="eh-file-status ${escAttr(file.status || 'modified')}"></span><span class="eh-file-name">${esc(file.filename)}</span><span class="eh-file-stat">${total}</span></button>`;
    }).join('');
    diff.innerHTML = head + revisionFiles.map((file, index) => {
      const notebookSelected = data.notebook && file.filename === selectedFile;
      const body = notebookSelected ? renderNotebookHistoryDiff(data.notebook) : renderUnified(file);
      return `<section class="file-diff" id="explorer-history-file-${index}">
        <div class="file-header"><span class="badge badge-${escAttr(file.status || 'modified')}">${esc(file.status || 'modified')}</span><span class="filename">${esc(file.filename)}</span><span class="file-stats"><span class="adds">+${file.additions || 0}</span> <span class="dels">-${file.deletions || 0}</span></span></div>
        <div class="file-body">${body}</div>
      </section>`;
    }).join('');
  }

  async function openExplorerHistory(ctx) {
    if (!ctx) return;
    const shell = _explorerHistoryShell(`History · ${ctx.path}`, 'Loading file history…');
    if (!shell) return;
    _explorerHistoryState = {mode: 'entry', ctx, commits: [], revisionCache: {}};
    const requestId = ++_explorerHistoryRequest;
    try {
      const response = await fetch(`/api/workspace-entry/history?path=${encodeURIComponent(ctx.root)}&file=${encodeURIComponent(ctx.path)}&limit=100`);
      if (!response.ok) throw new Error(await _explorerResponseError(response));
      const data = await response.json();
      if (requestId !== _explorerHistoryRequest || !_explorerHistoryState) return;
      const commits = data.commits || [];
      _explorerHistoryState.commits = commits;
      const committedCount = commits.filter(commit => commit.kind !== 'working-tree').length;
      const hasWorkingTree = commits.some(commit => commit.kind === 'working-tree');
      const summary = `${committedCount} commit${committedCount === 1 ? '' : 's'} · newest first${hasWorkingTree ? ' · uncommitted changes included' : ''}`;
      _explorerHistoryRenderCommits(summary);
    } catch (e) {
      if (requestId !== _explorerHistoryRequest) return;
      shell.list.innerHTML = `<div class="explorer-history-column-title">Revisions</div><div class="explorer-history-empty">${esc(e.message || e)}</div>`;
    }
  }
  window.openExplorerHistory = openExplorerHistory;

  async function openRepositoryHistory(ctx) {
    if (!ctx || !ctx.root) return;
    const label = ctx.label || 'main';
    const shell = _explorerHistoryShell(`Git history · ${label}`, 'Loading repository history…');
    if (!shell) return;
    _explorerHistoryState = {mode: 'repository', ctx, commits: [], revisionCache: {}};
    const requestId = ++_explorerHistoryRequest;
    const getJson = async url => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(await _explorerResponseError(response));
      return response.json();
    };
    try {
      const repo = encodeURIComponent(ctx.root);
      const [workingTree, branchDiff, commits] = await Promise.all([
        getJson(`/api/diff?repo=${repo}&type=uncommitted`),
        getJson(`/api/diff?repo=${repo}&type=branch`),
        getJson(`/api/commits?repo=${repo}&count=100`),
      ]);
      if (requestId !== _explorerHistoryRequest || !_explorerHistoryState) return;
      const branch = workingTree.branch || branchDiff.branch || label;
      const base = branchDiff.base_branch || 'main/master';
      const revisions = [
        {sha: 'WORKTREE', kind: 'working-tree', message: 'Uncommitted changes', states: ['working tree'], file_count: (workingTree.files || []).length},
        {sha: 'BRANCH', kind: 'branch', message: `Changes vs ${base}`, branch, base_branch: base, file_count: (branchDiff.files || []).length},
        ...(Array.isArray(commits) ? commits.map(commit => ({...commit, kind: 'commit'})) : []),
      ];
      _explorerHistoryState.commits = revisions;
      _explorerHistoryState.revisionCache = {WORKTREE: workingTree, BRANCH: branchDiff};
      _explorerHistoryRenderCommits(`${branch} · working tree, base comparison, and ${Math.max(0, revisions.length - 2)} commits`);
    } catch (e) {
      if (requestId !== _explorerHistoryRequest) return;
      shell.list.innerHTML = `<div class="explorer-history-column-title">Revisions</div><div class="explorer-history-empty">${esc(e.message || e)}</div>`;
    }
  }
  window.openRepositoryHistory = openRepositoryHistory;

  async function explorerHistorySelect(sha, button) {
    const state = _explorerHistoryState;
    const diff = document.getElementById('explorerHistoryDiff');
    const filesRail = document.getElementById('explorerHistoryFiles');
    if (!state || !diff || !filesRail || !sha) return;
    const requestId = ++_explorerHistoryRequest;
    document.querySelectorAll('#explorerHistoryList .explorer-history-commit').forEach(el => el.classList.toggle('active', el === button));
    const selected = state.commits.find(item => item.sha === sha) || {};
    const isWorkingTree = selected.kind === 'working-tree';
    const isBranchDiff = selected.kind === 'branch';
    filesRail.innerHTML = '<div class="explorer-history-column-title">Changed files</div><div class="explorer-history-empty">Loading files…</div>';
    diff.innerHTML = `<div class="explorer-history-empty">Loading ${isWorkingTree ? 'uncommitted changes' : (isBranchDiff ? 'base comparison' : 'commit diff')}…</div>`;
    try {
      let data = state.revisionCache[sha];
      if (!data) {
        if (state.mode === 'repository') {
          const response = await fetch(`/api/commit-diff?repo=${encodeURIComponent(state.ctx.root)}&sha=${encodeURIComponent(sha)}`);
          if (!response.ok) throw new Error(await _explorerResponseError(response));
          data = await response.json();
        } else {
          const ctx = state.ctx;
          const response = await fetch(`/api/workspace-entry/history-diff?path=${encodeURIComponent(ctx.root)}&file=${encodeURIComponent(ctx.path)}&sha=${encodeURIComponent(sha)}`);
          if (!response.ok) throw new Error(await _explorerResponseError(response));
          data = await response.json();
        }
        state.revisionCache[sha] = data;
      }
      if (requestId !== _explorerHistoryRequest || !_explorerHistoryState) return;
      if (data.notebook) {
        await Promise.all([
          ensureMarked().catch(() => {}),
          ensureHighlight().catch(() => {}),
        ]);
        if (requestId !== _explorerHistoryRequest || !_explorerHistoryState) return;
      }
      const details = isWorkingTree
        ? `Working tree · ${esc((data.states || selected.states || []).join(' + ') || 'uncommitted')} · not committed`
        : (isBranchDiff
          ? `${esc(selected.branch || data.branch || '')} vs ${esc(selected.base_branch || data.base_branch || 'main/master')}`
          : `${esc(selected.author || '')} · ${esc(selected.date || '')} · ${esc(sha.slice(0, 12))}`);
      const headClass = isWorkingTree ? ' working-tree' : (isBranchDiff ? ' branch-diff' : '');
      const head = `<div class="explorer-history-head${headClass}"><strong>${esc(selected.message || sha)}</strong><span>${details}</span></div>`;
      const emptyMessage = isWorkingTree
        ? 'No uncommitted changes remain.'
        : (isBranchDiff ? 'No changes from the base branch.' : 'No patch in this commit.');
      _explorerHistoryRenderFiles(data, head, emptyMessage);
    } catch (e) {
      if (requestId !== _explorerHistoryRequest) return;
      diff.innerHTML = `<div class="explorer-history-empty">${esc(e.message || e)}</div>`;
    }
  }
  window.explorerHistorySelect = explorerHistorySelect;

  function closeExplorerHistory() {
    const modal = document.getElementById('explorerHistoryModal');
    if (modal) modal.classList.remove('active');
    _explorerHistoryState = null;
    _explorerHistoryRequest += 1;
  }
  window.closeExplorerHistory = closeExplorerHistory;

  document.addEventListener('contextmenu', (event) => {
    const row = event.target.closest('[data-entry-kind][data-entry-path]');
    if (row) openExplorerContextMenu(event, row);
  });
  document.addEventListener('click', (event) => {
    const menu = document.getElementById('explorerContextMenu');
    if (!menu || !menu.classList.contains('open')) return;
    const button = event.target.closest('[data-explorer-action]');
    if (button && menu.contains(button)) {
      event.preventDefault();
      _explorerMenuAction(button.getAttribute('data-explorer-action'));
    } else if (!menu.contains(event.target)) {
      closeExplorerContextMenu();
    }
  });
  document.addEventListener('keydown', (event) => {
    const menu = document.getElementById('explorerContextMenu');
    if (menu && menu.classList.contains('open')) {
      const buttons = Array.from(menu.querySelectorAll('button'));
      const index = buttons.indexOf(document.activeElement);
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        const delta = event.key === 'ArrowDown' ? 1 : -1;
        buttons[(index + delta + buttons.length) % buttons.length].focus();
      } else if (event.key === 'Home' || event.key === 'End') {
        event.preventDefault();
        buttons[event.key === 'Home' ? 0 : buttons.length - 1].focus();
      }
    }
    if (event.key === 'Escape') {
      if (menu && menu.classList.contains('open')) closeExplorerContextMenu();
      else if (document.getElementById('explorerEntryModal')?.classList.contains('active')) closeExplorerEntryDialog();
      else if (document.getElementById('explorerDeleteModal')?.classList.contains('active')) closeExplorerDeleteDialog();
      else if (document.getElementById('explorerHistoryModal')?.classList.contains('active')) closeExplorerHistory();
    }
  });
  window.addEventListener('resize', closeExplorerContextMenu);
  document.addEventListener('scroll', closeExplorerContextMenu, true);

  // ─── Persistent sidebar-tree folder state ───────────────────────────────
  // Each tree (self / per-workspace / shared-claude / cerebro) is a scope.
  // Within a scope, folder paths map to true=open, false=closed. Absence of
  // a path means "use the renderer's default" (e.g. AUTO_OPEN_FOLDERS) so a
  // first visit still gets the sensible expanded set. Once the user toggles
  // a folder, its choice sticks across page reloads.
  const TREE_EXPANDED_KEY = 'labTreeExpanded';
  function _treeReadAll() {
    try {
      const raw = localStorage.getItem(TREE_EXPANDED_KEY);
      return raw ? (JSON.parse(raw) || {}) : {};
    } catch { return {}; }
  }
  function _treeWriteAll(map) {
    try { localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify(map)); } catch {}
  }
  function _treeIsOpen(scope, folderPath, fallback) {
    if (!scope || !folderPath) return !!fallback;
    const scopeMap = _treeReadAll()[scope];
    if (scopeMap && Object.prototype.hasOwnProperty.call(scopeMap, folderPath)) {
      return !!scopeMap[folderPath];
    }
    return !!fallback;
  }
  function _treeSetOpen(scope, folderPath, isOpen) {
    if (!scope || !folderPath) return;
    const root = _treeReadAll();
    const scopeMap = root[scope] || {};
    scopeMap[folderPath] = !!isOpen;
    root[scope] = scopeMap;
    _treeWriteAll(root);
  }
  // Loads the "open paths" set for trees (cerebro) that drive their own
  // render off an in-memory Set rather than DOM .open class flipping.
  function _treeLoadOpenSet(scope) {
    const out = new Set();
    const scopeMap = _treeReadAll()[scope] || {};
    for (const k of Object.keys(scopeMap)) if (scopeMap[k]) out.add(k);
    return out;
  }
  // Inline-onclick toggle: read scope/path/target id from data-* attrs,
  // flip the children container's .open class, mirror the arrow, persist.
  function _treeToggleFolder(btn) {
    const scope = btn.getAttribute('data-tree-scope');
    const path = btn.getAttribute('data-tree-path');
    const targetId = btn.getAttribute('data-tree-target');
    const children = targetId ? document.getElementById(targetId) : null;
    if (!children) return;
    const isOpen = children.classList.toggle('open');
    const arrow = btn.querySelector('.folder-arrow');
    if (arrow) arrow.classList.toggle('open', isOpen);
    if (scope && path) _treeSetOpen(scope, path, isOpen);
  }

  function applyIframeDarkMode(iframe) {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      // Trackpad pinch events are dispatched inside an iframe rather than to
      // the Lab document. Forward same-origin iframe gestures to Focus mode's
      // page zoom handler so pinching works over rendered HTML and proxied
      // apps too. Cross-origin/direct iframes are intentionally best-effort.
      _wireFocusZoomDocument(doc);
      const isDark = !document.body.classList.contains('light-mode');
      // Remove any previously injected style
      const existing = doc.getElementById('gdiff-theme');
      if (existing) existing.remove();

      if (!isDark) return;
      // If the iframe already has its own non-default background (e.g. a
      // report that ships its own dark theme), trust it. Overriding to
      // transparent only exposes the iframe element's CSS background and
      // makes the report look worse — sometimes a stark white pane.
      if (doc.body) {
        const bg = window.getComputedStyle(doc.body).backgroundColor;
        if (bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
          return;
        }
      }
      const style = doc.createElement('style');
      style.id = 'gdiff-theme';
      style.textContent = `
        html, body { background: transparent !important; color: #c9d1d9 !important; }
        h1, h2, h3, h4, h5, h6 { color: #e6edf3 !important; }
        p, span, li, td, div, label { color: #c9d1d9 !important; }
        th { color: #e6edf3 !important; background-color: #21262d !important; }
        table, th, td { border-color: #30363d !important; }
        .metric-block { border-color: #30363d !important; background: #161b22 !important; }
        .report-section h2 { border-bottom-color: #30363d !important; }
        .sev-none { background: #30363d !important; color: #c9d1d9 !important; }
        .sev-nq { background: #5a3e00 !important; color: #e6edf3 !important; }
        hr { border-color: #30363d !important; }
        code { background: #161b22 !important; color: #c9d1d9 !important; }
        a { color: #58a6ff !important; }
      `;
      doc.head.appendChild(style);
    } catch(e) {}
  }

  function hlLine(content, lang) {
    if (!lang || typeof hljs === 'undefined') return esc(content);
    try {
      return hljs.highlight(content, { language: lang, ignoreIllegals: true }).value;
    } catch (e) { return esc(content); }
  }

  function filenameLang(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    const map = { py:'python', js:'javascript', ts:'typescript', jsx:'javascript', tsx:'typescript', sh:'bash', yml:'yaml', yaml:'yaml', json:'json', html:'xml', xml:'xml', css:'css', sql:'sql', java:'java', go:'go', rs:'rust', rb:'ruby', kt:'kotlin', swift:'swift', c:'c', cpp:'cpp', h:'c', hpp:'cpp', scala:'scala', r:'r' };
    return map[ext] || null;
  }

  // Word-level diff: returns [delHtml, addHtml] with <span class="wdel/wadd"> around changed parts
  function wordDiff(oldStr, newStr) {
    const oldToks = tokenize(oldStr), newToks = tokenize(newStr);
    const dp = lcs(oldToks, newToks);
    let delH = '', addH = '', oi = 0, ni = 0, di = 0;
    while (oi < oldToks.length || ni < newToks.length) {
      if (di < dp.length && oi < oldToks.length && ni < newToks.length && oldToks[oi] === dp[di] && newToks[ni] === dp[di]) {
        delH += esc(oldToks[oi]); addH += esc(newToks[ni]); oi++; ni++; di++;
      } else {
        let dBuf = '', aBuf = '';
        while (oi < oldToks.length && (di >= dp.length || oldToks[oi] !== dp[di])) { dBuf += oldToks[oi++]; }
        while (ni < newToks.length && (di >= dp.length || newToks[ni] !== dp[di])) { aBuf += newToks[ni++]; }
        if (dBuf) delH += `<span class="wdel">${esc(dBuf)}</span>`;
        if (aBuf) addH += `<span class="wadd">${esc(aBuf)}</span>`;
      }
    }
    return [delH, addH];
  }

  function tokenize(s) {
    // Split into words and whitespace tokens
    return s.match(/\S+|\s+/g) || [];
  }

  function lcs(a, b) {
    const m = a.length, n = b.length;
    const dp = Array.from({length: m+1}, () => new Array(n+1).fill(0));
    for (let i = 1; i <= m; i++)
      for (let j = 1; j <= n; j++)
        dp[i][j] = a[i-1] === b[j-1] ? dp[i-1][j-1]+1 : Math.max(dp[i-1][j], dp[i][j-1]);
    const res = []; let i = m, j = n;
    while (i > 0 && j > 0) {
      if (a[i-1] === b[j-1]) { res.unshift(a[i-1]); i--; j--; }
      else if (dp[i-1][j] > dp[i][j-1]) i--;
      else j--;
    }
    return res;
  }

  function toggleFile(i) {
    document.getElementById(`fb-${i}`).classList.toggle('collapsed');
    document.getElementById(`chev-${i}`).classList.toggle('collapsed');
  }

  function switchDiffTab(tab) {
    currentDiffTab = tab;
    document.getElementById('tabUncommitted').classList.toggle('active', tab === 'uncommitted');
    document.getElementById('tabBranch').classList.toggle('active', tab === 'branch');
    document.getElementById('tabWorkspace').classList.toggle('active', tab === 'workspace');
    // Update commit tab active states
    document.querySelectorAll('.commit-tab').forEach(el => el.classList.remove('active'));
    if (tab.startsWith('commit:')) {
      const sha = tab.split(':')[1];
      document.querySelectorAll('.commit-tab').forEach(el => {
        if (el.getAttribute('onclick')?.includes(sha)) el.classList.add('active');
      });
    }
    if (tab === 'workspace') {
      loadWorkspaceView();
    } else if (tab.startsWith('commit:')) {
      const sha = tab.split(':')[1];
      diffCache[tab] ? renderDiff(diffCache[tab]) : loadCommitDiff(sha);
    } else {
      diffCache[tab] ? renderDiff(diffCache[tab]) : loadDiff();
    }
  }

  function setView(mode) {
    viewMode = mode;
    document.getElementById('btnUnified').classList.toggle('active', mode === 'unified');
    document.getElementById('btnSplit').classList.toggle('active', mode === 'split');
    if (diffCache[currentDiffTab]) renderDiff(diffCache[currentDiffTab]);
  }

  async function refreshDiff() {
    if (!currentRepo) return;
    if (currentDiffTab === 'workspace' || currentDiffTab.startsWith('commit:')) return;
    try {
      const res = await fetch(`/api/diff?repo=${encodeURIComponent(currentRepo)}&type=${currentDiffTab}`);
      const data = await res.json();
      const prev = diffCache[currentDiffTab];
      if (!prev || JSON.stringify(prev.files) !== JSON.stringify(data.files)) {
        diffCache[currentDiffTab] = data;
        document.getElementById('branchLabel').textContent = data.branch;
        renderDiff(data);
      }
    } catch (err) {}
  }

  // ─── File operations ───
  let modalMode = null;
  let deleteTarget = null;

  function createEditor(container, content, readOnly) {
    const ta = document.createElement('textarea');
    ta.id = 'modalTextarea';
    ta.value = content;
    ta.readOnly = !!readOnly;
    ta.spellcheck = false;
    ta.style.cssText = 'width:100%;height:100%;background:#0d1117;color:#e6edf3;border:none;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:20px;resize:none;outline:none;tab-size:4;';
    ta.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        e.preventDefault();
        const s = this.selectionStart, end = this.selectionEnd;
        this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = s + 4;
      }
    });
    container.appendChild(ta);
  }

  function getHljsLang(filename) {
    const ext = (filename || '').split('.').pop().toLowerCase();
    const map = { py: 'python', js: 'javascript', ts: 'typescript', jsx: 'javascript', tsx: 'typescript', sh: 'bash', bash: 'bash', yml: 'yaml', yaml: 'yaml', json: 'json', html: 'xml', xml: 'xml', css: 'css', sql: 'sql', java: 'java', go: 'go', rs: 'rust', rb: 'ruby', md: 'markdown' };
    return map[ext] || null;
  }

  function getChangedLines(filepath) {
    const tab = currentDiffTab === 'workspace' ? 'branch' : currentDiffTab;
    const data = diffCache[tab];
    if (!data) return { added: new Set(), lineToHunk: {} };
    const file = data.files.find(f => f.filename === filepath);
    if (!file) return { added: new Set(), lineToHunk: {} };
    const added = new Set();
    const lineToHunk = {}; // maps new_num -> hunk index
    file.hunks.forEach((h, hi) => {
      for (const l of h.lines) {
        if (l.type === 'add' && l.new_num) {
          added.add(l.new_num);
          lineToHunk[l.new_num] = hi;
        }
      }
    });
    return { added, lineToHunk, hunks: file.hunks };
  }

  // Modal state
  let _modalFileContent = '';
  let _modalFilepath = '';

  function setModalFooter(mode) {
    const footer = document.getElementById('modalFooter');
    const fn = _modalFilepath.replace(/'/g, "\\'");
    if (mode === 'view') {
      footer.innerHTML = `<button class="btn-cancel" onclick="closeModal()">Close</button>
        <button class="btn-edit" onclick="switchModalToEdit()">Edit</button>`;
    } else if (mode === 'edit') {
      footer.innerHTML = `<button class="btn-delete" onclick="switchModalToDelete()">Delete</button>
        <button class="btn-cancel" onclick="switchModalToView()">Cancel</button>
        <button class="btn-save" onclick="saveModal()">Save</button>`;
    } else if (mode === 'create') {
      footer.innerHTML = `<button class="btn-cancel" onclick="closeModal()">Cancel</button>
        <button class="btn-save" onclick="saveModal()">Create</button>`;
    }
  }

  async function openViewModal(filepath) {
    modalMode = 'view';
    _modalFilepath = filepath;
    document.getElementById('modalTitle').textContent = 'View File';
    const pathInput = document.getElementById('modalPath');
    pathInput.value = filepath;
    pathInput.readOnly = true;

    const container = document.getElementById('modalEditorContainer');
    container.innerHTML = '<div style="padding:24px;color:#8b949e">Loading...</div>';
    document.getElementById('editorModal').classList.add('active');
    setModalFooter(isNotebook(filepath) ? 'view' : 'view');  // no edit for notebooks yet

    if (isNotebook(filepath)) {
      try {
        const res = await fetch(`/api/notebook?repo=${encodeURIComponent(_activeRepoFileRoot())}&path=${encodeURIComponent(filepath)}`);
        const cells = await res.json();
        await Promise.all([
          ensureMarked().catch(() => {}),
          ensureHighlight().catch(() => {}),
        ]);
        container.innerHTML = `<div class="code-scroll"><div class="nb-container" style="padding:12px">${cells.map(c => renderNotebookCell(c, null)).join('')}</div></div>`;
        // Hide edit for notebooks
        setModalFooter('view');
      } catch (err) {
        container.innerHTML = `<div style="padding:24px;color:#f85149">Error: ${err.message}</div>`;
      }
      return;
    }

    setModalFooter('view');

    try {
      const res = await fetch(`/api/file?repo=${encodeURIComponent(_activeRepoFileRoot())}&path=${encodeURIComponent(filepath)}`);
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      _modalFileContent = data.content;
      container.innerHTML = '';

      const { added, lineToHunk, hunks } = getChangedLines(filepath);
      window._viewHunks = hunks || [];
      window._viewLineToHunk = lineToHunk || {};
      window._viewLang = getHljsLang(filepath);

      const lines = data.content.split('\n');
      const lang = window._viewLang;

      const rows = lines.map((line, i) => {
        const n = i + 1;
        const isChanged = added.has(n);
        const cls = isChanged ? ' class="vchanged"' : '';
        const hunkIdx = isChanged ? lineToHunk[n] : undefined;
        const hoverAttr = hunkIdx !== undefined ? ` onmouseenter="showDiffPopover(event,${hunkIdx})" onmouseleave="hideDiffPopover()"` : '';
        const hl = lang ? hlLine(line, lang) : esc(line);
        return `<tr${cls}><td class="vln"${hoverAttr}>${n}</td><td class="vgutter"></td><td class="vcode">${hl}</td></tr>`;
      }).join('');

      container.innerHTML = `<div class="code-scroll"><table class="view-table">${rows}</table></div>`;
    } catch (err) {
      container.innerHTML = `<div style="padding:24px;color:#f85149">Error: ${err.message}</div>`;
    }
  }

  function switchModalToEdit() {
    modalMode = 'edit';
    document.getElementById('modalTitle').textContent = 'Edit File';
    setModalFooter('edit');
    const container = document.getElementById('modalEditorContainer');
    container.innerHTML = '';
    createEditor(container, _modalFileContent, false);
  }

  function switchModalToView() {
    openViewModal(_modalFilepath);
  }

  function switchModalToDelete() {
    deleteTarget = _modalFilepath;
    document.getElementById('deleteFilename').textContent = _modalFilepath;
    document.getElementById('deleteModal').classList.add('active');
  }

  function openCreateModal() {
    modalMode = 'create';
    _modalFilepath = '';
    _modalFileContent = '';
    document.getElementById('modalTitle').textContent = 'Create File';
    const pathInput = document.getElementById('modalPath');
    pathInput.value = '';
    pathInput.readOnly = false;

    const container = document.getElementById('modalEditorContainer');
    container.innerHTML = '';
    document.getElementById('editorModal').classList.add('active');
    setModalFooter('create');
    createEditor(container, '', false);
    setTimeout(() => pathInput.focus(), 100);
  }

  function closeModal() {
    document.getElementById('editorModal').classList.remove('active');
    document.getElementById('modalEditorContainer').innerHTML = '';
  }

  async function saveModal() {
    const ta = document.getElementById('modalTextarea');
    if (!ta) { alert('Editor not ready'); return; }
    if (!currentRepo) { alert('No repo selected'); return; }
    const filepath = document.getElementById('modalPath').value.trim();
    if (!filepath) { alert('Enter a file path'); return; }
    const content = ta.value;
    const method = modalMode === 'create' ? 'POST' : 'PUT';

    try {
      const res = await fetch('/api/file', {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: _activeRepoFileRoot(), path: filepath, content }),
      });
      const result = await res.json();
      if (!res.ok) { alert(result.detail || 'Error saving file'); return; }
      _modalFileContent = content;
      _modalFilepath = filepath;
      closeModal();
      diffCache = { uncommitted: null, branch: null };
      if (currentDiffTab === 'workspace') loadWorkspaceView();
      else loadDiff();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  }

  function closeDeleteModal() {
    document.getElementById('deleteModal').classList.remove('active');
    deleteTarget = null;
  }

  async function confirmDelete() {
    if (!deleteTarget || !currentRepo) return;
    try {
      const res = await fetch(`/api/file?repo=${encodeURIComponent(_activeRepoFileRoot())}&path=${encodeURIComponent(deleteTarget)}`, { method: 'DELETE' });
      if (!res.ok) { const err = await res.json(); alert(err.detail || 'Error deleting file'); return; }
      closeDeleteModal();
      closeModal();
      diffCache = { uncommitted: null, branch: null };
      if (currentDiffTab === 'workspace') loadWorkspaceView();
      else loadDiff();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  }

  // ─── Workspace tab ───
  let fileTree = null;
  let workspaceOpenFile = null;
  let workspaceEditMode = false;
  let _repoFileRoot = null;
  function _activeRepoFileRoot() { return _repoFileRoot || currentRepo; }
  let showDotFiles = false;
  const SIDEBAR_FILE_CONFIG_LEGACY_KEY = 'labSidebarFileConfig-v1';
  const SIDEBAR_FILE_CONFIG_KEY_PREFIX = 'labSidebarFileConfig-v2:';
  const SIDEBAR_FILE_CONFIG_MIGRATION_KEY = 'labSidebarFileConfig-v1-migrated';
  const SIDEBAR_RECENT_MINUTE_OPTIONS = Object.freeze([15, 60, 120, 360, 1440]);
  const SIDEBAR_RECENT_MAX_MINUTES = 1440;
  const SIDEBAR_RECENT_GIT_MODES = Object.freeze([
    'uncommitted', 'origin-main', 'last-2-commits',
  ]);
  const SIDEBAR_SORT_MODES = Object.freeze(['updated', 'name', 'type']);
  const SIDEBAR_WORKTREE_DEFAULT_COLOR = '#6e7681';
  const SIDEBAR_FILE_CONFIG_DEFAULTS = Object.freeze({
    showHidden: false,
    showRecent: true,
    recentMode: 'mtime',
    recentMinutes: 1440,
    recentSort: 'updated',
    filesSort: 'name',
    trackMode: 'all',
    extensions: [],
    folderScopes: [],
    rootScopeColors: {},
    rootWorktreeFolders: {},
    selectedFolders: {},
    worktreeFolder: '',
    worktreeColors: {},
    selectedWorktrees: {},
  });
  let _sidebarAvailableExtensions = new Set();
  let _sidebarRecentDiagnosticsPending = null;
  let _sidebarWorktreeFolders = [];
  let _sidebarWorktreeFolderResolved = '';
  let _sidebarWorktreeDiscoveryKey = '';
  let _sidebarWorktreeDiscoveryPromise = null;
  let _sidebarWorktreeDiscoveryPromiseKey = '';
  let _sidebarWorktreeDiscoveryGeneration = 0;

  function _sidebarClearWorktreeDiscovery() {
    _sidebarWorktreeFolders = [];
    _sidebarWorktreeFolderResolved = '';
    _sidebarWorktreeDiscoveryKey = '';
    _sidebarWorktreeDiscoveryPromise = null;
    _sidebarWorktreeDiscoveryPromiseKey = '';
    _sidebarWorktreeDiscoveryGeneration += 1;
  }

  function _sidebarValidColor(value) {
    return /^#[0-9a-f]{6}$/i.test(String(value || ''))
      ? String(value).toLowerCase()
      : SIDEBAR_WORKTREE_DEFAULT_COLOR;
  }

  function _sidebarStringMap(value, {colors = false} = {}) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value)
      .filter(([key, item]) => key && typeof item === 'string' && item)
      .map(([key, item]) => [String(key), colors ? _sidebarValidColor(item) : String(item)]));
  }

  function _sidebarNormalizeFolderPath(value, baseRoot = '') {
    const requested = String(value || '').trim();
    if (!requested) return '';
    const combined = requested.startsWith('/')
      ? requested
      : `${String(baseRoot || '').replace(/\/$/, '')}/${requested}`;
    const parts = [];
    combined.split('/').forEach(part => {
      if (!part || part === '.') return;
      if (part === '..') {
        if (parts.length) parts.pop();
        return;
      }
      parts.push(part);
    });
    return '/' + parts.join('/');
  }

  function _sidebarNormalizeWorktreeFolder(value, workspaceRoot = '') {
    const requested = String(value || '').trim();
    return requested.startsWith('~/')
      ? requested
      : _sidebarNormalizeFolderPath(requested, workspaceRoot);
  }

  function _sidebarFolderScopeList(value) {
    if (!Array.isArray(value)) return [];
    const seen = new Set();
    return value.flatMap(row => {
      if (!row || typeof row !== 'object') return [];
      const path = _sidebarNormalizeFolderPath(row.path);
      if (!path || seen.has(path)) return [];
      seen.add(path);
      const fallback = path.split('/').filter(Boolean).pop() || path;
      return [{
        path,
        label: String(row.label || fallback).trim() || fallback,
        color: _sidebarValidColor(row.color),
        worktreeFolder: String(row.worktreeFolder || '').trim(),
      }];
    });
  }

  function _sidebarDefaultFileConfig() {
    return {
      ...SIDEBAR_FILE_CONFIG_DEFAULTS,
      extensions: [],
      folderScopes: [],
      rootScopeColors: {},
      rootWorktreeFolders: {},
      selectedFolders: {},
      worktreeColors: {},
      selectedWorktrees: {},
    };
  }

  function _sidebarNormalizeRecentMinutes(value) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return SIDEBAR_FILE_CONFIG_DEFAULTS.recentMinutes;
    }
    const capped = Math.min(numeric, SIDEBAR_RECENT_MAX_MINUTES);
    return SIDEBAR_RECENT_MINUTE_OPTIONS.includes(capped)
      ? capped
      : SIDEBAR_FILE_CONFIG_DEFAULTS.recentMinutes;
  }

  function _sidebarNormalizeSortMode(value, fallback) {
    const requested = String(value || '');
    return SIDEBAR_SORT_MODES.includes(requested) ? requested : fallback;
  }

  function _sidebarCurrentSortMode(section) {
    const isRecent = section === 'recent';
    return _sidebarNormalizeSortMode(
      isRecent ? _sidebarFileConfig.recentSort : _sidebarFileConfig.filesSort,
      isRecent ? SIDEBAR_FILE_CONFIG_DEFAULTS.recentSort : SIDEBAR_FILE_CONFIG_DEFAULTS.filesSort,
    );
  }

  function _sidebarNormalizeFileConfig(stored) {
    const recentMinutes = _sidebarNormalizeRecentMinutes(stored && stored.recentMinutes);
    const storedMode = String(stored && stored.recentMode || '');
    const recentMode = storedMode === 'none'
      || storedMode === 'mtime'
      || SIDEBAR_RECENT_GIT_MODES.includes(storedMode)
      ? storedMode
      : (stored && stored.showRecent === false ? 'none' : 'mtime');
    return {
      showHidden: !!(stored && stored.showHidden === true),
      showRecent: recentMode !== 'none',
      recentMode,
      recentMinutes,
      recentSort: _sidebarNormalizeSortMode(stored && stored.recentSort, SIDEBAR_FILE_CONFIG_DEFAULTS.recentSort),
      filesSort: _sidebarNormalizeSortMode(stored && stored.filesSort, SIDEBAR_FILE_CONFIG_DEFAULTS.filesSort),
      trackMode: stored && stored.trackMode === 'extensions' ? 'extensions' : 'all',
      extensions: stored && Array.isArray(stored.extensions)
        ? [...new Set(stored.extensions.map(value => String(value).toLowerCase()))]
        : [],
      folderScopes: _sidebarFolderScopeList(stored && stored.folderScopes),
      rootScopeColors: _sidebarStringMap(stored && stored.rootScopeColors, {colors: true}),
      rootWorktreeFolders: _sidebarStringMap(stored && stored.rootWorktreeFolders),
      selectedFolders: _sidebarStringMap(stored && stored.selectedFolders),
      // Kept as a read-only fallback so browser state from the original
      // single-worktree-folder implementation migrates without losing it.
      worktreeFolder: stored && typeof stored.worktreeFolder === 'string'
        ? stored.worktreeFolder.trim() : '',
      worktreeColors: _sidebarStringMap(stored && stored.worktreeColors, {colors: true}),
      selectedWorktrees: _sidebarStringMap(stored && stored.selectedWorktrees),
    };
  }

  function _sidebarFileConfigScopeKey() {
    const workspace = typeof currentWorkspace !== 'undefined' ? currentWorkspace : null;
    const workspacePath = _sidebarNormalizeFolderPath(workspace && workspace.path);
    return workspacePath ? encodeURIComponent(workspacePath) : '';
  }

  function _sidebarFileConfigStorageKey(scopeKey) {
    return scopeKey ? SIDEBAR_FILE_CONFIG_KEY_PREFIX + scopeKey : '';
  }

  function _sidebarCanMigrateLegacyFileConfig() {
    const workspace = typeof currentWorkspace !== 'undefined' ? currentWorkspace : null;
    const name = String(workspace && workspace.name || '');
    return !!workspace && name !== '__self__' && name !== '__vault__';
  }

  function _loadSidebarFileConfig(scopeKey = _sidebarFileConfigScopeKey()) {
    if (!scopeKey) return _sidebarDefaultFileConfig();
    try {
      const storageKey = _sidebarFileConfigStorageKey(scopeKey);
      let raw = localStorage.getItem(storageKey);
      // The old setting was browser-global. Preserve it once by assigning it
      // to the first workspace opened after this upgrade; every other workspace
      // starts from defaults instead of inheriting those folders.
      if (raw === null && _sidebarCanMigrateLegacyFileConfig()
          && !localStorage.getItem(SIDEBAR_FILE_CONFIG_MIGRATION_KEY)) {
        const legacy = localStorage.getItem(SIDEBAR_FILE_CONFIG_LEGACY_KEY);
        if (legacy !== null) {
          raw = legacy;
          localStorage.setItem(storageKey, legacy);
          localStorage.setItem(SIDEBAR_FILE_CONFIG_MIGRATION_KEY, scopeKey);
        }
      }
      return _sidebarNormalizeFileConfig(JSON.parse(raw || '{}'));
    } catch {
      return _sidebarDefaultFileConfig();
    }
  }

  let _sidebarFileConfigScope = _sidebarFileConfigScopeKey();
  let _sidebarFileConfig = _loadSidebarFileConfig(_sidebarFileConfigScope);
  showDotFiles = _sidebarFileConfig.showHidden;
  let showWorkspaceDotFiles = _sidebarFileConfig.showHidden;

  function _storeSidebarFileConfig() {
    const storageKey = _sidebarFileConfigStorageKey(_sidebarFileConfigScope);
    if (!storageKey) return;
    try { localStorage.setItem(storageKey, JSON.stringify(_sidebarFileConfig)); } catch {}
  }

  function _sidebarActivateFileConfig() {
    const scopeKey = _sidebarFileConfigScopeKey();
    if (scopeKey === _sidebarFileConfigScope) return false;
    _sidebarFileConfigScope = scopeKey;
    _sidebarFileConfig = _loadSidebarFileConfig(scopeKey);
    showDotFiles = _sidebarFileConfig.showHidden;
    showWorkspaceDotFiles = _sidebarFileConfig.showHidden;
    _sidebarAvailableExtensions = new Set();
    _sidebarRecentDiagnosticsPending = null;
    _sidebarClearWorktreeDiscovery();
    return true;
  }

  function _sidebarWorktreeBaseRoot() {
    if (currentRepo) return currentRepo;
    if (document.body && document.body.classList.contains('self-active')) return SELF_REPO_PATH;
    if (currentWorkspace && currentWorkspace.path) return currentWorkspace.path;
    return '';
  }

  function _sidebarFolderScope(path) {
    const requested = String(path || '');
    return (_sidebarFileConfig.folderScopes || []).find(row => row.path === requested) || null;
  }

  function _sidebarSelectedFolder(baseRoot) {
    const selected = String((_sidebarFileConfig.selectedFolders || {})[baseRoot] || '');
    return selected ? _sidebarFolderScope(selected) : null;
  }

  function _sidebarWorkspaceRoot(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    return selected ? selected.path : baseRoot;
  }

  function _sidebarWorkspaceLabel(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    return selected ? selected.label : 'Root';
  }

  function _sidebarWorkspaceColor(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    return selected
      ? _sidebarValidColor(selected.color)
      : _sidebarValidColor((_sidebarFileConfig.rootScopeColors || {})[baseRoot]);
  }

  function _sidebarActiveWorktreeFolder(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    if (selected) return String(selected.worktreeFolder || '').trim();
    return String(
      (_sidebarFileConfig.rootWorktreeFolders || {})[baseRoot]
      || _sidebarFileConfig.worktreeFolder
      || ''
    ).trim();
  }

  function _sidebarWorktreeRepositoryRoot(baseRoot) {
    const scopeRoot = String(baseRoot || '').trim();
    if (!scopeRoot) return '';
    if (currentRepo && String(currentRepo) === scopeRoot) return scopeRoot;
    if (currentWorkspace && String(currentWorkspace.path || '') === scopeRoot) {
      const registered = Array.isArray(currentWorkspace.repos)
        ? currentWorkspace.repos.find(row => row && row.path)
        : null;
      if (registered) return String(registered.path);
    }
    return scopeRoot;
  }

  async function _sidebarDiscoverWorktrees(folder, {
    force = false,
    baseRoot = _sidebarWorktreeBaseRoot(),
  } = {}) {
    const requested = String(folder || '').trim();
    const scopeRoot = String(baseRoot || '').trim();
    const repositoryRoot = _sidebarWorktreeRepositoryRoot(scopeRoot);
    if (!requested || !scopeRoot || !repositoryRoot) {
      _sidebarClearWorktreeDiscovery();
      return [];
    }
    const discoveryKey = `${requested}\n${scopeRoot}\n${repositoryRoot}`;
    if (!force && discoveryKey === _sidebarWorktreeDiscoveryKey) {
      return _sidebarWorktreeFolders;
    }
    if (!force && _sidebarWorktreeDiscoveryPromise && _sidebarWorktreeDiscoveryPromiseKey === discoveryKey) {
      return _sidebarWorktreeDiscoveryPromise;
    }
    const generation = ++_sidebarWorktreeDiscoveryGeneration;
    const promise = (async () => {
      const response = await fetch(`/api/sidebar-worktrees?path=${encodeURIComponent(requested)}&repo=${encodeURIComponent(repositoryRoot)}&scope=${encodeURIComponent(scopeRoot)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not scan worktree folder');
      const resolvedFolder = String(data.path || requested);
      const folders = Array.isArray(data.folders)
        ? data.folders.filter(row => row && row.name && row.path).map(row => ({
            name: String(row.name),
            path: String(row.path),
            repo: String(row.repo || row.path),
          }))
        : [];
      if (generation === _sidebarWorktreeDiscoveryGeneration) {
        _sidebarWorktreeFolderResolved = resolvedFolder;
        _sidebarWorktreeDiscoveryKey = `${resolvedFolder}\n${scopeRoot}\n${repositoryRoot}`;
        _sidebarWorktreeFolders = folders;
      }
      return folders;
    })();
    _sidebarWorktreeDiscoveryPromise = promise;
    _sidebarWorktreeDiscoveryPromiseKey = discoveryKey;
    try {
      return await promise;
    } finally {
      if (_sidebarWorktreeDiscoveryPromise === promise) {
        _sidebarWorktreeDiscoveryPromise = null;
        _sidebarWorktreeDiscoveryPromiseKey = '';
      }
    }
  }

  async function _sidebarEnsureWorktrees(baseRoot = _sidebarWorktreeBaseRoot()) {
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    const worktreeFolder = _sidebarActiveWorktreeFolder(baseRoot);
    if (!worktreeFolder) {
      _sidebarClearWorktreeDiscovery();
      return [];
    }
    try {
      return await _sidebarDiscoverWorktrees(worktreeFolder, {baseRoot: workspaceRoot});
    } catch (error) {
      _sidebarClearWorktreeDiscovery();
      _sidebarRecentLog('warning', `worktree folder scan failed: ${error.message || error}`, {
        action: 'sidebar.worktree.scan',
        target: worktreeFolder,
      });
      return [];
    }
  }

  function _sidebarSelectedWorktree(baseRoot) {
    if (!_sidebarActiveWorktreeFolder(baseRoot)) return null;
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    const selected = String((_sidebarFileConfig.selectedWorktrees || {})[workspaceRoot] || '');
    if (!selected) return null;
    return _sidebarWorktreeFolders.find(row => row.path === selected) || null;
  }

  function _sidebarScopedRoot(baseRoot) {
    const selected = _sidebarSelectedWorktree(baseRoot);
    return selected ? selected.path : _sidebarWorkspaceRoot(baseRoot);
  }

  function _sidebarWorktreeColor(path) {
    return _sidebarValidColor((_sidebarFileConfig.worktreeColors || {})[path]);
  }

  function _sidebarWorktreePickerHtml(baseRoot) {
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    const worktreeFolder = _sidebarActiveWorktreeFolder(baseRoot);
    const selected = _sidebarSelectedWorktree(baseRoot);
    const selectedPath = selected ? selected.path : '';
    const selectedLabel = selected ? selected.name : 'main';
    const options = [
      '<option value="">main</option>',
      ..._sidebarWorktreeFolders.map(row => `<option value="${escAttr(row.path)}"${row.path === selectedPath ? ' selected' : ''}>${esc(row.name)}</option>`),
    ];
    const color = selected ? _sidebarWorktreeColor(selected.path) : SIDEBAR_WORKTREE_DEFAULT_COLOR;
    const rootControl = worktreeFolder
      ? `<label title="Choose the root shown by Recently updated and Files"><select aria-label="File worktree" data-base-root="${escAttr(baseRoot)}" onchange="sidebarSelectWorktree(this)">${options.join('')}</select></label>`
      : `<span class="sidebar-worktree-current" title="Main checkout">main</span>`;
    return `<div class="sidebar-worktree-picker" data-base-root="${escAttr(baseRoot)}" data-workspace-root="${escAttr(workspaceRoot)}"><button class="sidebar-repo-history" type="button" data-base-root="${escAttr(baseRoot)}" onclick="sidebarOpenRepositoryHistory(this)" title="Open Git history for ${escAttr(selectedLabel)}" aria-label="Open Git history for ${escAttr(selectedLabel)}">${_SIDEBAR_GITHUB_ICON}</button>${rootControl}<button type="button" class="sidebar-link-terminal" data-base-root="${escAttr(baseRoot)}" onclick="termLinkCurrentScope(this)" title="Associate the active terminal with this folder/worktree; its running directory stays unchanged">Link current terminal</button><input type="color" aria-label="Worktree color" title="Color for ${escAttr(selected ? selected.name : 'the selected worktree')}" data-worktree-path="${escAttr(selectedPath)}" value="${escAttr(color)}" onchange="sidebarSetWorktreeColor(this)"${selected ? '' : ' disabled'} /></div>`;
  }

  function _sidebarFileScopeButtonsHtml(baseRoot) {
    const selectedPath = _sidebarSelectedFolder(baseRoot)?.path || '';
    const rootColor = _sidebarValidColor((_sidebarFileConfig.rootScopeColors || {})[baseRoot]);
    const scopes = [
      {path: '', label: 'Root', color: rootColor, title: baseRoot},
      ...(_sidebarFileConfig.folderScopes || []).map(row => ({
        path: row.path,
        label: row.label,
        color: _sidebarValidColor(row.color),
        title: row.path,
      })),
    ];
    return `<div class="sidebar-file-scope-buttons" role="group" aria-label="Workspace folders">${scopes.map(scope => {
      const active = scope.path === selectedPath;
      return `<button type="button" class="sidebar-file-scope-button${active ? ' active' : ''}" data-base-root="${escAttr(baseRoot)}" data-folder-path="${escAttr(scope.path)}" onclick="sidebarSelectFolder(this)" aria-pressed="${active ? 'true' : 'false'}" title="${escAttr(scope.title)}" style="--sidebar-workspace-color:${escAttr(scope.color)}"><span class="sidebar-file-scope-dot"></span><span>${esc(scope.label)}</span></button>`;
    }).join('')}</div>`;
  }

  function _sidebarWorktreeScopeStartHtml(baseRoot) {
    const folder = _sidebarSelectedFolder(baseRoot);
    const selected = _sidebarSelectedWorktree(baseRoot);
    if (!folder && !selected) return '';
    const color = selected ? _sidebarWorktreeColor(selected.path) : _sidebarWorkspaceColor(baseRoot);
    const worktreeAttr = selected ? ` data-worktree-path="${escAttr(selected.path)}"` : '';
    const label = selected ? `${_sidebarWorkspaceLabel(baseRoot)} · ${selected.name}` : _sidebarWorkspaceLabel(baseRoot);
    return `<div class="sidebar-worktree-scope" data-file-scope-root="${escAttr(_sidebarScopedRoot(baseRoot))}"${worktreeAttr} style="--sidebar-worktree-color:${escAttr(color)}" title="Files from ${escAttr(label)}">`;
  }

  function _sidebarWorktreeScopeEndHtml(baseRoot) {
    return (_sidebarSelectedFolder(baseRoot) || _sidebarSelectedWorktree(baseRoot)) ? '</div>' : '';
  }

  function _sidebarFileExtension(path) {
    const base = String(path || '').split('/').pop().toLowerCase();
    const index = base.lastIndexOf('.');
    return index > 0 && index < base.length - 1 ? base.slice(index + 1) : '__none__';
  }

  function _sidebarRememberAvailableExtensions(files) {
    _sidebarAvailableExtensions = new Set(
      (files || [])
        .filter(file => file && file.type !== 'dir')
        .map(file => _sidebarFileExtension(file.path || file.name))
    );
  }

  function _sidebarCurrentRecentMode() {
    const mode = String(_sidebarFileConfig && _sidebarFileConfig.recentMode || '');
    if (mode === 'none' || mode === 'mtime' || SIDEBAR_RECENT_GIT_MODES.includes(mode)) {
      return mode;
    }
    return _sidebarFileConfig && _sidebarFileConfig.showRecent === false ? 'none' : 'mtime';
  }

  function _sidebarRecentTypeAllowed(file) {
    if (_sidebarFileConfig.trackMode !== 'extensions') return true;
    return new Set(_sidebarFileConfig.extensions || [])
      .has(_sidebarFileExtension(file.path || file.name));
  }

  function _sidebarRecentFiles(files, nowSeconds = Date.now() / 1000) {
    if (_sidebarCurrentRecentMode() !== 'mtime') return [];
    const cutoff = nowSeconds - (_sidebarFileConfig.recentMinutes * 60);
    return (files || [])
      .filter(file => {
        if (!file || file.type === 'dir' || !Number.isFinite(Number(file.mtime))) return false;
        if (Number(file.mtime) < cutoff) return false;
        return _sidebarRecentTypeAllowed(file);
      })
      .sort((a, b) => _sidebarCompareFiles(a, b, _sidebarCurrentSortMode('recent')));
  }

  async function _sidebarResolveRecentFiles(files, rootPath) {
    const mode = _sidebarCurrentRecentMode();
    if (mode === 'none') return [];
    if (mode === 'mtime') return _sidebarRecentFiles(files);
    try {
      const response = await fetch(`/api/sidebar-recent-files?repo=${encodeURIComponent(rootPath)}&mode=${encodeURIComponent(mode)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || response.statusText || 'Could not load Git file scope');
      const byPath = new Map((files || [])
        .filter(file => file && file.type !== 'dir')
        .map(file => [String(file.path || file.name || ''), file]));
      return (Array.isArray(data.files) ? data.files : [])
        .map(path => byPath.get(String(path)))
        .filter(file => file && _sidebarRecentTypeAllowed(file))
        .sort((a, b) => _sidebarCompareFiles(a, b, _sidebarCurrentSortMode('recent')));
    } catch (error) {
      _sidebarRecentLog('warning', `recent Git file scope failed: ${error.message || error}`, {
        action: 'sidebar.recent.git_scope',
        event_type: 'sidebar.recent.git_scope_failed',
        target: rootPath,
      });
      return [];
    }
  }

  function _sidebarRecentExclusionReason(file, recentPaths, cutoff) {
    const path = String(file && (file.path || file.name) || '');
    if (recentPaths.has(path)) return 'included';
    const mtime = Number(file && file.mtime);
    if (!Number.isFinite(mtime)) return 'missing_mtime';
    if (mtime < cutoff) return 'outside_freshness_window';
    if (_sidebarFileConfig.trackMode === 'extensions') return 'extension_not_selected';
    return 'filtered_unknown';
  }

  function _sidebarRecentLog(level, message, details = {}) {
    try {
      const logger = window.labLog;
      const fn = logger && (logger[level] || logger.info);
      if (typeof fn === 'function') fn.call(logger, message, details);
    } catch (_) {}
  }

  function _sidebarLogRecentDiagnostics(files, rootPath, reason, nowSeconds = Date.now() / 1000) {
    const allFiles = (files || []).filter(file => file && file.type !== 'dir');
    const recent = _sidebarRecentFiles(allFiles, nowSeconds);
    const recentPaths = new Set(recent.map(file => String(file.path || file.name || '')));
    const cutoff = nowSeconds - (_sidebarFileConfig.recentMinutes * 60);
    const withMtime = allFiles.filter(file => Number.isFinite(Number(file.mtime)));
    const readmes = allFiles.filter(file => /(^|\/)readme\.md$/i.test(String(file.path || file.name || '')));
    const newest = [...withMtime]
      .sort((a, b) => Number(b.mtime) - Number(a.mtime))
      .slice(0, 5)
      .map(file => ({
        path: String(file.path || file.name || ''),
        mtime: Number(file.mtime),
        age_minutes: Math.round((nowSeconds - Number(file.mtime)) / 6) / 10,
      }));
    const summary = {
      reason,
      root: rootPath,
      now: nowSeconds,
      cutoff,
      recent_minutes: _sidebarFileConfig.recentMinutes,
      track_mode: _sidebarFileConfig.trackMode,
      extensions: _sidebarFileConfig.extensions || [],
      file_count: allFiles.length,
      files_with_mtime: withMtime.length,
      recent_count: recent.length,
      readme_count: readmes.length,
      newest,
    };
    _sidebarRecentLog('info', 'recent files diagnostic ' + JSON.stringify(summary), {
      action: 'sidebar.recent.diagnostic',
      event_type: 'sidebar.recent.summary',
      target: rootPath,
    });
    readmes.slice(0, 50).forEach(file => {
      const mtime = Number(file.mtime);
      const row = {
        path: String(file.path || file.name || ''),
        mtime: Number.isFinite(mtime) ? mtime : null,
        age_minutes: Number.isFinite(mtime) ? Math.round((nowSeconds - mtime) / 6) / 10 : null,
        result: _sidebarRecentExclusionReason(file, recentPaths, cutoff),
      };
      _sidebarRecentLog('info', 'recent README diagnostic ' + JSON.stringify(row), {
        action: 'sidebar.recent.diagnostic',
        event_type: 'sidebar.recent.readme',
        target: row.path,
      });
    });
    if (readmes.length > 50) {
      _sidebarRecentLog('warning', `recent README diagnostic truncated ${readmes.length - 50} rows`, {
        action: 'sidebar.recent.diagnostic',
        event_type: 'sidebar.recent.truncated',
        target: rootPath,
      });
    }
    try { if (window.labLog && window.labLog.flush) window.labLog.flush(); } catch (_) {}
  }

  function _sidebarMaybeLogRecentDiagnostics(files, rootPath) {
    const pending = _sidebarRecentDiagnosticsPending;
    if (!pending || (pending.root && pending.root !== rootPath)) return;
    _sidebarRecentDiagnosticsPending = null;
    _sidebarLogRecentDiagnostics(files, rootPath, pending.reason);
  }

  async function _sidebarFetchWorkspaceFiles(workspacePath) {
    const url = `/api/workspace-files?path=${encodeURIComponent(workspacePath)}&include_dotfiles=${showWorkspaceDotFiles}`;
    const response = await fetch(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      _sidebarRecentLog('error', 'recent files source fetch failed ' + JSON.stringify({
        root: workspacePath,
        status: response.status,
        detail: body.detail || response.statusText || 'request failed',
      }), {
        action: 'sidebar.recent.fetch',
        event_type: 'sidebar.recent.fetch_failed',
        target: workspacePath,
        status_code: response.status,
      });
      throw new Error(body.detail || response.statusText || 'Could not load workspace files');
    }
    const files = await response.json();
    if (!Array.isArray(files)) {
      _sidebarRecentLog('error', 'recent files source returned invalid payload ' + JSON.stringify({
        root: workspacePath,
        payload_type: files === null ? 'null' : typeof files,
      }), {
        action: 'sidebar.recent.fetch',
        event_type: 'sidebar.recent.invalid_payload',
        target: workspacePath,
      });
      throw new Error('Invalid workspace files response');
    }
    return files;
  }

  function _sidebarFileConfigCogHtml() {
    return '<button type="button" class="sidebar-file-config-cog" onclick="event.preventDefault();event.stopPropagation();openSidebarFileConfig()" title="File view settings" aria-label="Open file view settings"><span aria-hidden="true">&#x2699;</span></button>';
  }

  function _sidebarSortSelectHtml(section) {
    const isRecent = section === 'recent';
    const value = _sidebarCurrentSortMode(section);
    const label = isRecent ? 'Recently updated' : 'Files';
    const options = [
      ['updated', 'Update ↓'],
      ['name', 'Name'],
      ['type', 'Type'],
    ];
    return `<label class="sidebar-sort-control" title="Sort ${escAttr(label)} independently"><select data-sort-section="${escAttr(section)}" aria-label="Sort ${escAttr(label)}" onchange="sidebarSelectSort(this)">${options.map(([mode, text]) => `<option value="${mode}"${mode === value ? ' selected' : ''}>${text}</option>`).join('')}</select></label>`;
  }

  async function sidebarSelectSort(select) {
    const section = String(select && select.getAttribute('data-sort-section') || '');
    const fallback = section === 'recent'
      ? SIDEBAR_FILE_CONFIG_DEFAULTS.recentSort
      : SIDEBAR_FILE_CONFIG_DEFAULTS.filesSort;
    const mode = _sidebarNormalizeSortMode(select && select.value, fallback);
    if (section === 'recent') {
      if (_sidebarFileConfig.recentSort === mode) return;
      _sidebarFileConfig.recentSort = mode;
    } else if (section === 'files') {
      if (_sidebarFileConfig.filesSort === mode) return;
      _sidebarFileConfig.filesSort = mode;
    } else {
      return;
    }
    _storeSidebarFileConfig();
    await _refreshSidebarAfterFileConfig();
  }
  window.sidebarSelectSort = sidebarSelectSort;

  function _sidebarRecentSelectorValue() {
    const mode = _sidebarCurrentRecentMode();
    return mode === 'mtime' ? `mtime:${_sidebarFileConfig.recentMinutes}` : mode;
  }

  function _sidebarRecentSelectorsHtml() {
    const selected = _sidebarRecentSelectorValue();
    const rows = [
      [
        ['mtime:15', '15m', '15 min', 'Files updated in the last 15 minutes'],
        ['mtime:60', '1h', '1 hour', 'Files updated in the last hour'],
        ['mtime:120', '2h', '2 hours', 'Files updated in the last 2 hours'],
        ['mtime:360', '6h', '6 hours', 'Files updated in the last 6 hours'],
        ['mtime:1440', '24h', '24 hours', 'Files updated in the last 24 hours'],
      ],
      [
        ['uncommitted', 'Uncomm', 'Uncommitted', 'Files with uncommitted changes'],
        ['origin-main', 'vs main', 'vs origin/main', 'Files changed compared with origin/main'],
        ['last-2-commits', '2 cmts', 'Last 2 commits', 'Files changed by the last 2 commits'],
      ],
    ];
    return `<div class="sidebar-recent-selectors" role="group" aria-label="Recently updated file scope" title="Select one file scope; click the active option again to hide Recently updated">${rows.map(row => `<div class="sidebar-recent-selector-row">${row.map(([value, shortLabel, longLabel, title]) => {
      const active = value === selected;
      return `<button type="button" class="sidebar-recent-selector${active ? ' active' : ''}" data-recent-mode="${escAttr(value)}" onclick="sidebarSelectRecentMode(this)" aria-label="${escAttr(title)}" aria-pressed="${active ? 'true' : 'false'}" title="${escAttr(title)}${active ? ' · click again to hide' : ''}"><span class="sidebar-recent-label-short">${esc(shortLabel)}</span><span class="sidebar-recent-label-long">${esc(longLabel)}</span></button>`;
    }).join('')}</div>`).join('')}</div>`;
  }

  async function sidebarSelectRecentMode(button) {
    const requested = String(button && button.getAttribute('data-recent-mode') || '');
    const current = _sidebarRecentSelectorValue();
    if (requested === current) {
      _sidebarFileConfig.recentMode = 'none';
      _sidebarFileConfig.showRecent = false;
    } else if (requested.startsWith('mtime:')) {
      const minutes = _sidebarNormalizeRecentMinutes(requested.slice('mtime:'.length));
      _sidebarFileConfig.recentMode = 'mtime';
      _sidebarFileConfig.recentMinutes = minutes;
      _sidebarFileConfig.showRecent = true;
    } else if (SIDEBAR_RECENT_GIT_MODES.includes(requested)) {
      _sidebarFileConfig.recentMode = requested;
      _sidebarFileConfig.showRecent = true;
    } else {
      return;
    }
    _storeSidebarFileConfig();
    await _refreshSidebarAfterFileConfig();
  }
  window.sidebarSelectRecentMode = sidebarSelectRecentMode;

  function _sidebarRecentTreeModel(files) {
    const sortMode = _sidebarCurrentSortMode('recent');
    const compactNode = (node, parentPath) => {
      const model = {files: treeFiles(node, sortMode), folders: []};
      treeFolderNames(node, sortMode).forEach(folder => {
        const labelParts = [folder];
        let path = parentPath ? `${parentPath}/${folder}` : folder;
        let child = node[folder];

        // Match the compact-folder behavior used by editors: a run of
        // folders with no files and exactly one child is one visual row.
        // Stop at a real branch so siblings such as core/src and core/tests
        // remain immediately recognizable.
        while (treeFiles(child).length === 0) {
          const childFolders = treeFolderNames(child, sortMode);
          if (childFolders.length !== 1) break;
          const next = childFolders[0];
          labelParts.push(next);
          path += `/${next}`;
          child = child[next];
        }

        model.folders.push({
          label: labelParts.join('/'),
          path,
          children: compactNode(child, path),
        });
      });
      return model;
    };

    return compactNode(buildSidebarTree(files), '');
  }

  const _SIDEBAR_GITHUB_ICON = '<svg viewBox="0 0 16 16" aria-hidden="true"><path fill="currentColor" d="M8 .2a8 8 0 0 0-2.53 15.59c.4.07.55-.18.55-.39 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82A7.5 7.5 0 0 1 8 4.03c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.47.55.39A8 8 0 0 0 8 .2Z"/></svg>';

  function sidebarOpenRepositoryHistory(button) {
    const baseRoot = button && button.getAttribute('data-base-root');
    if (!baseRoot) return;
    const selected = _sidebarSelectedWorktree(baseRoot);
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    return openRepositoryHistory({
      root: selected ? (selected.repo || selected.path) : _sidebarWorktreeRepositoryRoot(workspaceRoot),
      label: selected ? selected.name : 'main',
    });
  }
  window.sidebarOpenRepositoryHistory = sidebarOpenRepositoryHistory;

  function _sidebarGitHistoryButtonHtml(path, root = '') {
    const safePath = String(path || '').replace(/'/g, "\\'");
    const safeRoot = String(root || '').replace(/'/g, "\\'");
    return `<span class="sidebar-actions"><button class="sidebar-git-history" type="button" onclick="event.preventDefault();event.stopPropagation();openSidebarFileHistory('${safePath}','${safeRoot}')" ondblclick="event.preventDefault();event.stopPropagation()" title="View Git history, including uncommitted changes" aria-label="View Git history for ${escAttr(path)}">${_SIDEBAR_GITHUB_ICON}</button></span>`;
  }

  function openSidebarFileHistory(path, root = '') {
    if (!path || !currentWorkspace || !currentWorkspace.path) return;
    return openExplorerHistory({
      kind: 'file',
      path: String(path),
      root: root || currentWorkspace.path,
      row: null,
      surface: 'workspace',
    });
  }
  window.openSidebarFileHistory = openSidebarFileHistory;

  function _sidebarRecentSectionHtml(files, activePath, root = '', {resolved = false} = {}) {
    const recent = resolved ? (files || []) : _sidebarRecentFiles(files);
    if (!recent.length) return '';
    let html = `<div class="sidebar-title sidebar-title-with-action"><span>Recently updated <span class="sidebar-title-count">${recent.length}</span></span><span class="sidebar-title-actions">${_sidebarSortSelectHtml('recent')}</span></div>`;
    const scopeRoot = root || (currentWorkspace && currentWorkspace.path ? currentWorkspace.path : 'global');
    const scope = `recent:${scopeRoot}`;
    const tree = _sidebarRecentTreeModel(recent);

    const renderNode = node => {
      let nodeHtml = '';
      node.folders.forEach(folder => {
        const fid = 'recent-folder-' + Math.random().toString(36).slice(2, 8);
        const open = _treeIsOpen(scope, folder.path, true);
        nodeHtml += `<div class="sidebar-folder sidebar-recent-folder" data-tree-scope="${escAttr(scope)}" data-tree-path="${escAttr(folder.path)}" data-tree-target="${fid}" onclick="_treeToggleFolder(this)" title="${escAttr(folder.path)}"><span class="folder-arrow${open ? ' open' : ''}">&#9654;</span>${esc(folder.label)}/</div>`;
        nodeHtml += `<div class="sidebar-folder-children${open ? ' open' : ''}" id="${fid}">${renderNode(folder.children)}</div>`;
      });
      node.files.forEach(file => {
        const path = String(file.path || file.name || '');
        const safePath = path.replace(/'/g, "\\'");
        const base = path.split('/').pop();
        const activeCls = activePath === path ? ' active' : '';
        const safeRoot = String(scopeRoot).replace(/'/g, "\\'");
        nodeHtml += `<a class="sidebar-file sidebar-file-recent${activeCls}${symlinkClass(file)}" data-filepath="${esc(path)}" data-entry-kind="file" data-entry-path="${escAttr(path)}" data-entry-root="${escAttr(scopeRoot)}"${symlinkTitle(file)} onclick="openWorkspaceDocFromFileClick('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openWorkspaceDocModal('${safePath}',{root:'${safeRoot}'})" title="Recently updated · ${escAttr(path)}"><span class="sidebar-fname">${symlinkMarker(file)}${fileIconHtml(base, file)}${esc(base)}</span>${_sidebarGitHistoryButtonHtml(path, scopeRoot)}</a>`;
      });
      return nodeHtml;
    };

    html += renderNode(tree);
    return html;
  }

  function _sidebarConfigFolderCardHtml(row, {root = false, baseRoot = ''} = {}) {
    const path = root ? baseRoot : String(row && row.path || '');
    const fallback = path.split('/').filter(Boolean).pop() || 'Workspace';
    const label = root ? 'Root' : String(row && row.label || fallback);
    const color = root
      ? _sidebarValidColor((_sidebarFileConfig.rootScopeColors || {})[baseRoot])
      : _sidebarValidColor(row && row.color);
    const rootWorktreeFolder = String(
      (_sidebarFileConfig.rootWorktreeFolders || {})[baseRoot]
      || _sidebarFileConfig.worktreeFolder
      || ''
    );
    const worktreeFolder = root ? rootWorktreeFolder : String(row && row.worktreeFolder || '');
    const identity = root
      ? `<div class="sidebar-config-folder-identity"><strong>Root</strong><code title="${escAttr(baseRoot)}">${esc(baseRoot)}</code></div>`
      : `<div class="sidebar-config-folder-fields">
          <label>Name<input type="text" data-scope-label value="${escAttr(label)}" placeholder="Workspace name" /></label>
          <label class="sidebar-config-folder-path">Folder or subfolder<input type="text" data-scope-path value="${escAttr(path)}" placeholder="workspaces/my-workspace or /absolute/path" autocomplete="off" spellcheck="false" /></label>
        </div>`;
    const remove = root ? '' : '<button class="sidebar-config-folder-remove" type="button" onclick="sidebarFileConfigRemoveFolder(this)" aria-label="Remove workspace folder" title="Remove workspace folder">&times;</button>';
    return `<div class="sidebar-config-folder-card${root ? ' root' : ''}" data-scope-root="${root ? 'true' : 'false'}">
      <div class="sidebar-config-folder-card-head">${identity}${remove}</div>
      <div class="sidebar-config-folder-options">
        <label class="sidebar-config-folder-color">Color<input type="color" data-scope-color value="${escAttr(color)}" /></label>
        <label class="sidebar-config-folder-worktree">Worktree folder <span class="sidebar-config-worktree-input-row"><input type="text" data-scope-worktree value="${escAttr(worktreeFolder)}" placeholder="Optional path to worktrees" autocomplete="off" spellcheck="false" oninput="sidebarFileConfigWorktreeInput(this)" /><button type="button" onclick="sidebarFileConfigScanScope(this)">Scan</button></span><small>Optional. Paste the folder containing Git worktrees, or a direct-child worktree inside it.</small></label>
      </div>
      <div class="sidebar-config-worktree-status" data-scope-status role="status">${worktreeFolder ? 'Scan to preview worktrees.' : 'No worktree folder — this workspace uses only its main folder.'}</div>
      <div class="sidebar-config-worktree-colors" data-scope-worktree-colors></div>
    </div>`;
  }

  function _sidebarRenderFolderConfig() {
    const host = document.getElementById('sidebarConfigFolderScopes');
    if (!host) return;
    const baseRoot = _sidebarWorktreeBaseRoot();
    host.innerHTML = _sidebarConfigFolderCardHtml(null, {root: true, baseRoot})
      + (_sidebarFileConfig.folderScopes || []).map(row => _sidebarConfigFolderCardHtml(row)).join('');
  }

  function sidebarFileConfigAddFolder() {
    const host = document.getElementById('sidebarConfigFolderScopes');
    if (!host) return;
    host.insertAdjacentHTML('beforeend', _sidebarConfigFolderCardHtml({
      path: '',
      label: '',
      color: SIDEBAR_WORKTREE_DEFAULT_COLOR,
      worktreeFolder: '',
    }));
    const error = document.getElementById('sidebarConfigFolderError');
    if (error) error.classList.remove('on');
  }

  function sidebarFileConfigRemoveFolder(button) {
    const card = button && button.closest('.sidebar-config-folder-card');
    if (card && card.getAttribute('data-scope-root') !== 'true') card.remove();
  }

  function _sidebarFolderCardPath(card, baseRoot = _sidebarWorktreeBaseRoot()) {
    if (!card) return '';
    if (card.getAttribute('data-scope-root') === 'true') return baseRoot;
    const input = card.querySelector('[data-scope-path]');
    return _sidebarNormalizeFolderPath(input && input.value, baseRoot);
  }

  function _sidebarCollectFolderConfigFromModal() {
    const baseRoot = _sidebarWorktreeBaseRoot();
    const rootScopeColors = {...(_sidebarFileConfig.rootScopeColors || {})};
    const rootWorktreeFolders = {...(_sidebarFileConfig.rootWorktreeFolders || {})};
    const folderScopes = [];
    const seen = new Set([baseRoot]);
    let problem = '';
    document.querySelectorAll('#sidebarConfigFolderScopes .sidebar-config-folder-card').forEach(card => {
      const isRoot = card.getAttribute('data-scope-root') === 'true';
      const colorInput = card.querySelector('[data-scope-color]');
      const worktreeInput = card.querySelector('[data-scope-worktree]');
      const color = _sidebarValidColor(colorInput && colorInput.value);
      if (isRoot) {
        rootScopeColors[baseRoot] = color;
        const rootFolder = _sidebarNormalizeWorktreeFolder(worktreeInput && worktreeInput.value, baseRoot);
        if (rootFolder) rootWorktreeFolders[baseRoot] = rootFolder;
        else delete rootWorktreeFolders[baseRoot];
        return;
      }
      const path = _sidebarFolderCardPath(card, baseRoot);
      if (!path) {
        problem ||= 'Every workspace needs a folder path.';
        return;
      }
      if (seen.has(path)) {
        problem ||= path === baseRoot
          ? 'Root is already included; choose a different folder or subfolder.'
          : `The folder ${path} was added more than once.`;
        return;
      }
      seen.add(path);
      const labelInput = card.querySelector('[data-scope-label]');
      const fallback = path.split('/').filter(Boolean).pop() || path;
      const worktreeFolder = _sidebarNormalizeWorktreeFolder(worktreeInput && worktreeInput.value, path);
      folderScopes.push({
        path,
        label: String(labelInput && labelInput.value || fallback).trim() || fallback,
        color,
        worktreeFolder,
      });
    });
    const error = document.getElementById('sidebarConfigFolderError');
    if (error) {
      error.textContent = problem;
      error.classList.toggle('on', !!problem);
    }
    return problem ? null : {folderScopes, rootScopeColors, rootWorktreeFolders};
  }

  function openSidebarFileConfig() {
    const modal = document.getElementById('sidebarFileConfigModal');
    if (!modal) return;
    const hidden = document.getElementById('sidebarConfigHidden');
    const recent = document.getElementById('sidebarConfigRecent');
    const freshness = document.getElementById('sidebarConfigFreshness');
    if (hidden) hidden.checked = _sidebarFileConfig.showHidden;
    if (recent) recent.checked = _sidebarCurrentRecentMode() !== 'none';
    if (freshness) freshness.value = String(_sidebarFileConfig.recentMinutes);
    const track = modal.querySelector(`input[name="sidebarRecentTrack"][value="${_sidebarFileConfig.trackMode}"]`);
    if (track) track.checked = true;

    const selected = new Set(_sidebarFileConfig.extensions || []);
    const available = [..._sidebarAvailableExtensions].sort((a, b) => {
      if (a === '__none__') return 1;
      if (b === '__none__') return -1;
      return a.localeCompare(b);
    });
    const host = document.getElementById('sidebarConfigExtensions');
    if (host) {
      host.innerHTML = available.length ? available.map(ext => {
        const label = ext === '__none__' ? '(no extension)' : `.${ext}`;
        const checked = _sidebarFileConfig.trackMode === 'all' || selected.has(ext);
        return `<label class="sidebar-config-extension" title="${escAttr(label)}"><input type="checkbox" value="${escAttr(ext)}" ${checked ? 'checked' : ''} /><span>${esc(label)}</span></label>`;
      }).join('') : '<span style="color:var(--text-dim);font-size:11px">No file extensions found.</span>';
    }
    _sidebarRenderFolderConfig();
    const error = document.getElementById('sidebarConfigFolderError');
    if (error) error.classList.remove('on');
    sidebarFileConfigSyncState();
    modal.classList.add('active');
    const baseRoot = _sidebarWorktreeBaseRoot();
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    const activeCard = [...document.querySelectorAll('#sidebarConfigFolderScopes .sidebar-config-folder-card')]
      .find(card => _sidebarFolderCardPath(card, baseRoot) === workspaceRoot);
    const scan = activeCard && activeCard.querySelector('.sidebar-config-worktree-input-row button');
    if (scan && _sidebarActiveWorktreeFolder(baseRoot)) void sidebarFileConfigScanScope(scan);
  }

  function closeSidebarFileConfig() {
    const modal = document.getElementById('sidebarFileConfigModal');
    if (modal) modal.classList.remove('active');
  }

  function sidebarFileConfigSyncState() {
    const recent = document.getElementById('sidebarConfigRecent');
    const options = document.getElementById('sidebarConfigRecentOptions');
    const enabled = !!(recent && recent.checked);
    const track = document.querySelector('input[name="sidebarRecentTrack"]:checked');
    const extensionMode = !!track && track.value === 'extensions';
    if (options) options.classList.toggle('disabled', !enabled);
    const freshness = document.getElementById('sidebarConfigFreshness');
    if (freshness) freshness.disabled = !enabled;
    document.querySelectorAll('input[name="sidebarRecentTrack"]').forEach(input => {
      input.disabled = !enabled;
    });
    document.querySelectorAll('#sidebarConfigExtensions input[type="checkbox"]').forEach(input => {
      input.disabled = !enabled || !extensionMode;
    });
    document.querySelectorAll('.sidebar-config-extension-head button').forEach(button => {
      button.disabled = !enabled || !extensionMode;
    });
  }

  function sidebarFileConfigSelectExtensions(checked) {
    document.querySelectorAll('#sidebarConfigExtensions input[type="checkbox"]').forEach(input => {
      input.checked = !!checked;
    });
  }

  function _sidebarCollectWorktreeColorsFromModal() {
    const colors = {...(_sidebarFileConfig.worktreeColors || {})};
    document.querySelectorAll('#sidebarConfigFolderScopes [data-scope-worktree-colors] input[type="color"]').forEach(input => {
      const path = input.getAttribute('data-worktree-path');
      if (path) colors[path] = _sidebarValidColor(input.value);
    });
    return colors;
  }

  function _sidebarRenderWorktreeConfig(card, folders) {
    const host = card && card.querySelector('[data-scope-worktree-colors]');
    const status = card && card.querySelector('[data-scope-status]');
    if (!host || !status) return;
    if (!folders.length) {
      host.innerHTML = '';
      status.classList.remove('error');
      status.textContent = 'No matching Git worktrees found for this workspace.';
      return;
    }
    host.innerHTML = folders.map(row => `
      <label class="sidebar-config-worktree-color-row" title="${escAttr(row.path)}">
        <span>${esc(row.name)}</span>
        <input type="color" aria-label="Color for ${escAttr(row.name)}" data-worktree-path="${escAttr(row.path)}" value="${escAttr(_sidebarWorktreeColor(row.path))}" />
      </label>`).join('');
    status.classList.remove('error');
    status.textContent = `${folders.length} worktree${folders.length === 1 ? '' : 's'} found.`;
  }

  function sidebarFileConfigWorktreeInput(input) {
    const card = input && input.closest('.sidebar-config-folder-card');
    const status = card && card.querySelector('[data-scope-status]');
    const colors = card && card.querySelector('[data-scope-worktree-colors]');
    if (colors) colors.innerHTML = '';
    if (status) {
      status.classList.remove('error');
      status.textContent = String(input.value || '').trim()
        ? 'Scan to preview worktrees.'
        : 'No worktree folder — this workspace uses only its main folder.';
    }
  }

  async function sidebarFileConfigScanScope(button) {
    const card = button && button.closest('.sidebar-config-folder-card');
    const input = card && card.querySelector('[data-scope-worktree]');
    const status = card && card.querySelector('[data-scope-status]');
    const colors = card && card.querySelector('[data-scope-worktree-colors]');
    const baseRoot = _sidebarWorktreeBaseRoot();
    const workspaceRoot = _sidebarFolderCardPath(card, baseRoot);
    const folder = String(input && input.value || '').trim();
    if (status) {
      status.classList.remove('error');
      status.textContent = folder ? 'Scanning…' : 'No worktree folder — this workspace uses only its main folder.';
    }
    if (!folder) {
      if (colors) colors.innerHTML = '';
      return [];
    }
    if (!workspaceRoot) {
      if (status) {
        status.classList.add('error');
        status.textContent = 'Enter this workspace folder before scanning its worktrees.';
      }
      return null;
    }
    try {
      const requested = _sidebarNormalizeWorktreeFolder(folder, workspaceRoot);
      const repositoryRoot = _sidebarWorktreeRepositoryRoot(workspaceRoot);
      const response = await fetch(`/api/sidebar-worktrees?path=${encodeURIComponent(requested)}&repo=${encodeURIComponent(repositoryRoot)}&scope=${encodeURIComponent(workspaceRoot)}`);
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not scan worktree folder');
      const folders = Array.isArray(data.folders)
        ? data.folders.filter(row => row && row.name && row.path).map(row => ({
            name: String(row.name),
            path: String(row.path),
            repo: String(row.repo || row.path),
          }))
        : [];
      if (input) input.value = String(data.path || requested);
      _sidebarRenderWorktreeConfig(card, folders);
      return folders;
    } catch (error) {
      if (colors) colors.innerHTML = '';
      if (status) {
        status.classList.add('error');
        status.textContent = error.message || String(error);
      }
      return null;
    }
  }

  async function sidebarSelectFolder(button) {
    _termCancelPendingLinkedFileOpen();
    const baseRoot = String(button && button.getAttribute('data-base-root') || '');
    if (!baseRoot) return;
    const requested = String(button.getAttribute('data-folder-path') || '');
    const selected = requested && _sidebarFolderScope(requested) ? requested : '';
    const previous = String((_sidebarFileConfig.selectedFolders || {})[baseRoot] || '');
    if (selected === previous) return;
    _sidebarFileConfig.selectedFolders = {...(_sidebarFileConfig.selectedFolders || {})};
    if (selected) _sidebarFileConfig.selectedFolders[baseRoot] = selected;
    else delete _sidebarFileConfig.selectedFolders[baseRoot];
    _sidebarClearWorktreeDiscovery();
    _storeSidebarFileConfig();
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    workspaceOpenFile = null;
    diffCache = {uncommitted: null, branch: null};
    _lastWorkspaceMtime = 0;
    _workspaceSidebarCache.delete(baseRoot);
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
    await _refreshSidebarAfterFileConfig();
  }

  async function sidebarSelectWorktree(select) {
    _termCancelPendingLinkedFileOpen();
    const baseRoot = String(select && select.getAttribute('data-base-root') || '');
    if (!baseRoot) return;
    const workspaceRoot = _sidebarWorkspaceRoot(baseRoot);
    const selected = String(select.value || '');
    _sidebarFileConfig.selectedWorktrees = {...(_sidebarFileConfig.selectedWorktrees || {})};
    if (selected) _sidebarFileConfig.selectedWorktrees[workspaceRoot] = selected;
    else delete _sidebarFileConfig.selectedWorktrees[workspaceRoot];
    _storeSidebarFileConfig();
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    workspaceOpenFile = null;
    diffCache = {uncommitted: null, branch: null};
    _lastWorkspaceMtime = 0;
    _workspaceSidebarCache.delete(baseRoot);
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
    await _refreshSidebarAfterFileConfig();
  }

  function sidebarSetWorktreeColor(input) {
    const path = String(input && input.getAttribute('data-worktree-path') || '');
    if (!path) return;
    const color = _sidebarValidColor(input.value);
    _sidebarFileConfig.worktreeColors = {...(_sidebarFileConfig.worktreeColors || {}), [path]: color};
    _storeSidebarFileConfig();
    document.querySelectorAll(`.sidebar-worktree-scope[data-worktree-path="${CSS.escape(path)}"]`).forEach(scope => {
      scope.style.setProperty('--sidebar-worktree-color', color);
    });
    termRenderSessionList();
  }

  async function _refreshSidebarAfterFileConfig() {
    if (document.body.classList.contains('self-active')) return selfPopulateSidebar();
    if (document.body.classList.contains('vault-active')) return vaultPopulateSidebar();
    if (currentRepo) return loadWorkspaceView();
    if (currentWorkspace && currentWorkspace.is_workspace) {
      _workspaceSidebarCache.delete(currentWorkspace.path);
      return _refreshWorkspaceSidebar({preserveScroll: true});
    }
  }

  async function saveSidebarFileConfig(event) {
    if (event) event.preventDefault();
    const hidden = document.getElementById('sidebarConfigHidden');
    const recent = document.getElementById('sidebarConfigRecent');
    const freshness = document.getElementById('sidebarConfigFreshness');
    const track = document.querySelector('input[name="sidebarRecentTrack"]:checked');
    const folderConfig = _sidebarCollectFolderConfigFromModal();
    if (!folderConfig) return false;
    const extensions = [...document.querySelectorAll('#sidebarConfigExtensions input[type="checkbox"]:checked')]
      .map(input => input.value);
    const recentMinutes = _sidebarNormalizeRecentMinutes(freshness && freshness.value);
    const recentEnabled = !!(recent && recent.checked);
    const previousRecentMode = _sidebarCurrentRecentMode();
    const recentMode = !recentEnabled
      ? 'none'
      : (previousRecentMode === 'none' || recentMinutes !== _sidebarFileConfig.recentMinutes
        ? 'mtime'
        : previousRecentMode);
    const validFolderPaths = new Set(folderConfig.folderScopes.map(row => row.path));
    const selectedFolders = Object.fromEntries(Object.entries(_sidebarFileConfig.selectedFolders || {})
      .filter(([, path]) => validFolderPaths.has(path)));
    _sidebarFileConfig = {
      showHidden: !!(hidden && hidden.checked),
      showRecent: recentMode !== 'none',
      recentMode,
      recentMinutes,
      recentSort: _sidebarFileConfig.recentSort,
      filesSort: _sidebarFileConfig.filesSort,
      trackMode: track && track.value === 'extensions' ? 'extensions' : 'all',
      extensions,
      folderScopes: folderConfig.folderScopes,
      rootScopeColors: folderConfig.rootScopeColors,
      rootWorktreeFolders: folderConfig.rootWorktreeFolders,
      selectedFolders,
      worktreeFolder: _sidebarFileConfig.worktreeFolder || '',
      worktreeColors: _sidebarCollectWorktreeColorsFromModal(),
      selectedWorktrees: {...(_sidebarFileConfig.selectedWorktrees || {})},
    };
    _sidebarClearWorktreeDiscovery();
    showDotFiles = _sidebarFileConfig.showHidden;
    showWorkspaceDotFiles = _sidebarFileConfig.showHidden;
    _storeSidebarFileConfig();
    if (currentWorkspace && currentWorkspace.path) {
      const baseRoot = _sidebarWorktreeBaseRoot() || currentWorkspace.path;
      _sidebarRecentDiagnosticsPending = {
        root: null,
        reason: 'file-sidebar-settings-save',
      };
    }
    closeSidebarFileConfig();
    termRenderSessionList();
    void _refreshSidebarAfterFileConfig();
    return false;
  }

  document.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    const modal = document.getElementById('sidebarFileConfigModal');
    if (modal && modal.classList.contains('active')) closeSidebarFileConfig();
  });

  function filterDotFiles(nodes) {
    return nodes.filter(n => !n.name.startsWith('.')).map(n => {
      if (n.type === 'dir' && n.children) {
        return { ...n, children: filterDotFiles(n.children) };
      }
      return n;
    });
  }

  function _sidebarFlattenTreeFiles(nodes, out = []) {
    (nodes || []).forEach(node => {
      if (!node) return;
      if (node.type === 'dir') _sidebarFlattenTreeFiles(node.children || [], out);
      else out.push(node);
    });
    return out;
  }

  function _sidebarSortNestedTree(nodes, metadataByPath, mode) {
    const prepared = (nodes || []).map(node => {
      if (!node) return node;
      if (node.type !== 'dir') {
        const metadata = metadataByPath.get(String(node.path || ''));
        return Number.isFinite(Number(metadata && metadata.mtime))
          ? {...node, mtime: Number(metadata.mtime)}
          : {...node};
      }
      const children = _sidebarSortNestedTree(node.children || [], metadataByPath, mode);
      const mtime = children.reduce((latest, child) => Math.max(latest, Number(child && child.mtime || 0)), 0);
      return {...node, children, mtime};
    }).filter(Boolean);
    return prepared.sort((a, b) => {
      if (a.type === 'dir' && b.type !== 'dir') return -1;
      if (a.type !== 'dir' && b.type === 'dir') return 1;
      if (a.type === 'dir') {
        if (mode === 'updated') {
          const updated = Number(b.mtime || 0) - Number(a.mtime || 0);
          if (updated) return updated;
        }
        return _sidebarCompareNames(a.name, b.name);
      }
      return _sidebarCompareFiles(a, b, mode);
    });
  }

  function toggleDotFiles(checked) {
    showDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    showWorkspaceDotFiles = checked;
    _storeSidebarFileConfig();
    loadWorkspaceView();
  }

  function toggleWorkspaceDotFiles(checked) {
    showWorkspaceDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    _storeSidebarFileConfig();
    if (currentWorkspace) _workspaceSidebarCache.delete(currentWorkspace.path);
    showWorkspaceInfo({preserveScroll: true});
  }

  async function loadWorkspaceView() {
    if (!currentRepo) return;
    const baseRoot = currentRepo;
    await _sidebarEnsureWorktrees(baseRoot);
    const fileRoot = _sidebarScopedRoot(baseRoot);
    _repoFileRoot = fileRoot;
    const sb = document.getElementById('sidebar');
    const content = document.getElementById('content');
    content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';

    // Ensure branch diff (vs master) is loaded for change indicators
    if (!diffCache.branch) {
      try {
        const dres = await fetch(`/api/diff?repo=${encodeURIComponent(fileRoot)}&type=branch`);
        diffCache.branch = await dres.json();
        document.getElementById('countBranch').textContent = diffCache.branch.files.length;
        if (diffCache.branch.base_branch) document.getElementById('branchTabLabel').textContent = `vs ${diffCache.branch.base_branch}`;
      } catch (err) {}
    }

    // Load file tree
    try {
      const res = await fetch(`/api/tree?repo=${encodeURIComponent(fileRoot)}`);
      fileTree = await res.json();
      _sidebarRememberAvailableExtensions(_sidebarFlattenTreeFiles(fileTree));
    } catch (err) {
      fileTree = [];
    }
    let recentFiles = [];
    let sidebarFiles = [];
    try {
      sidebarFiles = await _sidebarFetchWorkspaceFiles(fileRoot);
      _sidebarRememberAvailableExtensions(sidebarFiles);
      recentFiles = await _sidebarResolveRecentFiles(sidebarFiles, fileRoot);
    } catch (_) {}

    // Get changed files with status for indicators (vs master)
    const changedFiles = new Map();
    if (diffCache.branch) {
      diffCache.branch.files.forEach(f => changedFiles.set(f.filename, f.status));
      // Add deleted files to the tree (they won't be in git ls-files)
      diffCache.branch.files.filter(f => f.status === 'deleted').forEach(f => {
        const parts = f.filename.split('/');
        let parent = fileTree;
        for (let i = 0; i < parts.length - 1; i++) {
          const dirPath = parts.slice(0, i + 1).join('/');
          let dirNode = parent.find(n => n.type === 'dir' && n.path === dirPath);
          if (!dirNode) {
            dirNode = { name: parts[i], path: dirPath, type: 'dir', children: [] };
            parent.push(dirNode);
          }
          parent = dirNode.children;
        }
        if (!parent.find(n => n.path === f.filename)) {
          parent.push({ name: parts[parts.length - 1], path: f.filename, type: 'file' });
        }
      });
    }

    const filtered = showDotFiles ? fileTree : filterDotFiles(fileTree);
    const metadataByPath = new Map(sidebarFiles.map(file => [String(file.path || file.name || ''), file]));
    const sortedFiles = _sidebarSortNestedTree(filtered, metadataByPath, _sidebarCurrentSortMode('files'));
    sb.innerHTML = '<div class="sidebar-title sidebar-title-with-action"><span>Workspace</span>' + _sidebarFileConfigCogHtml() + '</div>' +
      _sidebarRecentSelectorsHtml() +
      _sidebarFileScopeButtonsHtml(baseRoot) +
      _sidebarWorktreePickerHtml(baseRoot) +
      symlinkLegendHtml() +
      _sidebarWorktreeScopeStartHtml(baseRoot) +
      _sidebarRecentSectionHtml(recentFiles, workspaceOpenFile, fileRoot, {resolved: true}) +
      _sidebarFilesTitle(fileRoot, 'repo') +
      '<ul class="tree-node">' + renderTreeNodes(sortedFiles, changedFiles) + '</ul>' +
      _sidebarWorktreeScopeEndHtml(baseRoot);
  }

  function dirHasChangedFiles(node, changedFiles) {
    if (node.type === 'file') return changedFiles.has(node.path);
    return node.children && node.children.some(c => dirHasChangedFiles(c, changedFiles));
  }

  function renderTreeNodes(nodes, changedFiles) {
    return nodes.map(node => {
      if (node.type === 'dir') {
        const hasChanged = dirHasChangedFiles(node, changedFiles);
        const collapsed = hasChanged ? '' : ' collapsed';
        const arrow = hasChanged ? '' : ' collapsed';
        return `<li>
          <div class="tree-dir${symlinkClass(node)}" data-entry-kind="folder" data-entry-path="${escAttr(node.path)}" data-entry-root="${escAttr(_activeRepoFileRoot() || '')}"${symlinkTitle(node)} onclick="toggleTreeDir(this)">
            <span class="arrow${arrow}">▾</span>${symlinkMarker(node)}${node.name}/
          </div>
          <ul class="tree-node tree-dir-children${collapsed}">${renderTreeNodes(node.children, changedFiles)}</ul>
        </li>`;
      } else {
        const status = changedFiles.get(node.path);
        let badge = '';
        if (status === 'added') badge = '<span class="sidebar-badge added"></span>';
        else if (status === 'deleted') badge = '<span class="sidebar-badge deleted"></span>';
        else if (status) badge = '<span class="sidebar-badge modified"></span>';
        const cls = workspaceOpenFile === node.path ? ' active' : '';
        return `<li>
          <div class="tree-file${cls}${symlinkClass(node)}" data-entry-kind="file" data-entry-path="${escAttr(node.path)}" data-entry-root="${escAttr(_activeRepoFileRoot() || '')}"${symlinkTitle(node)} onclick="openWorkspaceFileFromFileClick('${node.path.replace(/'/g, "\\'")}')">
            ${badge}${symlinkMarker(node)}${fileIconHtml(node.name, node)}${node.name}
          </div>
        </li>`;
      }
    }).join('');
  }

  function toggleTreeDir(el) {
    const children = el.nextElementSibling;
    const arrow = el.querySelector('.arrow');
    children.classList.toggle('collapsed');
    arrow.classList.toggle('collapsed');
  }

  function openWorkspaceFileFromFileClick(filepath) {
    // Only this explicit Files/Recently Updated entry point may drive the
    // linked terminal. Generic opens are also used by refresh/restore flows.
    _termCancelPendingLinkedFileOpen();
    _termSyncFromFileClick(_activeRepoFileRoot(), filepath);
    return openWorkspaceFile(filepath);
  }
  window.openWorkspaceFileFromFileClick = openWorkspaceFileFromFileClick;

  async function openWorkspaceFile(filepath) {
    if (!currentRepo) return;
    const fileRoot = _activeRepoFileRoot();
    workspaceOpenFile = filepath;
    workspaceEditMode = false;
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading...</div>';

    // Highlight active in tree
    document.querySelectorAll('.tree-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.tree-file').forEach(el => {
      if (el.textContent.trim().endsWith(filepath.split('/').pop())) el.classList.add('active');
    });

    if (isNotebook(filepath)) {
      await renderNotebookView(filepath);
      return;
    }

    if (/\.(diff|patch)$/i.test(filepath)) {
      try {
        await ensureHighlight().catch(() => {});
        const res = await fetch(`/api/workspace-diff-file?path=${encodeURIComponent(fileRoot)}&file=${encodeURIComponent(filepath)}`);
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
        const data = await res.json();
        if (workspaceOpenFile !== filepath) return;
        renderStoredDiffDocument(filepath, data, content);
      } catch (err) {
        if (workspaceOpenFile === filepath) content.innerHTML = `<div class="file-viewer-empty">Error: ${esc(err.message || err)}</div>`;
      }
      return;
    }

    try {
      const res = await fetch(`/api/file?repo=${encodeURIComponent(fileRoot)}&path=${encodeURIComponent(filepath)}`);
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      renderWorkspaceFileView(filepath, data.content);
    } catch (err) {
      content.innerHTML = `<div class="file-viewer-empty">Error: ${err.message}</div>`;
    }
  }

  function renderWorkspaceFileView(filepath, fileContent) {
    const content = document.getElementById('content');
    const { added } = getChangedLines(filepath);
    const lang = getHljsLang(filepath);
    const lines = fileContent.split('\n');

    const rows = lines.map((line, i) => {
      const n = i + 1;
      const isChanged = added.has(n);
      const cls = isChanged ? ' class="vchanged"' : '';
      const hl = lang ? hlLine(line, lang) : esc(line);
      const hunkIdx = isChanged && window._viewLineToHunk ? window._viewLineToHunk[n] : undefined;
      const hoverAttr = hunkIdx !== undefined ? ` onmouseenter="showDiffPopover(event,${hunkIdx})" onmouseleave="hideDiffPopover()"` : '';
      return `<tr${cls}><td class="vln"${hoverAttr}>${n}</td><td class="vgutter"></td><td class="vcode">${hl}</td></tr>`;
    }).join('');

    // Store hunk data for popover
    const chData = getChangedLines(filepath);
    window._viewHunks = chData.hunks || [];
    window._viewLineToHunk = chData.lineToHunk || {};
    window._viewLang = lang;

    const fn = filepath.replace(/'/g, "\\'");
    content.innerHTML = `
      <div class="file-viewer-header">
        <span class="fv-path">${esc(filepath)}</span>
        <button onclick="startWorkspaceEdit('${fn}')">Edit</button>
      </div>
      <div class="file-viewer-body">
        <table class="view-table">${rows}</table>
      </div>`;

    // Store content for edit mode
    window._workspaceFileContent = fileContent;
  }

  function startWorkspaceEdit(filepath) {
    workspaceEditMode = true;
    const content = document.getElementById('content');
    const fn = filepath.replace(/'/g, "\\'");
    content.innerHTML = `
      <div class="file-viewer-header">
        <span class="fv-path">${esc(filepath)}</span>
        <button class="btn-edit-active">Editing</button>
      </div>
      <div class="file-viewer-body">
        <textarea id="workspaceEditor" spellcheck="false">${esc(window._workspaceFileContent || '')}</textarea>
      </div>
      <div class="file-viewer-actions">
        <button class="btn-save" onclick="saveWorkspaceFile('${fn}')">Save</button>
        <button class="btn-cancel" onclick="openWorkspaceFile('${fn}')">Cancel</button>
      </div>`;
    // Tab support
    const ta = document.getElementById('workspaceEditor');
    ta.addEventListener('keydown', function(e) {
      if (e.key === 'Tab') {
        e.preventDefault();
        const s = this.selectionStart, end = this.selectionEnd;
        this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
        this.selectionStart = this.selectionEnd = s + 4;
      }
    });
    ta.focus();
  }

  async function saveWorkspaceFile(filepath) {
    const ta = document.getElementById('workspaceEditor');
    if (!ta || !currentRepo) return;
    try {
      const res = await fetch('/api/file', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo: _activeRepoFileRoot(), path: filepath, content: ta.value }),
      });
      const result = await res.json();
      if (!res.ok) { alert(result.detail || 'Error saving'); return; }
      diffCache = { uncommitted: null, branch: null };
      window._workspaceFileContent = ta.value;
      openWorkspaceFile(filepath);
    } catch (err) {
      alert('Error: ' + err.message);
    }
  }

  // ─── Notebook rendering ───
  function isNotebook(filepath) { return filepath.endsWith('.ipynb'); }

  function _normalizeAbsolutePath(path) {
    const raw = String(path || '');
    if (!raw.startsWith('/')) return null;
    const parts = [];
    raw.split('/').forEach((part) => {
      if (!part || part === '.') return;
      if (part === '..') {
        if (parts.length) parts.pop();
        return;
      }
      parts.push(part);
    });
    return '/' + parts.join('/');
  }

  // Notebook APIs deliberately accept only paths relative to the notebook's
  // owning vault. Workspace paths, however, are absolute. In a cross-vault
  // tab this root may differ from the shell's LAB_VAULT_ROOT, so callers can
  // pass the owning catalog path. Never strip until containment is checked.
  function _vaultRelativeNotebookPath(workspacePath, filepath, owningVaultRoot = VAULT_ROOT) {
    const vaultRoot = _normalizeAbsolutePath(owningVaultRoot);
    const workspaceRoot = _normalizeAbsolutePath(workspacePath);
    const file = String(filepath || '');
    if (!vaultRoot) throw new Error('Notebook vault root is unavailable');
    if (!workspaceRoot || !file || file.startsWith('/')) {
      throw new Error('Invalid notebook path');
    }
    if (file.split('/').some((part) => part === '..')) {
      throw new Error('Notebook path traversal is not allowed');
    }

    const combined = _normalizeAbsolutePath(workspaceRoot + '/' + file);
    const rootPrefix = vaultRoot === '/' ? '/' : vaultRoot + '/';
    if (!combined || !combined.startsWith(rootPrefix)) {
      throw new Error('Notebook is outside its owning vault');
    }
    const relative = combined.slice(rootPrefix.length);
    if (!relative || relative.startsWith('/')
        || relative.split('/').some((part) => part === '..')) {
      throw new Error('Invalid vault-relative notebook path');
    }
    return relative;
  }

  function _vaultRelativeNotebookPathOrNull(workspacePath, filepath, owningVaultRoot = VAULT_ROOT) {
    try { return _vaultRelativeNotebookPath(workspacePath, filepath, owningVaultRoot); }
    catch (_) { return null; }
  }

  function _notebookVaultContext(workspace = currentWorkspace) {
    const vaultId = typeof _workspaceVaultId === 'function'
      ? _workspaceVaultId(workspace) : null;
    const vault = typeof _vaultForWorkspace === 'function'
      ? _vaultForWorkspace(workspace) : null;
    return {
      vaultId: vaultId || null,
      vaultRoot: (vault && vault.path)
        || (workspace && workspace.vault_path) || VAULT_ROOT,
    };
  }

  function _renderNbOutput(output) {
    const o = output || {};
    const displayId = o.display_id ? ` data-display-id="${escAttr(String(o.display_id))}"` : '';
    const streamName = o.stream_name ? ` data-stream-name="${escAttr(String(o.stream_name))}"` : '';
    const attrs = ` data-output-type="${escAttr(String(o.type || 'text'))}"${displayId}${streamName}`;
    if (o.type === 'image') {
      return `<div class="nb-output"${attrs}><img src="data:image/png;base64,${escAttr(o.content || '')}"></div>`;
    }
    if (o.type === 'html') {
      return `<div class="nb-output-html"${attrs}>${o.content || ''}</div>`;
    }
    if (o.type === 'error') {
      return `<div class="nb-output nb-output-error"${attrs}>${esc(o.content || '')}</div>`;
    }
    const stderrCls = o.stream_name === 'stderr' ? ' nb-output-stderr' : '';
    return `<div class="nb-output${stderrCls}"${attrs}>${esc(o.content || '')}</div>`;
  }

  function _renderNbPinCodeButton() {
    return `<button class="nb-code-pin" type="button" data-nb-pin-code aria-pressed="false" title="Keep this code visible while code is hidden">Pin code</button>`;
  }

  function renderNotebookCell(cell, status, index = null) {
    const statusCls = status && status !== 'unchanged' ? ` nb-${status}` : '';
    const statusLabel = status && status !== 'unchanged'
      ? `<span class="nb-status nb-status-${status}">${status}</span>` : '';
    const execCount = cell.execution_count ? `[${cell.execution_count}]` : '';
    const metadata = cell.metadata || {};
    const actor = metadata.lab_actor === 'agent' || metadata.lab_actor === 'human'
      ? metadata.lab_actor : '';
    const action = metadata.lab_action === 'modified' || metadata.lab_action === 'created'
      ? metadata.lab_action : '';
    const actorBadge = actor
      ? `<span class="nb-cell-actor nb-cell-actor-${actor}">${actor}${action ? ` · ${action}` : ''}</span>`
      : '';
    const durationMs = Number(metadata.lab_duration_ms);
    const timingBadge = Number.isFinite(durationMs)
      ? `<span class="nb-cell-timing nb-cell-finished">finished in ${_formatNbElapsed(durationMs)}</span>`
      : '';

    let bodyHtml = '';
    if (cell.cell_type === 'markdown') {
      try {
        bodyHtml = `<div class="nb-markdown">${LabMarkdown.render(cell.source)}</div>`;
      } catch (e) {
        bodyHtml = `<div class="nb-source">${esc(cell.source)}</div>`;
      }
    } else {
      const lang = 'python';
      const lines = cell.source.split('\n');
      const highlighted = lines.map(l => hlLine(l, lang)).join('\n');
      bodyHtml = `<div class="nb-source">${highlighted}</div>`;
    }

    // Outputs
    let outputsHtml = '';
    if (cell.outputs && cell.outputs.length > 0) {
      const outs = cell.outputs.map(_renderNbOutput).join('');
      outputsHtml = `<div class="nb-outputs">
        ${outs}
      </div>`;
    }

    const indexAttr = Number.isInteger(index) ? ` data-cell-index="${index}"` : '';
    const cellIdAttr = cell.id ? ` data-cell-id="${escAttr(String(cell.id))}"` : '';
    const outputStateCls = outputsHtml ? ' nb-cell-has-outputs' : ' nb-cell-no-outputs';
    const cellTypeAttr = ` data-cell-type="${escAttr(String(cell.cell_type || 'cell'))}"`;
    const codeHeaderActions = cell.cell_type === 'code'
      ? `<div class="nb-cell-actions">${_renderNbPinCodeButton()}</div>`
      : '';
    return `<div class="nb-cell${statusCls}${outputStateCls}"${indexAttr}${cellIdAttr}${cellTypeAttr}>
      <div class="nb-cell-header">
        <span class="nb-type">${cell.cell_type}</span>
        <span class="nb-exec">${execCount}</span>
        ${actorBadge}
        ${timingBadge}
        ${statusLabel}
        ${codeHeaderActions}
      </div>
      ${bodyHtml}
      ${outputsHtml}
    </div>`;
  }

  // Interactive (Jupyter-style) cell rendering. Each code cell gets an
  // inline textarea + Run/Delete buttons; outputs appear right below it.
  // A trailing "+ Add cell" button creates pending draft cells that aren't
  // committed to .ipynb until the first Run — but ARE persisted in
  // localStorage so they survive tab switches / re-renders.
  function _cellDraftKey(relPath, cellKey) { return 'nb-draft:' + relPath + ':' + cellKey; }
  function _pendingKey(relPath) { return 'nb-pending:' + relPath; }
  function _readPending(relPath) {
    try {
      const raw = localStorage.getItem(_pendingKey(relPath));
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch (_) { return []; }
  }
  function _writePending(relPath, list) {
    try {
      if (!list || list.length === 0) localStorage.removeItem(_pendingKey(relPath));
      else localStorage.setItem(_pendingKey(relPath), JSON.stringify(list));
    } catch (_) {}
  }
  function _appendPending(relPath, code, insertAt) {
    const list = _readPending(relPath);
    const id = 'p' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8);
    const item = { id, code: code || '' };
    if (insertAt != null && !isNaN(insertAt)) item.insertAt = insertAt;
    list.push(item);
    _writePending(relPath, list);
    return id;
  }
  function _updatePending(relPath, id, code) {
    const list = _readPending(relPath);
    const item = list.find(x => x && x.id === id);
    if (!item) return;
    item.code = code;
    _writePending(relPath, list);
  }
  function _removePending(relPath, id) {
    _writePending(relPath, _readPending(relPath).filter(x => x && x.id !== id));
  }

  // Cell-magic detection. The first line of a code cell is treated as a magic
  // marker when it matches ``%%<lang>`` — most importantly ``%%sql`` so the
  // SQL query body below it lights up with the SQL hljs grammar instead of
  // python. Extend the table here if you start using more cell magics.
  function _detectCellLang(source) {
    const first = ((source || '').split('\n', 1)[0] || '').trim();
    if (/^%%sql\b/.test(first))                    return { lang: 'sql', skipFirst: true };
    if (/^%%(bash|shell|sh)\b/.test(first))        return { lang: 'bash', skipFirst: true };
    if (/^%%(javascript|js)\b/.test(first))        return { lang: 'javascript', skipFirst: true };
    if (/^%%html\b/.test(first))                   return { lang: 'xml', skipFirst: true };
    if (/^%%r\b/.test(first))                      return { lang: 'r', skipFirst: true };
    if (/^%%(?:cypher|json|yaml)\b/.test(first)) {
      const m = first.match(/^%%(\w+)/);
      return { lang: m ? m[1] : 'plaintext', skipFirst: true };
    }
    return { lang: 'python', skipFirst: false };
  }
  function _highlightCellSource(source) {
    if (typeof hljs === 'undefined') return esc(source || '');
    if (!source) return '';
    const { lang, skipFirst } = _detectCellLang(source);
    const lines = source.split('\n');
    if (!skipFirst) {
      return hlLine(source, lang);
    }
    const magic = '<span class="hljs-meta">' + esc(lines[0]) + '</span>';
    const rest = lines.slice(1).join('\n');
    if (!rest) return magic;
    return magic + '\n' + hlLine(rest, lang);
  }

  // Per-cell output collapse state. Keyed by (path, index); cleared en masse
  // when cells are deleted (indices shift). Pending cells have no committed
  // index so they don't participate.
  function _collapseKey(relPath, cellKey) { return 'nb-collapse:' + relPath + ':' + cellKey; }
  function _isOutputCollapsed(relPath, cellKey) {
    try { return localStorage.getItem(_collapseKey(relPath, cellKey)) === '1'; }
    catch (_) { return false; }
  }
  function _setOutputCollapsed(relPath, cellKey, collapsed) {
    try {
      if (collapsed) localStorage.setItem(_collapseKey(relPath, cellKey), '1');
      else localStorage.removeItem(_collapseKey(relPath, cellKey));
    } catch (_) {}
  }

  // "Seen" state per cell — used to highlight new outputs the user hasn't
  // acknowledged yet (handy when Claude Code or a parallel run writes the
  // .ipynb in the background). The stored value is the highest exec count
  // the user has clicked through; if a render sees a higher count, the cell
  // gets a green-bordered "NEW" badge until the user clicks the outputs.
  function _seenKey(relPath, cellKey) { return 'nb-seen:' + relPath + ':' + cellKey; }
  function _baselineSeenIfNew(relPath, cellKey, execCount) {
    if (execCount == null) return;
    try {
      if (localStorage.getItem(_seenKey(relPath, cellKey)) == null) {
        localStorage.setItem(_seenKey(relPath, cellKey), String(execCount));
      }
    } catch (_) {}
  }
  function _isCellSeen(relPath, cellKey, execCount) {
    if (execCount == null) return true;
    try {
      const stored = localStorage.getItem(_seenKey(relPath, cellKey));
      // No baseline yet means this cell has never been seen in this
      // notebook view. Two cases produce that:
      //   (a) Initial open — _baselineSeenIfNew has already run before us
      //       and stamped the current count, so we won't actually reach
      //       this branch with stored==null in practice.
      //   (b) A brand-new cell that appeared after the initial open (e.g.
      //       the user just hit Run on an empty cell, and the watcher
      //       re-rendered before the user clicked the output to ack).
      // For (b), the cell has output and the user has NOT acknowledged
      // it → it should show the green NEW edge. Treating null as "seen"
      // (the old behavior) suppressed the indicator on every cell's very
      // first run.
      if (stored == null) return false;
      return parseInt(stored, 10) >= execCount;
    } catch (_) { return true; }
  }
  function _markCellSeen(relPath, cellKey, execCount) {
    if (execCount == null) return;
    try { localStorage.setItem(_seenKey(relPath, cellKey), String(execCount)); } catch (_) {}
  }
  function _clearAllSeenForPath(relPath) {
    try {
      const prefix = 'nb-seen:' + relPath + ':';
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) keys.push(k);
      }
      keys.forEach(k => localStorage.removeItem(k));
    } catch (_) {}
  }

  // Per-notebook reading position. Large notebooks can grow and have cells
  // inserted in the middle, so persist both the stable nbformat cell id and
  // its last-known index. The id wins on restore; the index is a graceful
  // fallback for older notebooks (or when the saved cell was deleted).
  function _notebookPositionKey(scope, path) {
    return 'nb-position:' + String(scope || '') + '|' + String(path || '');
  }
  function _readNotebookPosition(scope, path) {
    try {
      const raw = localStorage.getItem(_notebookPositionKey(scope, path));
      if (!raw) return null;
      const saved = JSON.parse(raw);
      if (!saved || typeof saved !== 'object') return null;
      const index = saved.index == null ? NaN : Number(saved.index);
      return {
        cellId: saved.cellId ? String(saved.cellId) : '',
        index: Number.isInteger(index) && index >= 0 ? index : null,
      };
    } catch (_) { return null; }
  }
  function _writeNotebookPosition(scope, path, cell) {
    if (!cell) return;
    const indexAttr = cell.getAttribute('data-cell-index');
    const rawIndex = indexAttr == null ? NaN : Number(indexAttr);
    const index = Number.isInteger(rawIndex) && rawIndex >= 0 ? rawIndex : null;
    const cellId = cell.getAttribute('data-cell-id') || '';
    if (!cellId && index == null) return;
    try {
      localStorage.setItem(
        _notebookPositionKey(scope, path),
        JSON.stringify({ cellId, index }),
      );
    } catch (_) {}
  }

  function _notebookCodeHiddenKey(scope, path) {
    return 'nb-hide-code:' + String(scope || '') + '|' + String(path || '');
  }
  function _isNotebookCodeHidden(scope, path) {
    try { return localStorage.getItem(_notebookCodeHiddenKey(scope, path)) === '1'; }
    catch (_) { return false; }
  }
  function _setNotebookCodeHidden(scope, path, hidden) {
    try { localStorage.setItem(_notebookCodeHiddenKey(scope, path), hidden ? '1' : '0'); }
    catch (_) {}
  }

  function _notebookPinnedCodeKey(scope, path) {
    return 'nb-pinned-code:' + String(scope || '') + '|' + String(path || '');
  }
  function _readNotebookPinnedCode(scope, path) {
    try {
      const raw = localStorage.getItem(_notebookPinnedCodeKey(scope, path));
      const saved = raw ? JSON.parse(raw) : [];
      return Array.isArray(saved)
        ? saved.filter(key => typeof key === 'string' && key.length > 0)
        : [];
    } catch (_) { return []; }
  }
  function _notebookCellPinKey(cell) {
    if (!cell) return '';
    const cellId = cell.getAttribute('data-cell-id');
    if (cellId) return 'id:' + cellId;
    const index = cell.getAttribute('data-cell-index');
    return index != null && index !== '' && index !== 'new' ? 'index:' + index : '';
  }
  function _setNotebookCodePinned(scope, path, cell, pinned) {
    const key = _notebookCellPinKey(cell);
    if (!key) return false;
    const saved = new Set(_readNotebookPinnedCode(scope, path));
    if (pinned) saved.add(key);
    else saved.delete(key);
    try {
      const storageKey = _notebookPinnedCodeKey(scope, path);
      if (saved.size) localStorage.setItem(storageKey, JSON.stringify(Array.from(saved)));
      else localStorage.removeItem(storageKey);
    } catch (_) {}
    return saved.has(key);
  }
  function _syncNotebookCodePinCell(cell, pinned) {
    if (!cell) return;
    cell.classList.toggle('nb-code-pinned', !!pinned);
    cell.querySelectorAll('[data-nb-pin-code]').forEach((button) => {
      button.textContent = pinned ? 'Unpin code' : 'Pin code';
      button.title = pinned
        ? 'Remove this fixed code slot'
        : 'Keep this code visible while code is hidden';
      button.setAttribute('aria-pressed', pinned ? 'true' : 'false');
    });
  }
  function _applyNotebookCodePins(notebook, scope, path) {
    if (!notebook) return;
    const saved = new Set(_readNotebookPinnedCode(scope, path));
    notebook.querySelectorAll('.nb-cell[data-cell-type="code"]').forEach((cell) => {
      _syncNotebookCodePinCell(cell, saved.has(_notebookCellPinKey(cell)));
    });
  }

  // The active cell is browser-session state, not another persistent pin.
  // Remember its stable id so live notebook re-renders keep the user's
  // selection while pinned and running cells continue to occupy fixed slots.
  let _nbActiveCodeCell = null;
  function _rememberNotebookActiveCodeCell(scope, path, cell) {
    const key = _notebookCellPinKey(cell);
    if (!key) return null;
    _nbActiveCodeCell = {
      scope: String(scope || ''),
      path: String(path || ''),
      key,
    };
    return cell;
  }
  function _restoreNotebookActiveCodeCell(notebook, scope, path) {
    if (!notebook || !_nbActiveCodeCell
        || _nbActiveCodeCell.scope !== String(scope || '')
        || _nbActiveCodeCell.path !== String(path || '')) return null;
    return Array.from(notebook.querySelectorAll('.nb-cell[data-cell-type="code"]'))
      .find(cell => _notebookCellPinKey(cell) === _nbActiveCodeCell.key) || null;
  }

  function _setNotebookCodePeek(notebook, target) {
    if (!notebook) return null;
    notebook.querySelectorAll('.nb-cell.nb-code-peek').forEach((cell) => {
      cell.classList.remove('nb-code-peek');
    });
    if (!target) return null;
    target.classList.add('nb-code-peek');
    return target;
  }

  function _activateNotebookCodeCell(notebook, eventTarget, scope, path, reveal) {
    if (!notebook || !eventTarget || typeof eventTarget.closest !== 'function') return null;
    const cell = eventTarget.closest('.nb-cell[data-cell-type="code"]');
    if (!cell) return null;
    _rememberNotebookActiveCodeCell(scope, path, cell);
    if (reveal) _setNotebookCodePeek(notebook, cell);
    return cell;
  }

  function _notebookCommittedCells(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll('.nb-container > .nb-cell[data-cell-index]'))
      .filter(cell => cell.getAttribute('data-cell-index') !== 'new');
  }

  function _notebookReadingCell(cells) {
    if (!cells || !cells.length) return null;
    // The fixed Lab chrome occupies roughly the top 128px. Treat the last
    // cell whose top has crossed a reading line just below it as the current
    // cell. This remains stable while reading a tall output within one cell.
    const readingLine = Math.min(
      Math.max(0, window.innerHeight - 1),
      Math.max(140, Math.round(window.innerHeight * 0.22)),
    );
    let current = cells[0];
    for (const cell of cells) {
      const rect = cell.getBoundingClientRect();
      if (rect.top <= readingLine) current = cell;
      else break;
    }
    return current;
  }

  function _resolveNotebookPosition(cells, saved) {
    if (!cells || !cells.length) return null;
    if (saved && saved.cellId) {
      const byId = cells.find(cell => cell.getAttribute('data-cell-id') === saved.cellId);
      if (byId) return byId;
    }
    if (saved && saved.index != null) {
      const byIndex = cells.find(
        cell => Number(cell.getAttribute('data-cell-index')) === saved.index,
      );
      if (byIndex) return byIndex;
      return cells[Math.min(saved.index, cells.length - 1)];
    }
    return cells[0];
  }

  function _notebookRunningCell(notebook) {
    if (!notebook) return null;
    const running = Array.from(
      notebook.querySelectorAll('.nb-cell-interactive.nb-cell-running'),
    );
    return running.find(cell => cell.getAttribute('data-queue-pos') === '1')
      || running[0] || null;
  }

  function _nbToolbarTooltipElement() {
    return document.getElementById('nbToolbarTooltip');
  }

  function _nbHideToolbarTooltip() {
    const tooltip = _nbToolbarTooltipElement();
    if (!tooltip) return;
    const anchor = tooltip._nbAnchor;
    if (anchor && anchor.removeAttribute) anchor.removeAttribute('aria-describedby');
    tooltip._nbAnchor = null;
    tooltip.hidden = true;
    tooltip.textContent = '';
  }

  function _nbShowToolbarTooltip(anchor) {
    const tooltip = _nbToolbarTooltipElement();
    const label = anchor && anchor.getAttribute('data-nb-tooltip');
    if (!tooltip || !label) {
      _nbHideToolbarTooltip();
      return;
    }
    if (tooltip._nbAnchor && tooltip._nbAnchor !== anchor) {
      tooltip._nbAnchor.removeAttribute('aria-describedby');
    }
    // Native `title` tooltips wait for a dwell timer. Render this fixed
    // tooltip synchronously so pointer and keyboard users get the label as
    // soon as they reach an icon, without being clipped by the toolbar.
    tooltip._nbAnchor = anchor;
    tooltip.textContent = label;
    tooltip.hidden = false;
    tooltip.style.left = '0px';
    tooltip.style.top = '0px';
    anchor.setAttribute('aria-describedby', 'nbToolbarTooltip');
    const anchorRect = anchor.getBoundingClientRect();
    const tipRect = tooltip.getBoundingClientRect();
    const gap = 6;
    const centered = ((anchorRect.left + anchorRect.right) / 2) - (tipRect.width / 2);
    const left = Math.max(gap, Math.min(centered, window.innerWidth - tipRect.width - gap));
    let top = anchorRect.bottom + gap;
    if (top + tipRect.height > window.innerHeight - gap) {
      top = Math.max(gap, anchorRect.top - tipRect.height - gap);
    }
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
  }

  function _nbSetToolbarButtonLabel(button, label) {
    if (!button) return;
    button.setAttribute('data-nb-tooltip', label);
    button.setAttribute('aria-label', label);
    const tooltip = _nbToolbarTooltipElement();
    if (tooltip && !tooltip.hidden && tooltip._nbAnchor === button) {
      _nbShowToolbarTooltip(button);
    }
  }

  function _bindNbToolbarTooltips(controls) {
    if (!controls) return;
    controls.querySelectorAll('button[data-nb-tooltip]').forEach((button) => {
      button.addEventListener('pointerenter', () => _nbShowToolbarTooltip(button));
      button.addEventListener('pointerleave', _nbHideToolbarTooltip);
      button.addEventListener('focus', () => _nbShowToolbarTooltip(button));
      button.addEventListener('blur', _nbHideToolbarTooltip);
      button.addEventListener('click', _nbHideToolbarTooltip);
    });
  }

  function _renderNbJumpControls(cellCount, codeHidden = false, actionsHtml = '') {
    const disabled = cellCount > 0 ? '' : ' disabled';
    const label = cellCount > 0 ? `1 / ${cellCount}` : '0 / 0';
    const codeLabel = codeHidden ? 'Code hidden — show all code' : 'Code visible — hide all code';
    return `<nav class="nb-jump-controls" aria-label="Notebook controls">
      <button type="button" data-nb-jump="start" data-nb-tooltip="Go to first cell" aria-label="Go to first cell"${disabled}><span aria-hidden="true">↑</span></button>
      <span class="nb-jump-position" aria-live="polite">${label}</span>
      <button type="button" data-nb-jump="end" data-nb-tooltip="Go to last cell" aria-label="Go to last cell"${disabled}><span aria-hidden="true">↓</span></button>
      <button type="button" class="nb-jump-running" data-nb-jump-running data-nb-tooltip="Go to running cell" aria-label="Go to running cell" hidden><span class="nb-jump-running-dot" aria-hidden="true"></span></button>
      <button type="button" data-nb-toggle-code data-nb-tooltip="${codeLabel}" aria-label="${codeLabel}" aria-pressed="${codeHidden ? 'true' : 'false'}"><span aria-hidden="true">&lt;/&gt;</span></button>
      ${actionsHtml}
    </nav><div class="nb-jump-controls-spacer" aria-hidden="true"></div>`;
  }

  let _nbNavigationCleanup = null;
  let _nbNavigationRefreshRunning = null;
  function _clearNbNavigation() {
    if (_nbNavigationCleanup) _nbNavigationCleanup();
    _nbHideToolbarTooltip();
    _nbNavigationCleanup = null;
    _nbNavigationRefreshRunning = null;
  }

  function _bindNbNavigation(container, scope, path, { restore = true } = {}) {
    _clearNbNavigation();
    const cells = _notebookCommittedCells(container);
    const notebook = container && container.querySelector('.nb-container');
    const controls = container && container.querySelector('.nb-jump-controls');
    const positionLabel = controls && controls.querySelector('.nb-jump-position');
    const codeToggle = controls && controls.querySelector('[data-nb-toggle-code]');
    const runningButton = controls && controls.querySelector('[data-nb-jump-running]');
    let codeHidden = _isNotebookCodeHidden(scope, path);

    _applyNotebookCodePins(notebook, scope, path);

    let frame = null;
    let active = true;
    function navigableCells() {
      if (!codeHidden) return cells;
      const visible = cells.filter((cell) => (
        cell.getAttribute('data-cell-type') !== 'code'
        || cell.classList.contains('nb-cell-has-outputs')
        || cell.classList.contains('nb-cell-pending')
        || cell.classList.contains('nb-cell-running')
        || cell.classList.contains('nb-code-pinned')
      ));
      return visible.length ? visible : cells;
    }
    function applyCodeHidden(hidden) {
      codeHidden = !!hidden;
      if (notebook) notebook.classList.toggle('nb-code-hidden', codeHidden);
      if (codeHidden) {
        _setNotebookCodePeek(
          notebook,
          _restoreNotebookActiveCodeCell(notebook, scope, path),
        );
      } else {
        _setNotebookCodePeek(notebook, null);
      }
      if (codeToggle) {
        const label = codeHidden ? 'Code hidden — show all code' : 'Code visible — hide all code';
        codeToggle.innerHTML = '<span aria-hidden="true">&lt;/&gt;</span>';
        _nbSetToolbarButtonLabel(codeToggle, label);
        codeToggle.setAttribute('aria-pressed', codeHidden ? 'true' : 'false');
      }
    }
    function record(cell) {
      if (!cell) return;
      _writeNotebookPosition(scope, path, cell);
      if (positionLabel) {
        const idx = cells.indexOf(cell);
        if (idx >= 0) positionLabel.textContent = `${idx + 1} / ${cells.length}`;
      }
    }
    function recordCurrent() {
      frame = null;
      if (!active || !container.isConnected) return;
      record(_notebookReadingCell(navigableCells()));
    }
    function scheduleRecord() {
      if (frame == null) frame = requestAnimationFrame(recordCurrent);
    }
    function jump(cell, block) {
      if (!cell) return;
      record(cell);
      cell.scrollIntoView({ behavior: 'smooth', block });
    }
    function refreshRunningControl() {
      if (!runningButton) return;
      const running = _notebookRunningCell(notebook);
      runningButton.hidden = !running;
      if (!running) return;
      const idx = cells.indexOf(running);
      const suffix = idx >= 0 ? ` ${idx + 1} of ${cells.length}` : '';
      _nbSetToolbarButtonLabel(runningButton, `Go to running cell${suffix}`);
    }

    applyCodeHidden(codeHidden);
    refreshRunningControl();
    _bindNbToolbarTooltips(controls);
    _nbNavigationRefreshRunning = refreshRunningControl;
    if (controls) {
      const start = controls.querySelector('[data-nb-jump="start"]');
      const end = controls.querySelector('[data-nb-jump="end"]');
      if (start) start.addEventListener('click', () => {
        const visible = navigableCells();
        jump(visible[0], 'start');
      });
      if (end) end.addEventListener('click', () => {
        const visible = navigableCells();
        jump(visible[visible.length - 1], 'end');
      });
      if (runningButton) runningButton.addEventListener('click', () => {
        jump(_notebookRunningCell(notebook), 'start');
      });
      if (codeToggle) codeToggle.addEventListener('click', () => {
        const before = _notebookReadingCell(navigableCells());
        const beforeIndex = Math.max(0, cells.indexOf(before));
        applyCodeHidden(!codeHidden);
        _setNotebookCodeHidden(scope, path, codeHidden);
        const visible = navigableCells();
        const target = visible.find(cell => cells.indexOf(cell) >= beforeIndex)
          || visible[visible.length - 1];
        requestAnimationFrame(() => {
          if (!active || !target) return;
          target.scrollIntoView({ behavior: 'auto', block: 'start' });
          record(target);
        });
      });
    }
    let activateCodeCell = null;
    if (notebook) {
      activateCodeCell = (event) => {
        const cell = _activateNotebookCodeCell(
          notebook, event.target, scope, path, codeHidden,
        );
        if (cell) record(cell);
      };
      notebook.addEventListener('click', activateCodeCell);
      notebook.addEventListener('focusin', activateCodeCell);
      notebook.querySelectorAll('[data-nb-pin-code]').forEach((button) => {
        button.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          const cell = button.closest('.nb-cell[data-cell-type="code"]');
          if (!cell) return;
          const wasPeek = cell.classList.contains('nb-code-peek');
          const pinned = _setNotebookCodePinned(
            scope, path, cell, !cell.classList.contains('nb-code-pinned'),
          );
          _syncNotebookCodePinCell(cell, pinned);
          // Unpinning a fixed cell turns it into the one transient open slot.
          // If it was already that slot, keep it open; otherwise replace the
          // prior transient peek so unpinned cells remain accordion-like.
          if (!pinned && codeHidden && !wasPeek) {
            _setNotebookCodePeek(notebook, cell);
          }
          record(cell);
        });
      });
    }
    if (!cells.length) return null;
    window.addEventListener('scroll', scheduleRecord, { passive: true });
    window.addEventListener('resize', scheduleRecord, { passive: true });

    if (restore) {
      // Let the newly-injected cell DOM settle before scrolling, then reopen
      // at the most recently read cell (or the first cell on a notebook that
      // has no saved position yet). Running work never steals the viewport;
      // the blue Running control is the explicit jump affordance.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (!active || !container.isConnected) return;
        const resolved = _resolveNotebookPosition(
          cells, _readNotebookPosition(scope, path),
        );
        const visible = navigableCells();
        const resolvedIndex = Math.max(0, cells.indexOf(resolved));
        const target = visible.includes(resolved)
          ? resolved
          : (visible.find(cell => cells.indexOf(cell) >= resolvedIndex)
            || visible[visible.length - 1]);
        if (target) {
          target.scrollIntoView({ behavior: 'auto', block: 'start' });
          record(target);
        }
      }));
    } else {
      scheduleRecord();
    }

    _nbNavigationCleanup = () => {
      if (!active) return;
      // Capture the latest position before a tab switch replaces this DOM.
      record(_notebookReadingCell(navigableCells()));
      active = false;
      if (frame != null) cancelAnimationFrame(frame);
      window.removeEventListener('scroll', scheduleRecord);
      window.removeEventListener('resize', scheduleRecord);
      if (notebook && activateCodeCell) {
        notebook.removeEventListener('click', activateCodeCell);
        notebook.removeEventListener('focusin', activateCodeCell);
      }
    };
    return { recordCurrent };
  }

  function _formatNbElapsed(milliseconds) {
    const totalSeconds = Math.max(0, Number(milliseconds) || 0) / 1000;
    if (totalSeconds < 60) {
      return `${totalSeconds.toFixed(totalSeconds < 10 ? 1 : 0)}s`;
    }
    const wholeSeconds = Math.floor(totalSeconds);
    const hours = Math.floor(wholeSeconds / 3600);
    const minutes = Math.floor((wholeSeconds % 3600) / 60);
    const seconds = wholeSeconds % 60;
    if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`;
    return `${minutes}m ${seconds}s`;
  }

  let _nbElapsedTicker = null;
  function _updateNbElapsedTimers() {
    const timers = Array.from(document.querySelectorAll('[data-nb-started-at-ms]'));
    const now = Date.now();
    timers.forEach((timer) => {
      const startedAt = Number(timer.getAttribute('data-nb-started-at-ms'));
      if (!Number.isFinite(startedAt)) return;
      timer.textContent = `running · ${_formatNbElapsed(now - startedAt)}`;
    });
    if (!timers.length && _nbElapsedTicker != null) {
      clearInterval(_nbElapsedTicker);
      _nbElapsedTicker = null;
    }
  }

  function _ensureNbElapsedTicker() {
    _updateNbElapsedTimers();
    if (_nbElapsedTicker == null && document.querySelector('[data-nb-started-at-ms]')) {
      _nbElapsedTicker = setInterval(_updateNbElapsedTimers, 250);
    }
  }

  function renderNbCellInteractive(cell, index, relPath, opts) {
    opts = opts || {};
    // `opts.pending` is a client-side draft (Run button not yet sent).
    // `cell.metadata.lab_pending` is server-side: the nb_exec endpoint
    // wrote a placeholder while the Jupyter call is in flight. Both get
    // the same .nb-cell-pending visual frame so the user can't tell
    // which side started the run — the "[*]" gutter + running CSS look
    // identical.
    const serverPending = !!(cell && cell.metadata && cell.metadata.lab_pending === true);
    const clientPending = !!opts.pending;
    const pending = clientPending || serverPending;
    const isCode = cell.cell_type === 'code';
    const metadata = (cell && cell.metadata) || {};
    const actor = metadata.lab_actor === 'agent' || metadata.lab_actor === 'human'
      ? metadata.lab_actor : '';
    const action = metadata.lab_action === 'modified' || metadata.lab_action === 'created'
      ? metadata.lab_action : '';
    const actorBadge = actor
      ? `<span class="nb-cell-actor nb-cell-actor-${actor}" title="This cell was ${action || 'executed'} by ${actor === 'agent' ? 'an' : 'a'} ${actor}">${actor}${action ? ` · ${action}` : ''}</span>`
      : '';
    const startedAtMs = Number(metadata.lab_started_at) * 1000;
    const durationMs = Number(metadata.lab_duration_ms);
    const timingBadge = serverPending && Number.isFinite(startedAtMs)
      ? `<span class="nb-cell-timing" data-nb-started-at-ms="${startedAtMs}">running · ${_formatNbElapsed(Date.now() - startedAtMs)}</span>`
      : (!serverPending && Number.isFinite(durationMs)
        ? `<span class="nb-cell-timing nb-cell-finished">finished in ${_formatNbElapsed(durationMs)}</span>`
        : '');
    // For server-side pending cells, prefer the queue position passed in
    // by the caller (1, 2, 3 in submission order) over the bare [*]
    // placeholder. The number gives the user immediate insight into
    // how many cells are queued and which one will run first.
    const execCount = serverPending
      ? (opts.queuePos ? `[${opts.queuePos}]` : '[*]')
      : (cell.execution_count ? `[${cell.execution_count}]` : (isCode ? '[ ]' : ''));

    // Outputs — same shape as renderNotebookCell. Markdown cells skip outputs.
    // Collapsible header lets the user hide noisy pip-install / log spam;
    // state persists per (path, index) via localStorage.
    let outputsHtml = '';
    if (isCode && cell.outputs && cell.outputs.length > 0) {
      const outs = cell.outputs.map(_renderNbOutput).join('');
      const collapsed = !pending && _isOutputCollapsed(relPath, cell.id || index);
      const lineCount = cell.outputs.reduce((n, o) => n + ((o.content || '').split('\n').length), 0);
      const summary = collapsed
        ? `<span class="nb-outputs-summary"> · ${cell.outputs.length} output${cell.outputs.length === 1 ? '' : 's'}, ${lineCount} line${lineCount === 1 ? '' : 's'} hidden</span>`
        : '';
      outputsHtml = `<div class="nb-outputs${collapsed ? ' nb-outputs-collapsed' : ''}">
        <div class="nb-outputs-toggle" title="Click to ${collapsed ? 'show' : 'hide'} output">
          <span class="nb-outputs-caret">${collapsed ? '▶' : '▼'}</span> Output${summary}
          <button class="nb-outputs-copy" type="button" title="Copy output to clipboard">⧉ copy</button>
        </div>
        <div class="nb-outputs-body">${outs}</div>
      </div>`;
    }

    // Markdown stays read-only for now — edit is code-only in v1.
    if (!isCode) {
      let bodyHtml = '';
      try { bodyHtml = `<div class="nb-markdown">${LabMarkdown.render(cell.source)}</div>`; }
      catch (e) { bodyHtml = `<div class="nb-source">${esc(cell.source)}</div>`; }
      const markdownCellIdAttr = cell.id ? ` data-cell-id="${escAttr(String(cell.id))}"` : '';
      return `<div class="nb-cell nb-cell-interactive nb-cell-no-outputs" data-cell-index="${index}"${markdownCellIdAttr} data-cell-type="markdown">
        <div class="nb-cell-header">
          <span class="nb-type">${cell.cell_type}</span>
        </div>
        ${bodyHtml}
        ${outputsHtml}
      </div>`;
    }

    // Code cell: editable textarea + Run/Delete. Draft restoration happens
    // post-render in bindNbCellInteractive so we don't try to read
    // localStorage during innerHTML assembly.
    const source = cell.source || '';
    const rowsHint = Math.max(2, Math.min(20, source.split('\n').length));
    // Two distinct pending states with different visuals:
    //   nb-cell-pending → client-side DRAFT (typed but not sent yet)
    //   nb-cell-running → server-side RUNNING (placeholder while Jupyter
    //                     is executing). Persistent blue glow + "running"
    //                     label instead of dashed grey + "draft".
    const pendingCls = serverPending ? ' nb-cell-running' : (opts.pending ? ' nb-cell-pending' : '');
    const actorCls = actor ? ` nb-cell-${actor}` : '';
    const idxAttr = clientPending ? 'new' : String(index);
    const pendingId = clientPending ? (opts.pendingId || '') : '';
    const pendingAttr = pendingId ? ` data-pending-id="${esc(pendingId)}"` : '';
    // A server-running cell is already a committed nbformat cell with a
    // stable id. Keep that id/index in the DOM so live WebSocket deltas can
    // target it while it runs; only browser-local drafts use index="new".
    const cellIdAttr = (!clientPending && cell.id) ? ` data-cell-id="${esc(cell.id)}"` : '';
    const pendingInsertAt = (clientPending && opts.insertAt != null) ? String(opts.insertAt) : '';
    const insertAtAttr = pendingInsertAt !== '' ? ` data-insert-at="${pendingInsertAt}"` : '';
    const liveSequence = Number(opts.liveSequence);
    const liveSequenceAttr = Number.isFinite(liveSequence)
      ? ` data-live-sequence="${liveSequence}"` : '';
    const queuePos = Number(opts.queuePos);
    const queuePosAttr = Number.isInteger(queuePos) && queuePos > 0
      ? ` data-queue-pos="${queuePos}"` : '';
    const highlighted = _highlightCellSource(source);
    const execCountNum = (cell.execution_count != null) ? cell.execution_count : '';
    const unseen = !pending && outputsHtml && !_isCellSeen(relPath, cell.id || index, cell.execution_count);
    const unseenCls = unseen ? ' nb-cell-unseen' : '';
    const newBadge = unseen
      ? `<span class="nb-cell-new-badge" title="New outputs — click anywhere on the output to acknowledge">NEW</span>`
      : '';
    const serverBusyAttr = serverPending ? ' disabled' : '';
    const serverReadonlyAttr = serverPending ? ' readonly aria-busy="true"' : '';
    const outputStateCls = outputsHtml ? ' nb-cell-has-outputs' : ' nb-cell-no-outputs';
    return `<div class="nb-cell nb-cell-interactive${pendingCls}${unseenCls}${actorCls}${outputStateCls}" data-cell-index="${idxAttr}"${cellIdAttr}${pendingAttr}${insertAtAttr}${liveSequenceAttr}${queuePosAttr} data-exec-count="${execCountNum}" data-cell-type="code">
      <div class="nb-cell-header">
        <span class="nb-type">code</span>
        <span class="nb-exec">${execCount}</span>
        ${actorBadge}
        ${timingBadge}
        ${newBadge}
        <div class="nb-cell-actions">
          <span class="nb-cell-busy" style="display:none">running…</span>
          <button class="nb-cell-copy-src" type="button" title="Copy cell source to clipboard">⧉ copy</button>
          ${clientPending ? '' : _renderNbPinCodeButton()}
          <button class="nb-cell-run" type="button" title="Run (Cmd/Ctrl+Enter)"${serverBusyAttr}>▶ Run</button>
          <button class="nb-cell-del" type="button" title="${pending ? 'Discard draft' : 'Delete cell'}"${serverBusyAttr}>✕</button>
        </div>
      </div>
      <div class="nb-cell-edit-wrap">
        <pre class="nb-cell-edit-highlight hljs" aria-hidden="true"><code class="hljs">${highlighted}</code></pre>
        <textarea class="nb-cell-edit-area" spellcheck="false" rows="${rowsHint}"${serverReadonlyAttr}
          placeholder="${pending ? 'Type code, then Cmd/Ctrl+Enter or click Run…' : ''}">${esc(source)}</textarea>
      </div>
      ${outputsHtml}
    </div>`;
  }

  function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved, vaultId = null) {
    if (!wrap || !wrap.classList.contains('nb-cell-interactive')) return;
    const ta = wrap.querySelector('.nb-cell-edit-area');
    if (!ta) return;  // markdown cell
    const runBtn = wrap.querySelector('.nb-cell-run');
    const delBtn = wrap.querySelector('.nb-cell-del');
    const busy = wrap.querySelector('.nb-cell-busy');
    const idxAttr = wrap.getAttribute('data-cell-index');
    const isPending = idxAttr === 'new';
    const isServerRunning = wrap.classList.contains('nb-cell-running');
    const cellIndex = isPending ? null : parseInt(idxAttr, 10);
    const cellId = wrap.getAttribute('data-cell-id') || null;
    const cellKey = cellId || cellIndex;
    const pendingId = wrap.getAttribute('data-pending-id') || null;

    // Restore in-flight draft. Committed cells use a per-index draft key;
    // pending cells persist via the path-scoped pending list so they survive
    // navigation away and back.
    const draftKey = isPending ? null : _cellDraftKey(relPath, cellKey);
    let localRunOutputSnapshot = null;
    const idleExecText = wrap.querySelector('.nb-exec')?.textContent || '';
    // While an agent/human execution is live, the server snapshot is the code
    // actually running. Keep any unsaved browser draft in localStorage, but do
    // not let it visually replace that source until the run has completed.
    if (draftKey && !isServerRunning) {
      try {
        const draft = localStorage.getItem(draftKey);
        if (draft != null) ta.value = draft;
      } catch (_) {}
    }
    // Repaint the overlay later if draft restoration changed ta.value — the
    // initial render baked the on-disk source, not the draft.
    var _draftDiffersFromDisk = (draftKey != null && ta.value !== ta.defaultValue);
    // Live syntax-highlight overlay: re-render the <pre> behind the textarea
    // whenever the user types. The textarea text is transparent (caret only),
    // so the overlay is what the user sees as "the code".
    const highlightCode = wrap.querySelector('.nb-cell-edit-highlight code');
    function _repaintHighlight() {
      if (!highlightCode) return;
      highlightCode.innerHTML = _highlightCellSource(ta.value);
    }
    function _syncOverlayScroll() {
      const pre = wrap.querySelector('.nb-cell-edit-highlight');
      if (!pre) return;
      pre.scrollTop = ta.scrollTop;
      pre.scrollLeft = ta.scrollLeft;
    }
    if (highlightCode && _draftDiffersFromDisk) _repaintHighlight();
    ta.addEventListener('scroll', _syncOverlayScroll);
    ta.addEventListener('input', () => {
      if (isPending && pendingId) {
        _updatePending(relPath, pendingId, ta.value);
      } else if (draftKey) {
        try { localStorage.setItem(draftKey, ta.value); } catch (_) {}
      }
      _repaintHighlight();
    });

    function _showLocalRunningOutput() {
      const existing = wrap.querySelector(':scope > .nb-outputs');
      // Keep the old output node alive (but hidden) until the server's
      // authoritative running snapshot replaces this cell.  If the request
      // itself fails, unhiding the same node preserves its toggle/copy event
      // listeners as well as the prior rich output DOM.
      localRunOutputSnapshot = { existing };
      const placeholder = `<div class="nb-outputs" data-local-running-output="true">
        <div class="nb-outputs-toggle nb-outputs-live-label">
          <span class="nb-outputs-caret">▼</span> Output · live
        </div>
        <div class="nb-outputs-body"><div class="nb-output nb-output-local-running" role="status"><span class="nb-running-spinner" aria-hidden="true"></span><span>Starting execution… first output will stream here.</span></div></div>
      </div>`;
      if (existing) {
        existing.hidden = true;
        existing.insertAdjacentHTML('beforebegin', placeholder);
      } else {
        wrap.insertAdjacentHTML('beforeend', placeholder);
      }
    }

    function _restoreLocalRunningOutput() {
      if (!localRunOutputSnapshot) return;
      const placeholder = wrap.querySelector(':scope > .nb-outputs[data-local-running-output="true"]');
      if (placeholder) placeholder.remove();
      if (localRunOutputSnapshot.existing) localRunOutputSnapshot.existing.hidden = false;
      localRunOutputSnapshot = null;
    }

    function setRunning(on) {
      runBtn.disabled = on;
      delBtn.disabled = on;
      ta.readOnly = on;
      if (on) ta.setAttribute('aria-busy', 'true');
      else ta.removeAttribute('aria-busy');
      busy.style.display = on ? '' : 'none';
      if (on) {
        busy.setAttribute('data-nb-started-at-ms', String(Date.now()));
        busy.textContent = 'running · 0.0s';
        const gutter = wrap.querySelector('.nb-exec');
        if (gutter) gutter.textContent = '[*]';
        _showLocalRunningOutput();
        _ensureNbElapsedTicker();
      } else {
        busy.removeAttribute('data-nb-started-at-ms');
        busy.textContent = 'running…';
        const gutter = wrap.querySelector('.nb-exec');
        if (gutter) gutter.textContent = idleExecText;
        _restoreLocalRunningOutput();
      }
      wrap.classList.toggle('nb-cell-running', on);
      if (_nbNavigationRefreshRunning) _nbNavigationRefreshRunning();
      _clearCellError(wrap);
    }

    async function run() {
      const code = ta.value || '';
      if (!code.trim()) return;
      setRunning(true);
      // Read insertAt off the DOM — pending cells produced by an "insert
      // between cells" click carry it. Cells with no insertAt append.
      let insertAt = NaN;
      if (isPending) {
        insertAt = parseInt(wrap.getAttribute('data-insert-at') || '', 10);
      }
      try {
        const body = { path: relPath, code, actor: 'human' };
        if (vaultId) body.vault = vaultId;
        if (cellId) body.cell_id = cellId;
        else if (cellIndex != null) body.cell_index = cellIndex;
        else if (!isNaN(insertAt)) body.insert_at = insertAt;
        const res = await fetch('/api/nb/exec', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const e = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(e.detail || ('exec failed (' + res.status + ')'));
        }
        if (draftKey) { try { localStorage.removeItem(draftKey); } catch (_) {} }
        // Inserting shifts every subsequent cell's index by 1 — drop all
        // per-cell drafts and seen markers for this path so stale code or
        // stale baselines don't reappear at the wrong position.
        if (!isNaN(insertAt)) {
          _clearAllDraftsForPath(relPath);
          _clearAllSeenForPath(relPath);
        }
        // Successful Run on a pending cell promotes it to a committed cell —
        // remove from pending storage before re-render so it's not duplicated.
        if (isPending && pendingId) _removePending(relPath, pendingId);
        openWorkspaceDoc(filepath, { preserveScroll: true });
      } catch (err) {
        _showCellError(wrap, err.message || String(err));
        setRunning(false);
      }
    }

    // Two-step delete confirmation. First click on ✕ swaps the button into a
    // "⚠ Click again" state for 3s; the second click within that window
    // actually deletes. Auto-resets after the timeout or if the user runs
    // the cell instead. Empty pending drafts skip the confirm — there's
    // nothing to lose.
    let _delConfirmTimer = null;
    function _resetDeleteButton() {
      delBtn.textContent = '✕';
      delBtn.classList.remove('nb-cell-del-confirming');
      delBtn.title = isPending ? 'Discard draft' : 'Delete cell';
      if (_delConfirmTimer) { clearTimeout(_delConfirmTimer); _delConfirmTimer = null; }
    }
    function _armDeleteConfirm(label, hint) {
      delBtn.classList.add('nb-cell-del-confirming');
      delBtn.textContent = label;
      delBtn.title = hint;
      if (_delConfirmTimer) clearTimeout(_delConfirmTimer);
      _delConfirmTimer = setTimeout(_resetDeleteButton, 3000);
    }
    // If the user starts editing the textarea after arming, dismiss the
    // pending confirm — they clearly didn't mean to delete.
    ta.addEventListener('input', _resetDeleteButton, { passive: true });

    async function del() {
      const armed = delBtn.classList.contains('nb-cell-del-confirming');
      if (isPending) {
        const hasContent = (ta.value || '').trim() !== '';
        // Empty draft → discard outright. With content → require a second
        // click so a fat-finger doesn't wipe what the user typed.
        if (hasContent && !armed) {
          _armDeleteConfirm('⚠ Discard?', 'Click again within 3s to discard this draft');
          return;
        }
        _resetDeleteButton();
        if (pendingId) _removePending(relPath, pendingId);
        wrap.parentNode && wrap.parentNode.removeChild(wrap);
        if (typeof onPendingRemoved === 'function') onPendingRemoved();
        return;
      }
      // Committed cell — always two-step. The first click arms; the second
      // (within 3s) actually rewrites the .ipynb.
      if (!armed) {
        _armDeleteConfirm('⚠ Click again', 'Click again within 3s to delete this cell — this rewrites the .ipynb');
        return;
      }
      _resetDeleteButton();
      setRunning(true);
      try {
        const res = await fetch('/api/nb/cell/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(cellId
            ? { path: relPath, cell_id: cellId, ...(vaultId ? {vault: vaultId} : {}) }
            : { path: relPath, cell_index: cellIndex, ...(vaultId ? {vault: vaultId} : {}) }),
        });
        if (!res.ok) {
          const e = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(e.detail || ('delete failed (' + res.status + ')'));
        }
        // Deletion shifts indices; safest to clear all per-cell drafts AND
        // seen markers for this notebook so stale code/baselines don't
        // reappear at the wrong index.
        _clearAllDraftsForPath(relPath);
        _clearAllSeenForPath(relPath);
        openWorkspaceDoc(filepath, { preserveScroll: true });
      } catch (err) {
        _showCellError(wrap, err.message || String(err));
        setRunning(false);
      }
    }

    runBtn.addEventListener('click', run);
    delBtn.addEventListener('click', del);
    ta.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        run();
      }
    });

    // Output collapse toggle (only for committed cells with real outputs).
    const outputsWrap = wrap.querySelector(':scope > .nb-outputs');
    const toggle = outputsWrap && outputsWrap.querySelector('.nb-outputs-toggle');
    if (toggle && !isPending) {
      toggle.addEventListener('click', (e) => {
        // Output action buttons should not also fold the output panel.
        if (e.target.closest('.nb-outputs-copy')) return;
        const nowCollapsed = !outputsWrap.classList.contains('nb-outputs-collapsed');
        outputsWrap.classList.toggle('nb-outputs-collapsed', nowCollapsed);
        const caret = toggle.querySelector('.nb-outputs-caret');
        if (caret) caret.textContent = nowCollapsed ? '▶' : '▼';
        let summary = toggle.querySelector('.nb-outputs-summary');
        if (nowCollapsed && !summary) {
          const body = outputsWrap.querySelector('.nb-outputs-body');
          const lines = body ? body.textContent.split('\n').length : 0;
          const items = body ? body.children.length : 0;
          summary = document.createElement('span');
          summary.className = 'nb-outputs-summary';
          summary.textContent = ` · ${items} output${items === 1 ? '' : 's'}, ${lines} line${lines === 1 ? '' : 's'} hidden`;
          toggle.insertBefore(summary, toggle.querySelector('.nb-outputs-copy'));
        } else if (!nowCollapsed && summary) {
          summary.remove();
        }
        _setOutputCollapsed(relPath, cellKey, nowCollapsed);
      });
    }

    // Copy source to clipboard.
    const copySrcBtn = wrap.querySelector('.nb-cell-copy-src');
    if (copySrcBtn) {
      copySrcBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await _copyToClipboard(ta.value || '', copySrcBtn);
      });
    }

    // Copy outputs to clipboard. Concatenates all text/error outputs with
    // newlines; images and HTML are flagged in the copied string so the user
    // knows they were skipped.
    const copyOutBtn = outputsWrap && outputsWrap.querySelector('.nb-outputs-copy');
    if (copyOutBtn) {
      copyOutBtn.addEventListener('click', async (e) => {
        e.stopPropagation();  // don't fold/expand the output panel
        const body = outputsWrap.querySelector('.nb-outputs-body');
        await _copyToClipboard(_outputsToText(body), copyOutBtn);
      });
    }

    // "Unseen" indicator dismissal — clicking anywhere on the outputs area
    // marks them as seen and removes the green highlight.
    if (outputsWrap && !isPending && wrap.classList.contains('nb-cell-unseen')) {
      const execCount = parseInt(wrap.getAttribute('data-exec-count') || 'NaN', 10);
      outputsWrap.addEventListener('click', () => {
        if (!wrap.classList.contains('nb-cell-unseen')) return;
        wrap.classList.remove('nb-cell-unseen');
        const badge = wrap.querySelector('.nb-cell-new-badge');
        if (badge) badge.remove();
        if (!isNaN(execCount)) _markCellSeen(relPath, cellKey, execCount);

        // When this was the LAST unseen cell in the notebook, also clear
        // the sidebar's blue "new outputs" dot. The dot is driven by the
        // file-level `_nbGetLastViewed` timestamp (compared against the
        // notebook's mtime). Stamping now means the next sidebar refresh
        // computes `mtime > lastViewed` as false → dot disappears. We
        // also yank the dot from the DOM immediately so the user sees
        // the result without waiting for the next mtime poll tick.
        const stillUnseen = document.querySelector('.nb-cell-unseen');
        if (!stillUnseen) {
          _nbMarkViewed(filepath, Date.now() / 1000);
          document
            .querySelectorAll(`.sidebar-file[data-filepath="${CSS.escape(filepath)}"] .nb-unseen-dot`)
            .forEach(el => el.remove());
        }
      }, { once: false });
    }
  }

  // Generic clipboard helper with brief "✓ copied" feedback on the triggering
  // button. Falls back to execCommand for legacy contexts where Clipboard API
  // isn't available (e.g. http localhost without isSecureContext).
  async function _copyToClipboard(text, btn) {
    let ok = false;
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(text);
        ok = true;
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { ok = document.execCommand('copy'); }
        finally { document.body.removeChild(ta); }
      }
    } catch (_) { ok = false; }
    if (!btn) return ok;
    const original = btn.textContent;
    btn.textContent = ok ? '✓ copied' : '✗ copy failed';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1200);
    return ok;
  }

  // Flatten the rendered outputs DOM into something useful in a paste buffer.
  function _outputsToText(bodyEl) {
    if (!bodyEl) return '';
    const parts = [];
    bodyEl.querySelectorAll(':scope > *').forEach((el) => {
      if (el.classList.contains('nb-output-html')) {
        parts.push('[html output — copy from the page or use the raw .ipynb]');
      } else if (el.querySelector('img')) {
        parts.push('[image output — see the rendered cell]');
      } else {
        parts.push(el.textContent || '');
      }
    });
    return parts.join('\n');
  }

  function _showCellError(wrap, msg) {
    _clearCellError(wrap);
    const err = document.createElement('div');
    err.className = 'nb-cell-error-msg';
    err.textContent = msg;
    wrap.appendChild(err);
  }
  function _clearCellError(wrap) {
    const old = wrap.querySelector(':scope > .nb-cell-error-msg');
    if (old) old.remove();
  }
  function _clearAllDraftsForPath(relPath) {
    try {
      const prefix = 'nb-draft:' + relPath + ':';
      const keys = [];
      for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        if (k && k.indexOf(prefix) === 0) keys.push(k);
      }
      keys.forEach(k => localStorage.removeItem(k));
    } catch (_) {}
  }

  // "+ Add cell" button — pushes a new draft to the path-scoped pending list
  // (persisted in localStorage so the cell survives tab switches and
  // re-renders). Multiple pending cells are allowed; another can be created
  // while one is still running.
  function renderNbAddCellButton() {
    return `<div class="nb-add-cell-wrap">
      <button class="nb-add-cell-btn" type="button">+ Add cell</button>
    </div>`;
  }

  function _nbRuntimeLines(values) {
    return (Array.isArray(values) ? values : []).join('\n');
  }

  function renderNbRuntimePanel(runtime, relPath) {
    const spec = (runtime && runtime.spec) || {
      version: 1, mode: 'local', kind: 'managed', python: '', packages: [],
      editable: [], imports: [], cli_paths: [], cli_checks: [], environment: {},
      working_dir: '.', validation_code: '',
    };
    const status = (runtime && runtime.status) || 'unconfigured';
    const activePython = runtime && runtime.active && runtime.active.python;
    return `<dialog class="nb-runtime-dialog">
      <form method="dialog" class="nb-runtime-card">
        <div class="nb-runtime-title"><div><strong>Workspace Runtime</strong><span>Shared by people and agents</span></div><button value="cancel" class="nb-runtime-close" title="Close">✕</button></div>
        <p class="nb-runtime-help">Choose the exact Python environment for this workspace. Libraries that invoke CLI commands inherit the configured CLI paths inside the Jupyter kernel.</p>
        <div class="nb-runtime-grid">
          <label>Environment<select name="kind"><option value="managed"${spec.kind === 'managed' ? ' selected' : ''}>Managed by Lab</option><option value="existing"${spec.kind === 'existing' ? ' selected' : ''}>Existing Python</option></select></label>
          <label class="nb-runtime-span">Python version or executable<input name="python" value="${esc(spec.python || '')}" placeholder="3.12, python3, or /absolute/path/to/python"></label>
          <label>Working directory<input name="working_dir" value="${esc(spec.working_dir || '.')}" placeholder="."></label>
          <label>CLI directories<textarea name="cli_paths" rows="3" placeholder="tools/bin\nclients/acme/bin">${esc(_nbRuntimeLines(spec.cli_paths))}</textarea></label>
          <label>Python packages<textarea name="packages" rows="5" placeholder="pandas==2.3.2\npolars>=1.0">${esc(_nbRuntimeLines(spec.packages))}</textarea></label>
          <label>Editable local libraries<textarea name="editable" rows="5" placeholder="libs/client_sdk">${esc(_nbRuntimeLines(spec.editable))}</textarea></label>
          <label>Required imports<textarea name="imports" rows="4" placeholder="pandas\nclient_sdk">${esc(_nbRuntimeLines(spec.imports))}</textarea></label>
          <label>CLI checks (JSON)<textarea name="cli_checks" rows="4" placeholder='[{"command":"client-cli","args":["--version"]}]'>${esc(JSON.stringify(spec.cli_checks || [], null, 2))}</textarea></label>
          <label class="nb-runtime-span">Environment variables (JSON)<textarea name="environment" rows="3" placeholder='{"DATA_PROFILE":"prod"}'>${esc(JSON.stringify(spec.environment || {}, null, 2))}</textarea></label>
          <label class="nb-runtime-span">Extra validation code<textarea name="validation_code" rows="3" placeholder="from client_sdk import healthcheck\nassert healthcheck()">${esc(spec.validation_code || '')}</textarea></label>
        </div>
        <div class="nb-runtime-current"><span>Status: <strong>${esc(status)}</strong></span>${activePython ? `<span title="Active interpreter">${esc(activePython)}</span>` : ''}</div>
        <pre class="nb-runtime-log" hidden></pre>
        <div class="nb-runtime-actions"><button type="button" class="nb-runtime-save">Save</button><button type="button" class="nb-runtime-build">Build &amp; validate in Jupyter</button></div>
      </form>
    </dialog>`;
  }

  function bindNbRuntimePanel(container, relPath, filepath, vaultId = null) {
    const openBtn = container.querySelector('.nb-runtime-open');
    const dialog = container.querySelector('.nb-runtime-dialog');
    if (!openBtn || !dialog) return;
    openBtn.addEventListener('click', () => dialog.showModal());
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) dialog.close();
    });
    const saveBtn = dialog.querySelector('.nb-runtime-save');
    const buildBtn = dialog.querySelector('.nb-runtime-build');
    const log = dialog.querySelector('.nb-runtime-log');

    function lines(name) {
      return (dialog.querySelector(`[name="${name}"]`).value || '')
        .split('\n').map(v => v.trim()).filter(Boolean);
    }
    function readJson(name, fallback) {
      const raw = (dialog.querySelector(`[name="${name}"]`).value || '').trim();
      return raw ? JSON.parse(raw) : fallback;
    }
    function readSpec() {
      const cliChecks = readJson('cli_checks', []);
      const environment = readJson('environment', {});
      if (!Array.isArray(cliChecks)) throw new Error('CLI checks must be a JSON array');
      if (!environment || Array.isArray(environment) || typeof environment !== 'object') throw new Error('Environment variables must be a JSON object');
      return {
        version: 1,
        mode: 'local',
        kind: dialog.querySelector('[name="kind"]').value,
        python: dialog.querySelector('[name="python"]').value.trim(),
        packages: lines('packages'), editable: lines('editable'), imports: lines('imports'),
        cli_paths: lines('cli_paths'), cli_checks: cliChecks, environment,
        working_dir: dialog.querySelector('[name="working_dir"]').value.trim() || '.',
        validation_code: dialog.querySelector('[name="validation_code"]').value,
      };
    }
    function showLog(message, isError) {
      log.hidden = false;
      log.classList.toggle('nb-runtime-log-error', !!isError);
      log.textContent = message;
    }
    async function save() {
      const spec = readSpec();
      const res = await fetch('/api/nb/runtime', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: relPath, spec, ...(vaultId ? {vault: vaultId} : {}) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
      return data;
    }
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true; buildBtn.disabled = true;
      try {
        const data = await save();
        showLog(`Saved workspace runtime. Status: ${data.status}`, false);
      } catch (err) {
        showLog(err.message || String(err), true);
      } finally {
        saveBtn.disabled = false; buildBtn.disabled = false;
      }
    });
    buildBtn.addEventListener('click', async () => {
      saveBtn.disabled = true; buildBtn.disabled = true;
      buildBtn.textContent = 'Building & validating…';
      try {
        await save();
        const res = await fetch('/api/nb/runtime/build', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: relPath, ...(vaultId ? {vault: vaultId} : {}) }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail || {};
          throw new Error([detail.message || detail, detail.log || ''].filter(Boolean).join('\n\n'));
        }
        showLog((data.built && data.built.log) || 'Runtime is ready. Import and CLI checks passed inside Jupyter.', false);
        setTimeout(() => { dialog.close(); openWorkspaceDoc(filepath, { preserveScroll: true }); }, 700);
      } catch (err) {
        showLog(err.message || String(err), true);
      } finally {
        saveBtn.disabled = false; buildBtn.disabled = false;
        buildBtn.textContent = 'Build & validate in Jupyter';
      }
    });
  }

  async function _requestNbKernelRestart(relPath, vaultId = null) {
    const res = await fetch('/api/nb/session/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path: relPath, ...(vaultId ? {vault: vaultId} : {}) }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(data.detail || ('restart failed (' + res.status + ')'));
    }
    return res.json().catch(() => ({}));
  }

  const _nbRunAllState = new Map();

  function _nbRunAllKey(relPath, vaultId = null) {
    return `${String(vaultId || '')}::${String(relPath || '')}`;
  }

  function _nbRunAllPresentation(state, restartFirst) {
    if (!state || state.restartFirst !== restartFirst) {
      return restartFirst
        ? { label: 'Restart kernel and run all cells', html: '<span aria-hidden="true">↻▶</span>' }
        : { label: 'Run all cells', html: '<span aria-hidden="true">▶▶</span>' };
    }
    if (state.phase === 'restarting') {
      return { label: 'Restarting kernel', html: '<span aria-hidden="true">↻…</span>' };
    }
    const label = `Running cell ${state.current} of ${state.total}`;
    const icon = restartFirst ? '↻▶' : '▶';
    return {
      label,
      html: `<span aria-hidden="true">${icon}</span><span class="nb-toolbar-progress">${state.current}/${state.total}</span>`,
    };
  }

  function renderNbRunAllButtons(relPath, vaultId, codeCellCount, kernelBusy = false) {
    const state = _nbRunAllState.get(_nbRunAllKey(relPath, vaultId));
    const disabled = state || kernelBusy || codeCellCount < 1 ? ' disabled' : '';
    const run = _nbRunAllPresentation(state, false);
    const restart = _nbRunAllPresentation(state, true);
    return `<button class="nb-run-all" type="button" data-nb-tooltip="${run.label}" aria-label="${run.label}"${disabled}>${run.html}</button>
      <button class="nb-restart-run-all" type="button" data-nb-tooltip="${restart.label}" aria-label="${restart.label}"${disabled}>${restart.html}</button>`;
  }

  function _syncNbRunAllButtons(container, state = null) {
    const runBtn = container.querySelector('.nb-run-all');
    const restartBtn = container.querySelector('.nb-restart-run-all');
    if (!runBtn || !restartBtn) return;
    runBtn.disabled = !!state;
    restartBtn.disabled = !!state;
    const restartOnlyBtn = container.querySelector('.nb-restart-kernel');
    if (restartOnlyBtn) restartOnlyBtn.disabled = !!state;
    const run = _nbRunAllPresentation(state, false);
    const restart = _nbRunAllPresentation(state, true);
    runBtn.innerHTML = run.html;
    _nbSetToolbarButtonLabel(runBtn, run.label);
    restartBtn.innerHTML = restart.html;
    _nbSetToolbarButtonLabel(restartBtn, restart.label);
  }

  function _nbExecutionError(result) {
    const outputs = result && result.cell && Array.isArray(result.cell.outputs)
      ? result.cell.outputs : [];
    const error = outputs.find(output => output
      && (output.type === 'error' || output.output_type === 'error'));
    if (!error) return null;
    const detail = String(error.content || error.evalue || error.ename || 'cell execution failed')
      .split('\n').find(line => line.trim()) || 'cell execution failed';
    return detail.slice(0, 240);
  }

  function bindNbRunAll(container, relPath, filepath, vaultId = null) {
    const runBtn = container.querySelector('.nb-run-all');
    const restartBtn = container.querySelector('.nb-restart-run-all');
    if (!runBtn || !restartBtn) return;

    async function runAll(restartFirst) {
      const key = _nbRunAllKey(relPath, vaultId);
      if (_nbRunAllState.has(key)) return;
      const cells = Array.from(
        container.querySelectorAll('.nb-cell-interactive[data-cell-type="code"]'),
      ).filter(cell => cell.getAttribute('data-cell-index') !== 'new').map((cell) => {
        const textarea = cell.querySelector('.nb-cell-edit-area');
        return {
          code: textarea ? textarea.value : '',
          cellId: cell.getAttribute('data-cell-id') || null,
          cellIndex: parseInt(cell.getAttribute('data-cell-index') || '', 10),
        };
      }).filter(cell => cell.code.trim() && (cell.cellId || Number.isInteger(cell.cellIndex)));
      if (!cells.length) {
        alert('There are no non-empty code cells to run.');
        return;
      }
      if (restartFirst && !confirm(
        `Restart the kernel and run ${cells.length} code cell${cells.length === 1 ? '' : 's'}? All variables will be wiped.`,
      )) return;

      const state = {
        restartFirst,
        phase: restartFirst ? 'restarting' : 'running',
        current: restartFirst ? 0 : 1,
        total: cells.length,
      };
      _nbRunAllState.set(key, state);
      _syncNbRunAllButtons(container, state);
      let failure = null;
      try {
        if (restartFirst) {
          await _requestNbKernelRestart(relPath, vaultId);
          state.phase = 'running';
        }
        for (let index = 0; index < cells.length; index += 1) {
          state.current = index + 1;
          _syncNbRunAllButtons(container, state);
          const cell = cells[index];
          const body = { path: relPath, code: cell.code, actor: 'human' };
          if (vaultId) body.vault = vaultId;
          if (cell.cellId) body.cell_id = cell.cellId;
          else body.cell_index = cell.cellIndex;
          const res = await fetch('/api/nb/exec', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          const result = await res.json().catch(() => ({}));
          if (!res.ok) {
            throw new Error(result.detail || `cell ${index + 1} failed (${res.status})`);
          }
          try {
            localStorage.removeItem(_cellDraftKey(relPath, cell.cellId || cell.cellIndex));
          } catch (_) {}
          const executionError = _nbExecutionError(result);
          if (executionError) {
            throw new Error(`Cell ${index + 1} stopped Run all: ${executionError}`);
          }
        }
      } catch (err) {
        failure = err;
      } finally {
        _nbRunAllState.delete(key);
        _syncNbRunAllButtons(container, null);
        if (_currentOpenNotebookRelPath() === relPath
            && (!vaultId || vaultId === _workspaceVaultId(currentWorkspace))) {
          try {
            await openWorkspaceDoc(filepath, { preserveScroll: true });
          } catch (err) {
            if (!failure) failure = err;
          }
        }
      }
      if (failure) alert('Run all failed: ' + (failure.message || failure));
    }

    runBtn.addEventListener('click', () => runAll(false));
    restartBtn.addEventListener('click', () => runAll(true));
  }

  function bindNbInterruptKernel(container, relPath, vaultId = null) {
    const btn = container.querySelector('.nb-interrupt-kernel');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const originalHtml = btn.innerHTML;
      const originalLabel = btn.getAttribute('data-nb-tooltip') || 'Interrupt kernel';
      _nbSetToolbarButtonLabel(btn, 'Interrupting kernel');
      try {
        const res = await fetch('/api/nb/session/interrupt', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: relPath, ...(vaultId ? {vault: vaultId} : {}) }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `interrupt failed (${res.status})`);
        }
        btn.innerHTML = '<span aria-hidden="true">✓</span>';
        _nbSetToolbarButtonLabel(btn, 'Kernel interrupted');
      } catch (err) {
        alert('Kernel interrupt failed: ' + (err.message || err));
        btn.innerHTML = originalHtml;
        _nbSetToolbarButtonLabel(btn, originalLabel);
      } finally {
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          _nbSetToolbarButtonLabel(btn, originalLabel);
          btn.disabled = false;
        }, 1200);
      }
    });
  }

  async function bindNbRestartKernel(container, relPath, filepath, vaultId = null) {
    const btn = container.querySelector('.nb-restart-kernel');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      if (!confirm('Restart the kernel for this notebook? All variables will be wiped. Cells stay; you re-run them on the new kernel.')) return;
      btn.disabled = true;
      const originalHtml = btn.innerHTML;
      const originalLabel = btn.getAttribute('data-nb-tooltip') || 'Restart kernel';
      _nbSetToolbarButtonLabel(btn, 'Restarting kernel');
      try {
        await _requestNbKernelRestart(relPath, vaultId);
        btn.innerHTML = '<span aria-hidden="true">✓</span>';
        _nbSetToolbarButtonLabel(btn, 'Kernel restarted');
        setTimeout(() => {
          btn.innerHTML = originalHtml;
          _nbSetToolbarButtonLabel(btn, originalLabel);
          btn.disabled = false;
        }, 1500);
      } catch (err) {
        alert('Kernel restart failed: ' + (err.message || err));
        btn.innerHTML = originalHtml;
        _nbSetToolbarButtonLabel(btn, originalLabel);
        btn.disabled = false;
      }
    });
  }

  function bindNbAddCellButton(container, relPath, filepath, vaultId = null) {
    const btn = container.querySelector('.nb-add-cell-btn');
    const cellsHost = container.querySelector('.nb-container');
    if (!btn || !cellsHost) return;
    btn.addEventListener('click', () => {
      const id = _appendPending(relPath, '');
      const blank = { cell_type: 'code', source: '', outputs: [], execution_count: null };
      const html = renderNbCellInteractive(blank, -1, relPath, { pending: true, pendingId: id });
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      const node = tmp.firstElementChild;
      cellsHost.appendChild(node);
      bindNbCellInteractive(node, relPath, filepath, null, vaultId);
      const ta = node.querySelector('.nb-cell-edit-area');
      if (ta) ta.focus();
    });
  }

  // Hover-revealed "+ insert cell" bars between every pair of cells. Click
  // inserts a pending cell at that position (data-insert-at), which on Run
  // POSTs `insert_at` so the new cell lands between existing cells instead
  // of being appended at the end.
  function bindNbCellInserters(container, relPath, filepath, vaultId = null) {
    container.querySelectorAll('.nb-cell-insert-btn').forEach((btn) => {
      const inserter = btn.closest('.nb-cell-inserter');
      if (!inserter) return;
      const at = parseInt(inserter.getAttribute('data-insert-at') || '', 10);
      btn.addEventListener('click', (e) => {
        e.preventDefault();
        if (isNaN(at)) return;
        const id = _appendPending(relPath, '', at);
        const blank = { cell_type: 'code', source: '', outputs: [], execution_count: null };
        const html = renderNbCellInteractive(blank, -1, relPath, {
          pending: true, pendingId: id, insertAt: at,
        });
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        const node = tmp.firstElementChild;
        // Drop the new pending cell right after this inserter so it sits
        // exactly at the visual gap the user clicked.
        inserter.parentNode.insertBefore(node, inserter.nextElementSibling);
        bindNbCellInteractive(node, relPath, filepath, null, vaultId);
        const ta = node.querySelector('.nb-cell-edit-area');
        if (ta) ta.focus();
      });
    });
  }

  function renderNotebookCellDiff(diffCell) {
    if (diffCell.status === 'modified' && diffCell.base_cell) {
      // Show old and new source
      const lang = 'python';
      const oldLines = diffCell.base_cell.source.split('\n').map(l => hlLine(l, lang)).join('\n');
      const newLines = diffCell.cell.source.split('\n').map(l => hlLine(l, lang)).join('\n');

      let outputsHtml = '';
      if (diffCell.cell.outputs && diffCell.cell.outputs.length > 0) {
        const outs = diffCell.cell.outputs.map(o => {
          if (o.type === 'image') return `<div class="nb-output"><img src="data:image/png;base64,${o.content}"></div>`;
          if (o.type === 'error') return `<div class="nb-output nb-output-error">${esc(o.content)}</div>`;
          return `<div class="nb-output">${esc(o.content || '')}</div>`;
        }).join('');
        outputsHtml = `<div class="nb-outputs">${outs}</div>`;
      }

      return `<div class="nb-cell nb-modified">
        <div class="nb-cell-header">
          <span class="nb-type">${diffCell.cell.cell_type}</span>
          <span class="nb-exec">${diffCell.cell.execution_count ? '[' + diffCell.cell.execution_count + ']' : ''}</span>
          <span class="nb-status nb-status-modified">modified</span>
        </div>
        <div class="nb-source-old">${oldLines}</div>
        <div class="nb-source-new">${newLines}</div>
        ${outputsHtml}
      </div>`;
    }
    return renderNotebookCell(diffCell.cell || diffCell.base_cell, diffCell.status);
  }

  function _notebookLineDiffKinds(beforeText, afterText, forceChanged) {
    const beforeLines = String(beforeText || '').split('\n');
    const afterLines = String(afterText || '').split('\n');
    const beforeKinds = beforeLines.map(() => 'delete');
    const afterKinds = afterLines.map(() => 'add');

    if (!forceChanged && beforeText === afterText) {
      return {
        before: beforeKinds.map(() => 'context'),
        after: afterKinds.map(() => 'context'),
      };
    }

    // Avoid an unbounded quadratic allocation for generated, unusually large
    // cells. In that case the useful fallback is still honest: every line on
    // the old side is removed and every line on the new side is added.
    if (forceChanged || beforeLines.length * afterLines.length > 40000) {
      return {before: beforeKinds, after: afterKinds};
    }

    const lengths = Array.from(
      {length: beforeLines.length + 1},
      () => new Array(afterLines.length + 1).fill(0),
    );
    for (let beforeIndex = 1; beforeIndex <= beforeLines.length; beforeIndex++) {
      for (let afterIndex = 1; afterIndex <= afterLines.length; afterIndex++) {
        lengths[beforeIndex][afterIndex] = beforeLines[beforeIndex - 1] === afterLines[afterIndex - 1]
          ? lengths[beforeIndex - 1][afterIndex - 1] + 1
          : Math.max(lengths[beforeIndex - 1][afterIndex], lengths[beforeIndex][afterIndex - 1]);
      }
    }

    let beforeIndex = beforeLines.length;
    let afterIndex = afterLines.length;
    while (beforeIndex > 0 && afterIndex > 0) {
      if (beforeLines[beforeIndex - 1] === afterLines[afterIndex - 1]) {
        beforeKinds[beforeIndex - 1] = 'context';
        afterKinds[afterIndex - 1] = 'context';
        beforeIndex--;
        afterIndex--;
      } else if (lengths[beforeIndex - 1][afterIndex] >= lengths[beforeIndex][afterIndex - 1]) {
        beforeIndex--;
      } else {
        afterIndex--;
      }
    }
    return {before: beforeKinds, after: afterKinds};
  }

  function _renderNotebookHistoryOutputs(outputs, changeKind) {
    const changeClass = changeKind ? ` nb-history-output-${changeKind}` : '';
    if (!outputs || !outputs.length) {
      return `<div class="nb-history-no-output${changeClass}">No output</div>`;
    }
    return `<div class="nb-history-outputs${changeClass}"><div class="nb-history-output-label">Output</div>${outputs.map(output => {
      if (output.type === 'image') {
        return `<div class="nb-output"><img src="data:image/png;base64,${output.content}"></div>`;
      }
      if (output.type === 'html') {
        return `<div class="nb-output-html">${output.content}</div>`;
      }
      if (output.type === 'error') {
        return `<div class="nb-output nb-output-error">${esc(output.content || '')}</div>`;
      }
      return `<div class="nb-output">${esc(output.content || '')}</div>`;
    }).join('')}</div>`;
  }

  function _renderNotebookHistoryCodeSource(cell, lineKinds) {
    const source = String(cell.source || '');
    const lines = source.split('\n');
    const {lang, skipFirst} = _detectCellLang(source);
    return `<pre class="nb-history-source"><code>${lines.map((line, index) => {
      const kind = lineKinds[index] || 'context';
      const kindClass = kind === 'context' ? '' : ` nb-history-line-${kind}`;
      const highlighted = skipFirst && index === 0
        ? `<span class="hljs-meta">${esc(line)}</span>`
        : hlLine(line, lang);
      return `<span class="nb-history-line${kindClass}">${highlighted}</span>`;
    }).join('')}</code></pre>`;
  }

  function _renderNotebookHistorySide(cell, label, emptyLabel, lineKinds, outputChange) {
    if (!cell) {
      return `<section class="nb-history-side is-empty"><div class="nb-history-side-label">${label}</div><div class="nb-history-placeholder">${emptyLabel}</div></section>`;
    }
    const exec = cell.execution_count == null ? '' : `[${cell.execution_count}]`;
    let sourceHtml;
    if (cell.cell_type === 'markdown') {
      const changedKind = (lineKinds || []).find(kind => kind !== 'context');
      const changedClass = changedKind ? ` nb-history-markdown-${changedKind}` : '';
      try {
        sourceHtml = `<div class="nb-history-markdown${changedClass}">${LabMarkdown.render(cell.source || '')}</div>`;
      } catch (_) {
        sourceHtml = _renderNotebookHistoryCodeSource(cell, lineKinds || []);
      }
    } else {
      sourceHtml = _renderNotebookHistoryCodeSource(cell, lineKinds || []);
    }
    return `<section class="nb-history-side"><div class="nb-history-side-label"><span>${label}</span><span>${esc(cell.cell_type || 'code')} ${exec}</span></div>${sourceHtml}${_renderNotebookHistoryOutputs(cell.outputs, outputChange)}</section>`;
  }

  function renderNotebookHistoryDiff(notebook) {
    const cells = (notebook.cells || []).filter(cell => cell.status !== 'unchanged');
    if (!cells.length) {
      return '<div class="explorer-history-empty">No semantic notebook cell changes in this revision.</div>';
    }
    const beforeCount = Number(notebook.before_cells || 0);
    const afterCount = Number(notebook.after_cells || 0);
    const summary = `<div class="nb-history-summary"><strong>Notebook review</strong><span>${cells.length} changed cell${cells.length === 1 ? '' : 's'} · ${beforeCount} before → ${afterCount} after</span></div>`;
    return summary + `<div class="nb-history-cells">${cells.map(diffCell => {
      const status = String(diffCell.status || 'modified');
      const before = status === 'added' ? null : (diffCell.base_cell || diffCell.cell || null);
      const after = status === 'deleted' ? null : (diffCell.cell || null);
      const sourceDiff = _notebookLineDiffKinds(
        before ? before.source : '',
        after ? after.source : '',
        !!before && !!after && before.cell_type !== after.cell_type,
      );
      const outputsChanged = JSON.stringify(before ? (before.outputs || []) : [])
        !== JSON.stringify(after ? (after.outputs || []) : []);
      const beforeOutputChange = before && outputsChanged ? 'delete' : '';
      const afterOutputChange = after && outputsChanged ? 'add' : '';
      return `<article class="nb-history-cell nb-history-${escAttr(status.replace(/_/g, '-'))}">
        <div class="nb-history-cell-head"><span>Cell ${Number(diffCell.index || 0) + 1}</span><span>${esc(status.replace(/_/g, ' '))}</span></div>
        <div class="nb-history-grid">
          ${_renderNotebookHistorySide(before, 'Before', 'Cell did not exist', sourceDiff.before, beforeOutputChange)}
          ${_renderNotebookHistorySide(after, 'After', 'Cell was removed', sourceDiff.after, afterOutputChange)}
        </div>
      </article>`;
    }).join('')}</div>`;
  }
  window.renderNotebookHistoryDiff = renderNotebookHistoryDiff;

  // Browsers never execute <script> tags injected via innerHTML; Plotly
  // notebook outputs bundle <script> blocks that populate an otherwise-empty
  // <div id="..."> — so without this helper, the chart area stays blank. Walk
  // the inserted notebook subtree, clone each <script> as a live element, and
  // swap it in. Also shim `require(["plotly"], fn)` (Jupyter's requirejs
  // idiom) so the chart init script can find the Plotly global.
  // Plotly is intentionally lazy-loaded; if any cell script will call
  // `require(["plotly"], fn)`, load it and wait briefly before activating.
  function _waitForPlotly(root, timeoutMs) {
    var hasRequirePlotly = false;
    root.querySelectorAll('.nb-outputs script, .nb-output-html script').forEach(function (s) {
      if ((s.textContent || '').indexOf('require(["plotly"') !== -1
        || (s.textContent || '').indexOf("require(['plotly'") !== -1) {
        hasRequirePlotly = true;
      }
    });
    if (!hasRequirePlotly || window.Plotly) return Promise.resolve();
    return ensurePlotly().catch(function () {}).then(function () {
      if (window.Plotly) return;
      return new Promise(function (resolve) {
        var start = Date.now();
        (function poll() {
          if (window.Plotly) return resolve();
          if (Date.now() - start > (timeoutMs || 5000)) return resolve();
          setTimeout(poll, 50);
        })();
      });
    });
  }

  async function activateNotebookScripts(root) {
    if (!root) return;
    await _waitForPlotly(root, 5000);
    root.querySelectorAll('.nb-outputs script, .nb-output-html script').forEach(old => {
      const s = document.createElement('script');
      for (const a of old.attributes) s.setAttribute(a.name, a.value);
      if (old.textContent) s.text = old.textContent;
      old.parentNode.replaceChild(s, old);
    });
  }

  async function renderNotebookView(filepath) {
    _clearNbNavigation();
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading notebook...</div>';
    try {
      const res = await fetch(`/api/notebook?repo=${encodeURIComponent(_activeRepoFileRoot())}&path=${encodeURIComponent(filepath)}`);
      const cells = await res.json();
      await Promise.all([
        ensureMarked().catch(() => {}),
        ensureHighlight().catch(() => {}),
      ]);
      const scope = _activeRepoFileRoot();
      content.innerHTML = `<div class="file-viewer-header">
        <span class="fv-path">${esc(filepath)}</span>
      </div>
      ${_renderNbJumpControls(cells.length, _isNotebookCodeHidden(scope, filepath))}
      <div class="nb-container">${cells.map((c, i) => renderNotebookCell(c, null, i)).join('')}</div>`;
      activateNotebookScripts(content);
      _bindNbNavigation(content, scope, filepath);
    } catch (err) {
      content.innerHTML = `<div class="file-viewer-empty">Error: ${err.message}</div>`;
    }
  }

  async function renderNotebookDiff(filepath, diffType) {
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading notebook diff...</div>';
    try {
      const res = await fetch(`/api/notebook-diff?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(filepath)}&type=${diffType}`);
      const data = await res.json();
      await Promise.all([
        ensureMarked().catch(() => {}),
        ensureHighlight().catch(() => {}),
      ]);
      const header = `<div class="file-header" style="margin:0 0 8px;cursor:default">
        <span class="badge badge-modified">notebook</span>
        <span class="filename">${esc(filepath)}</span>
        <span class="file-stats">${data.changed_cells}/${data.total_cells} cells changed</span>
      </div>`;
      content.innerHTML = header + `<div class="nb-container">${data.cells.map(c => renderNotebookCellDiff(c)).join('')}</div>`;
    } catch (err) {
      content.innerHTML = `<div class="file-viewer-empty">Error: ${err.message}</div>`;
    }
  }

  // ─── Diff popover ───
  let popoverTimeout = null;

  function showDiffPopover(event, hunkIdx) {
    clearTimeout(popoverTimeout);
    const hunk = window._viewHunks[hunkIdx];
    if (!hunk) return;
    const lang = window._viewLang;
    const pop = document.getElementById('diffPopover');

    let rows = `<div class="diff-popover-header">@@ -${hunk.old_start},${hunk.old_count} +${hunk.new_start},${hunk.new_count} @@</div><table>`;
    const lines = hunk.lines;
    let li = 0;
    while (li < lines.length) {
      const l = lines[li];
      if (l.type === 'context') {
        const code = lang ? hlLine(l.content, lang) : esc(l.content);
        rows += `<tr class="pop-ctx"><td class="pop-ln">${l.old_num}</td><td class="pop-code">${code}</td><td class="pop-ln">${l.new_num}</td><td class="pop-code">${code}</td></tr>`;
        li++;
      } else if (l.type === 'delete') {
        const dels = []; while (li < lines.length && lines[li].type === 'delete') { dels.push(lines[li]); li++; }
        const adds = []; while (li < lines.length && lines[li].type === 'add') { adds.push(lines[li]); li++; }
        const max = Math.max(dels.length, adds.length);
        for (let j = 0; j < max; j++) {
          const d = dels[j], a = adds[j];
          const lln = d ? d.old_num : '', lc = d ? (lang ? hlLine(d.content, lang) : esc(d.content)) : '', lcls = d ? 'pop-del' : 'pop-empty';
          const rln = a ? a.new_num : '', rc = a ? (lang ? hlLine(a.content, lang) : esc(a.content)) : '', rcls = a ? 'pop-add' : 'pop-empty';
          rows += `<tr><td class="pop-ln ${lcls}">${lln}</td><td class="pop-code ${lcls}">${lc}</td><td class="pop-ln ${rcls}">${rln}</td><td class="pop-code ${rcls}">${rc}</td></tr>`;
        }
      } else if (l.type === 'add') {
        const code = lang ? hlLine(l.content, lang) : esc(l.content);
        rows += `<tr><td class="pop-ln pop-empty"></td><td class="pop-code pop-empty"></td><td class="pop-ln pop-add">${l.new_num}</td><td class="pop-code pop-add">${code}</td></tr>`;
        li++;
      } else { li++; }
    }
    rows += '</table>';
    pop.innerHTML = rows;

    // Position at 10% from top of the modal, centered horizontally
    const modal = document.querySelector('.modal');
    const modalRect = modal.getBoundingClientRect();
    const top = modalRect.top + modalRect.height * 0.10;
    const left = modalRect.left + (modalRect.width - pop.offsetWidth) / 2;
    pop.style.top = top + 'px';
    pop.classList.add('active');
    pop.style.left = (modalRect.left + (modalRect.width - pop.getBoundingClientRect().width) / 2) + 'px';
  }

  function hideDiffPopover() {
    popoverTimeout = setTimeout(() => {
      document.getElementById('diffPopover').classList.remove('active');
    }, 200);
  }

  // Keep popover open when hovering over it
  document.getElementById('diffPopover').addEventListener('mouseenter', () => clearTimeout(popoverTimeout));
  document.getElementById('diffPopover').addEventListener('mouseleave', () => hideDiffPopover());

  // Meta contains agent instructions; skills stay in the workspace file tree.
  function _agentContextMetaHtml() {
    return `<a class="sidebar-file sidebar-file-meta" onclick="openAgentContext()" title="Read the Lab context supplied when an agent starts"><span class="sidebar-fname">${fileIconHtml('AGENTS.md')}Lab agent context</span></a>`;
  }

  async function openAgentContext() {
    const modal = document.getElementById('docViewModal');
    const body = document.getElementById('docModalBody');
    document.getElementById('docModalTitle').textContent = 'Lab agent context';
    body.innerHTML = '<div class="loading">Loading…</div>';
    modal.classList.add('active');
    _workspaceDocEditing = false;
    if (_docModalEscHandler) document.removeEventListener('keydown', _docModalEscHandler);
    _docModalEscHandler = event => { if (event.key === 'Escape') closeDocModal(); };
    document.addEventListener('keydown', _docModalEscHandler);
    try {
      const response = await fetch('/api/agents/context/guide');
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Could not load agent context.');
      body.innerHTML = `<pre style="white-space:pre-wrap;overflow-wrap:anywhere;padding:20px">${esc(data.content)}</pre>`;
    } catch (error) {
      body.innerHTML = `<div class="empty">${esc(error.message)}</div>`;
    }
  }
  window.openAgentContext = openAgentContext;

  // ─── Focus mode ─────────────────────────────────────────────────────────
  // Keeps the topbar (Home / vault picker / workspace tabs / gear) visible
  // while hiding the workspace attrs bar above the Overview strip and content.
  // Entering from the button also requests browser fullscreen and keeps the
  // display awake. Keep Alive exposes that wake lock independently beside the
  // Focus control. Esc exits Focus; both preferences persist across reloads.
  const FOCUS_MODE_KEY = 'labFocusMode';
  const KEEP_ALIVE_KEY = 'labKeepAlive';
  const LINKED_TERMINAL_SYNC_KEY = 'labLinkedTerminalSync';
  const LID_AWAKE_DURATIONS = [15, 30, 60];
  const LID_AWAKE_DEFAULT_UNTIL = '17:00';
  const FOCUS_ZOOM_MIN = 0.5;
  const FOCUS_ZOOM_MAX = 3;
  const FOCUS_ZOOM_SENSITIVITY = 0.01;
  let _screenWakeLock = null;
  let _screenWakeLockRequest = null;
  let _focusOwnsFullscreen = false;
  let _focusZoom = 1;
  let _lidAwakeSupported = true;
  let _lidAwakeDeadlineMs = 0;
  let _lidAwakeMenuOpen = false;
  let _lidAwakeBusy = false;
  let _lidAwakeError = '';
  let _linkedTerminalSyncOn = false;
  let _lidAwakePasswordSaved = false;
  let _lidAwakeEditingPassword = false;
  let _lidAwakeUntilTime = LID_AWAKE_DEFAULT_UNTIL;

  function _lidAwakeIsActive() {
    return _lidAwakeDeadlineMs > Date.now();
  }

  function _formatLidAwakeRemaining(remainingMs) {
    const totalSeconds = Math.max(0, Math.ceil(Number(remainingMs || 0) / 1000));
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = String(totalSeconds % 60).padStart(2, '0');
    return `${minutes}:${seconds}`;
  }

  function _lidAwakeLabel() {
    if (_lidAwakeBusy && !_lidAwakeIsActive()) return 'Lid Awake…';
    if (!_lidAwakeIsActive()) return 'Lid Awake';
    return `Lid Awake ${_formatLidAwakeRemaining(_lidAwakeDeadlineMs - Date.now())}`;
  }

  function _applyLidAwakeStatus(status) {
    _lidAwakeSupported = status && status.supported !== false;
    if (status && typeof status.password_saved === 'boolean') {
      _lidAwakePasswordSaved = status.password_saved;
      if (!_lidAwakePasswordSaved) _lidAwakeEditingPassword = true;
    }
    const deadline = Number(status && status.deadline);
    _lidAwakeDeadlineMs = status && status.active && Number.isFinite(deadline)
      ? deadline * 1000
      : 0;
  }

  function _renderLidAwakeMenu() {
    const menu = document.getElementById('lidAwakeMenu');
    if (!menu) return;
    const button = document.querySelector('.lid-awake-toggle');
    if (button) button.setAttribute('aria-expanded', _lidAwakeMenuOpen ? 'true' : 'false');
    if (!_lidAwakeMenuOpen || !button || !currentWorkspace) {
      menu.classList.remove('open');
      menu.innerHTML = '';
      return;
    }

    const active = _lidAwakeIsActive();
    const verb = active ? 'Renew for' : 'Start for';
    const disabled = _lidAwakeBusy ? ' disabled' : '';
    const durationButtons = LID_AWAKE_DURATIONS.map(minutes =>
      `<button type="button" role="menuitem" onclick="event.stopPropagation(); setLidAwake(${minutes})"${disabled}>${verb} ${minutes} min</button>`
    ).join('');
    const untilVerb = active ? 'Renew' : 'Start';
    const untilControl = `
      <div class="lid-awake-until">
        <label for="lidAwakeUntilTime">Until
          <input id="lidAwakeUntilTime" type="time" step="60" value="${escAttr(_lidAwakeUntilTime)}" oninput="updateLidAwakeUntilTime(this.value)"${disabled}>
        </label>
        <button type="button" role="menuitem" class="lid-awake-until-button" onclick="event.stopPropagation(); setLidAwakeUntil()"${disabled}>${untilVerb} until ${esc(_lidAwakeUntilTime || 'time')}</button>
        <span>Past times mean tomorrow.</span>
      </div>`;
    const current = active
      ? `<div class="lid-awake-current"><span class="lid-awake-dot"></span><span id="lidAwakeMenuCountdown">${_formatLidAwakeRemaining(_lidAwakeDeadlineMs - Date.now())} remaining</span></div>`
      : '';
    const cancel = active
      ? `<button type="button" role="menuitem" class="lid-awake-cancel" onclick="event.stopPropagation(); cancelLidAwake()"${disabled}>Cancel now</button>`
      : '';
    const needsPassword = !active
      && (!_lidAwakePasswordSaved || _lidAwakeEditingPassword);
    const authentication = active ? '' : (needsPassword ? `
      <label class="lid-awake-password-label" for="lidAwakePassword">Mac password</label>
      <input id="lidAwakePassword" class="lid-awake-password" type="password" autocomplete="off" autocapitalize="none" spellcheck="false" placeholder="Enter Mac password"${disabled}>`
      : `<div class="lid-awake-saved-password">
          <span>Password saved in macOS Keychain</span>
          <div class="lid-awake-secret-actions">
            <button type="button" onclick="event.stopPropagation(); editLidAwakePassword()"${disabled}>Change</button>
            <button type="button" onclick="event.stopPropagation(); forgetLidAwakePassword()"${disabled}>Forget</button>
          </div>
        </div>`);
    const message = _lidAwakeError
      ? `<div class="lid-awake-error">${esc(_lidAwakeError)}</div>`
      : (_lidAwakeBusy
        ? `<div class="lid-awake-note">${needsPassword ? 'Checking password…' : 'Using saved password…'}</div>`
        : (active
          ? '<div class="lid-awake-note">Choose a duration or an until time to reset the timer.</div>'
          : `<div class="lid-awake-note">${needsPassword
            ? 'After a successful start, the password is encrypted in macOS Keychain—not browser storage.'
            : 'Keeps this Mac running with the lid closed. The browser never receives the saved password.'}</div>`));
    menu.innerHTML = `
      <div class="lid-awake-title">Lid Awake</div>
      ${current}
      ${authentication}
      <div class="lid-awake-durations">${durationButtons}</div>
      ${untilControl}
      ${cancel}
      <div class="lid-awake-safety">Thermal safety is always on.</div>
      ${message}`;

    const rect = button.getBoundingClientRect();
    menu.style.top = `${Math.round(rect.bottom + 6)}px`;
    menu.style.right = `${Math.max(8, Math.round(window.innerWidth - rect.right))}px`;
    menu.classList.add('open');
  }

  function _updateLidAwakeControl() {
    if (_lidAwakeDeadlineMs && !_lidAwakeIsActive()) {
      _lidAwakeDeadlineMs = 0;
      _lidAwakeMenuOpen = false;
      if (currentWorkspace) renderRepoTabs();
      else _renderLidAwakeMenu();
      return;
    }
    const button = document.querySelector('.lid-awake-toggle');
    if (button) {
      const label = button.querySelector('.lid-awake-label');
      if (label) label.textContent = _lidAwakeLabel();
      button.classList.toggle('active', _lidAwakeIsActive());
      button.setAttribute('aria-label', _lidAwakeIsActive()
        ? `${_lidAwakeLabel()}; choose a new time or cancel`
        : 'Start Lid Awake timer');
    }
    const countdown = document.getElementById('lidAwakeMenuCountdown');
    if (countdown && _lidAwakeIsActive()) {
      countdown.textContent = `${_formatLidAwakeRemaining(_lidAwakeDeadlineMs - Date.now())} remaining`;
    }
  }

  async function _syncLidAwakeStatus() {
    if (!window.fetch) return;
    try {
      const wasActive = _lidAwakeIsActive();
      const wasSupported = _lidAwakeSupported;
      const response = await window.fetch('/api/power/lid-awake');
      if (!response.ok) return;
      _applyLidAwakeStatus(await response.json());
      _updateLidAwakeControl();
      if (_lidAwakeMenuOpen
          && (wasActive !== _lidAwakeIsActive()
            || wasSupported !== _lidAwakeSupported)) _renderLidAwakeMenu();
    } catch {}
  }

  function toggleLidAwakeMenu(event) {
    if (event && typeof event.stopPropagation === 'function') event.stopPropagation();
    if (!_lidAwakeSupported || _lidAwakeBusy) return;
    _lidAwakeMenuOpen = !_lidAwakeMenuOpen;
    _lidAwakeError = '';
    if (!_lidAwakeMenuOpen && _lidAwakePasswordSaved) {
      _lidAwakeEditingPassword = false;
    }
    _renderLidAwakeMenu();
  }
  window.toggleLidAwakeMenu = toggleLidAwakeMenu;

  function editLidAwakePassword() {
    if (_lidAwakeBusy || _lidAwakeIsActive()) return;
    _lidAwakeEditingPassword = true;
    _lidAwakeError = '';
    _renderLidAwakeMenu();
    const input = document.getElementById('lidAwakePassword');
    if (input && typeof input.focus === 'function') input.focus();
  }
  window.editLidAwakePassword = editLidAwakePassword;

  function updateLidAwakeUntilTime(value) {
    _lidAwakeUntilTime = String(value || '');
    const button = document.querySelector('.lid-awake-until-button');
    if (button) {
      const verb = _lidAwakeIsActive() ? 'Renew' : 'Start';
      button.textContent = `${verb} until ${_lidAwakeUntilTime || 'time'}`;
    }
  }
  window.updateLidAwakeUntilTime = updateLidAwakeUntilTime;

  async function _startLidAwake(schedule) {
    if (_lidAwakeBusy) return;
    let password = null;
    if (!_lidAwakeIsActive()
        && (!_lidAwakePasswordSaved || _lidAwakeEditingPassword)) {
      const input = document.getElementById('lidAwakePassword');
      password = input ? input.value : '';
      if (!password) {
        _lidAwakeError = 'Enter your Mac password.';
        _renderLidAwakeMenu();
        return;
      }
    }
    _lidAwakeBusy = true;
    _lidAwakeError = '';
    _renderLidAwakeMenu();
    _updateLidAwakeControl();
    try {
      const response = await window.fetch('/api/power/lid-awake', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          ...schedule,
          ...(password !== null ? {password} : {}),
        }),
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = body && body.detail;
        const error = new Error(
          (detail && typeof detail === 'object' ? detail.message : detail)
            || 'Lid Awake could not be started.'
        );
        if (detail && typeof detail.password_saved === 'boolean') {
          error.passwordSaved = detail.password_saved;
        }
        throw error;
      }
      _applyLidAwakeStatus(body);
      _lidAwakeEditingPassword = false;
      if (body.warning) {
        _lidAwakeError = String(body.warning);
        _lidAwakeEditingPassword = true;
        _lidAwakeMenuOpen = true;
      } else {
        _lidAwakeMenuOpen = false;
      }
    } catch (error) {
      if (error && error.passwordSaved === false) {
        _lidAwakePasswordSaved = false;
        _lidAwakeEditingPassword = true;
      }
      _lidAwakeError = String(error && error.message || error);
      _lidAwakeMenuOpen = true;
    } finally {
      password = null;
      _lidAwakeBusy = false;
      if (currentWorkspace) renderRepoTabs();
      else _renderLidAwakeMenu();
    }
  }

  function setLidAwake(minutes) {
    const normalized = Number(minutes);
    if (!LID_AWAKE_DURATIONS.includes(normalized)) return Promise.resolve();
    return _startLidAwake({minutes: normalized});
  }
  window.setLidAwake = setLidAwake;

  function setLidAwakeUntil() {
    if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(_lidAwakeUntilTime)) {
      _lidAwakeError = 'Choose a valid until time.';
      _renderLidAwakeMenu();
      return Promise.resolve();
    }
    return _startLidAwake({until: _lidAwakeUntilTime});
  }
  window.setLidAwakeUntil = setLidAwakeUntil;

  async function forgetLidAwakePassword() {
    if (_lidAwakeBusy || _lidAwakeIsActive()) return;
    _lidAwakeBusy = true;
    _lidAwakeError = '';
    _renderLidAwakeMenu();
    try {
      const response = await window.fetch('/api/power/lid-awake/password', {
        method: 'DELETE',
      });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'The saved password could not be forgotten.');
      _lidAwakePasswordSaved = false;
      _lidAwakeEditingPassword = true;
    } catch (error) {
      _lidAwakeError = String(error && error.message || error);
    } finally {
      _lidAwakeBusy = false;
      if (currentWorkspace) renderRepoTabs();
      else _renderLidAwakeMenu();
    }
  }
  window.forgetLidAwakePassword = forgetLidAwakePassword;

  async function cancelLidAwake() {
    if (_lidAwakeBusy) return;
    _lidAwakeBusy = true;
    _lidAwakeError = '';
    _renderLidAwakeMenu();
    try {
      const response = await window.fetch('/api/power/lid-awake', {method: 'DELETE'});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.detail || 'Lid Awake could not be cancelled.');
      _applyLidAwakeStatus(body);
      _lidAwakeMenuOpen = false;
    } catch (error) {
      _lidAwakeError = String(error && error.message || error);
      _lidAwakeMenuOpen = true;
    } finally {
      _lidAwakeBusy = false;
      if (currentWorkspace) renderRepoTabs();
      else _renderLidAwakeMenu();
    }
  }
  window.cancelLidAwake = cancelLidAwake;

  document.addEventListener('click', (event) => {
    const target = event && event.target;
    if (target && target.closest
        && target.closest('#lidAwakeMenu, .lid-awake-toggle')) return;
    if (!_lidAwakeMenuOpen) return;
    _lidAwakeMenuOpen = false;
    _renderLidAwakeMenu();
  });

  if (typeof LAB_IS_ADMIN === 'undefined' || LAB_IS_ADMIN) {
    if (window.fetch) void _syncLidAwakeStatus();
    if (typeof window.setInterval === 'function') {
      window.setInterval(_updateLidAwakeControl, 1000);
      window.setInterval(() => void _syncLidAwakeStatus(), 15000);
    }
  }

  function _applyFocusZoom(zoom) {
    const clamped = Math.min(FOCUS_ZOOM_MAX, Math.max(FOCUS_ZOOM_MIN, zoom));
    _focusZoom = Math.round(clamped * 1000) / 1000;
    // CSS zoom participates in layout, unlike transform:scale(), so fixed
    // sidebars, terminals, modals, and scrollable documents keep behaving
    // like a normally browser-zoomed page.
    document.body.style.zoom = _focusZoom === 1 ? '' : String(_focusZoom);
  }

  function _resetFocusZoom() {
    _focusZoom = 1;
    document.body.style.zoom = '';
  }

  function _handleFocusZoomWheel(e) {
    // Chromium exposes a trackpad pinch as a cancelable Ctrl+wheel gesture.
    // Browser page zoom is suppressed by the Fullscreen API, so reproduce it
    // only while Focus mode is active and leave ordinary two-finger scrolling
    // (and all behavior outside Focus mode) untouched.
    if (!document.body.classList.contains('focus-mode')
        || !e.ctrlKey
        || !Number.isFinite(e.deltaY)
        || e.deltaY === 0) return;
    if (typeof e.preventDefault === 'function') e.preventDefault();
    _applyFocusZoom(_focusZoom * Math.exp(-e.deltaY * FOCUS_ZOOM_SENSITIVITY));
  }

  function _wireFocusZoomDocument(doc) {
    if (!doc || doc.__labFocusZoomWired || typeof doc.addEventListener !== 'function') return;
    doc.__labFocusZoomWired = true;
    doc.addEventListener('wheel', _handleFocusZoomWheel, {capture: true, passive: false});
  }

  _wireFocusZoomDocument(document);

  function _shouldKeepDisplayAwake() {
    return document.body.classList.contains('focus-mode')
      || document.body.classList.contains('keep-alive');
  }

  async function _acquireScreenWakeLock() {
    if (!_shouldKeepDisplayAwake()
        || document.visibilityState !== 'visible'
        || typeof navigator === 'undefined'
        || !navigator.wakeLock
        || typeof navigator.wakeLock.request !== 'function') return null;
    if (_screenWakeLock && !_screenWakeLock.released) return _screenWakeLock;
    if (_screenWakeLockRequest) return _screenWakeLockRequest;

    const request = navigator.wakeLock.request('screen').then(lock => {
      // Both intents may have been switched off while the browser was
      // granting the lock.
      if (!_shouldKeepDisplayAwake()
          || document.visibilityState !== 'visible') {
        try {
          const released = lock.release();
          if (released && typeof released.catch === 'function') released.catch(() => {});
        } catch {}
        return null;
      }
      _screenWakeLock = lock;
      lock.addEventListener('release', () => {
        if (_screenWakeLock === lock) _screenWakeLock = null;
      }, {once: true});
      return lock;
    }).catch(() => null);
    _screenWakeLockRequest = request;
    try { return await request; }
    finally {
      if (_screenWakeLockRequest === request) _screenWakeLockRequest = null;
    }
  }

  function _releaseScreenWakeLock() {
    const lock = _screenWakeLock;
    _screenWakeLock = null;
    if (!lock || lock.released) return;
    try {
      const released = lock.release();
      if (released && typeof released.catch === 'function') released.catch(() => {});
    } catch {}
  }

  function _enterFocusFullscreen() {
    if (document.fullscreenElement
        || !document.documentElement
        || typeof document.documentElement.requestFullscreen !== 'function') return;
    _focusOwnsFullscreen = true;
    try {
      const entered = document.documentElement.requestFullscreen();
      if (entered && typeof entered.catch === 'function') {
        entered.catch(() => { _focusOwnsFullscreen = false; });
      }
    } catch { _focusOwnsFullscreen = false; }
  }

  function _exitFocusFullscreen() {
    if (!_focusOwnsFullscreen || !document.fullscreenElement
        || typeof document.exitFullscreen !== 'function') {
      _focusOwnsFullscreen = false;
      return;
    }
    _focusOwnsFullscreen = false;
    try {
      const exited = document.exitFullscreen();
      if (exited && typeof exited.catch === 'function') exited.catch(() => {});
    } catch {}
  }

  function applyFocusMode(on) {
    document.body.classList.toggle('focus-mode', !!on);
    try { localStorage.setItem(FOCUS_MODE_KEY, on ? '1' : '0'); } catch {}
    if (on) void _acquireScreenWakeLock();
    else {
      _resetFocusZoom();
      if (!_shouldKeepDisplayAwake()) _releaseScreenWakeLock();
      _exitFocusFullscreen();
    }
    // Re-render the strip so the button label flips.
    try { if (currentWorkspace) renderRepoTabs(); } catch {}
  }
  function toggleFocusMode() {
    const on = !document.body.classList.contains('focus-mode');
    applyFocusMode(on);
    // Fullscreen requires a user gesture, so only request it from the toggle
    // click/shortcut rather than when restoring Focus mode after a reload.
    if (on) _enterFocusFullscreen();
  }
  window.toggleFocusMode = toggleFocusMode;

  function applyKeepAlive(on) {
    document.body.classList.toggle('keep-alive', !!on);
    try { localStorage.setItem(KEEP_ALIVE_KEY, on ? '1' : '0'); } catch {}
    if (on) void _acquireScreenWakeLock();
    else if (!_shouldKeepDisplayAwake()) _releaseScreenWakeLock();
    try { if (currentWorkspace) renderRepoTabs(); } catch {}
  }
  function toggleKeepAlive() {
    applyKeepAlive(!document.body.classList.contains('keep-alive'));
  }
  window.toggleKeepAlive = toggleKeepAlive;

  function toggleLinkedTerminalSync() {
    _linkedTerminalSyncOn = !_linkedTerminalSyncOn;
    if (!_linkedTerminalSyncOn) _termCancelPendingLinkedFileOpen();
    try { localStorage.setItem(LINKED_TERMINAL_SYNC_KEY, _linkedTerminalSyncOn ? '1' : '0'); } catch {}
    try { if (currentWorkspace) renderRepoTabs(); } catch {}
  }
  window.toggleLinkedTerminalSync = toggleLinkedTerminalSync;

  try {
    if (localStorage.getItem(FOCUS_MODE_KEY) === '1') {
      document.body.classList.add('focus-mode');
    }
    if (localStorage.getItem(KEEP_ALIVE_KEY) === '1') {
      document.body.classList.add('keep-alive');
    }
    _linkedTerminalSyncOn = localStorage.getItem(LINKED_TERMINAL_SYNC_KEY) === '1';
    if (_shouldKeepDisplayAwake()) void _acquireScreenWakeLock();
  } catch {}
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible'
        && _shouldKeepDisplayAwake()) {
      void _acquireScreenWakeLock();
    }
    if (document.visibilityState === 'visible'
        && (typeof LAB_IS_ADMIN === 'undefined' || LAB_IS_ADMIN)) {
      void _syncLidAwakeStatus();
    }
  });
  document.addEventListener('fullscreenchange', () => {
    // Browser Esc exits fullscreen first. Keep Focus mode, persistence, and
    // its layout preference in sync with that visible exit. Keep Alive, if
    // independently enabled, continues owning the wake lock.
    if (_focusOwnsFullscreen && !document.fullscreenElement
        && document.body.classList.contains('focus-mode')) {
      _focusOwnsFullscreen = false;
      applyFocusMode(false);
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !document.body.classList.contains('focus-mode')) return;
    // Don't steal Esc from terminals, form fields, or any layer that
    // consumes Esc itself (settings/editor modals, the doc view modal,
    // proxy fullscreen) — one press must close one thing.
    const t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, [contenteditable="true"], .term-panel')) return;
    if (document.querySelector('.modal-overlay.active, .doc-modal-overlay.active')) return;
    if (document.body.classList.contains('proxy-fullscreen')) return;
    applyFocusMode(false);
  });

  function renderRepoTabs() {
    const container = document.getElementById('repoTabs');
    if (!currentWorkspace) {
      _lidAwakeMenuOpen = false;
      _renderLidAwakeMenu();
      container.style.display = 'none';
      document.body.classList.remove('has-repo-tabs');
      return;
    }

    container.style.display = 'flex';
    document.body.classList.add('has-repo-tabs');

    let html = '';
    const isSelf = document.body.classList.contains('self-active');
    const isAssistant = document.body.classList.contains('assistant-active');
    const isVault = document.body.classList.contains('vault-active');
    const proxyOpen = typeof _workspaceDocPath === 'string' && _workspaceDocPath.startsWith('__proxy__/');
    const notebookOpen = _contextSubView === 'notebooks'
      || (typeof _workspaceDocPath === 'string' && _workspaceDocPath.toLowerCase().endsWith('.ipynb'));
    const overviewActive = _contextSubView === 'overview' && !_workspaceDocPath && !currentRepo && !proxyOpen;
    const codeSearchActive = _contextSubView === 'code-search';

    if (isAssistant) {
      const assistantSection = _workspaceDocPath ? 'document' : (window.AssistantView ? window.AssistantView.section() : 'overview');
      html += `<button class="repo-tab${assistantSection === 'overview' ? ' active' : ''}" data-assistant-section="overview" onclick="AssistantView.setSection('overview')" style="font-weight:600">&#x1F4CB; Overview</button>`;
      html += `<button class="repo-tab${assistantSection === 'tasks' ? ' active' : ''}" data-assistant-section="tasks" onclick="AssistantView.setSection('tasks')" style="font-weight:600">&#x2726; Tasks</button>`;
      html += `<button class="repo-tab${assistantSection === 'meetings' ? ' active' : ''}" data-assistant-section="meetings" onclick="AssistantView.setSection('meetings')">&#x1F4DD; Meeting notes</button>`;
    } else if (isSelf || isVault) {
      if (LAB_IS_ADMIN) {
        html += `<button class="repo-tab${isSelf && overviewActive ? ' active' : ''}" onclick="${isSelf ? 'selfShowWorkbench()' : 'goToProductivity()'}" style="font-weight:600">&#x1F4CB; Overview</button>`;
        html += `<button class="repo-tab${isSelf && codeSearchActive ? ' active' : ''}" onclick="${isSelf ? 'showScopedCodeSearch()' : "goToProductivity({subview:'code-search'})"}">&#x1F50D; Code Search</button>`;
      }
      for (const vault of (vaultCatalog || [])) {
        const active = isVault && _vaultCurrent && _vaultCurrent.id === vault.id;
        const action = active ? 'vaultShowOverview()' : `goToVault(${JSON.stringify(vault.id)})`;
        html += `<button class="repo-tab vault-context-tab${active ? ' active' : ''}" style="--vault-color:${escAttr(vault.color || '#8b949e')}" onclick="${escAttr(action)}"><span class="vault-mark"></span>${esc(vault.name || vault.id)}</button>`;
      }
      if (LAB_IS_ADMIN) html += `<button class="repo-tab home-logs-tab${isSelf && _contextSubView === 'logs' ? ' active' : ''}" onclick="goToLogs()">&#x2637; Logs</button>`;
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${isSelf && _contextSubView === 'admin' ? ' active' : ''}" onclick="${isSelf ? 'selfShowAdmin()' : "goToProductivity({subview:'admin'})"}">&#x2699; Admin</button>`;
    } else if (currentWorkspace.is_workspace) {
      html += `<button class="repo-tab${overviewActive ? ' active' : ''}" onclick="showWorkspaceDashboard()" style="font-weight:600">&#x1F4CB; Overview</button>`;
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${codeSearchActive ? ' active' : ''}" onclick="showScopedCodeSearch()">&#x1F50D; Code Search</button>`;
      html += `<button class="repo-tab${notebookOpen ? ' active' : ''}" onclick="openWorkspaceNotebooks()" title="Lab Jupyter notebooks — no server configuration required">&#x25C9; Jupyter</button>`;
    }

    // One tab per declared server (workspace.json proxies) — clicking it opens
    // the same inline iframe view as the sidebar Servers entry. The list
    // comes from the sidebar payload cache; on a cold load it's empty until
    // _refreshWorkspaceSidebar fetches workspace-info and re-calls us.
    if (!isSelf && !isAssistant && !isVault && currentWorkspace.is_workspace) {
      const cached = _workspaceSidebarCache.get(currentWorkspace.path);
      const proxies = (cached && Array.isArray(cached.proxies)) ? cached.proxies : [];
      proxies.forEach(p => {
        if (!p || !p.name) return;
        const name = String(p.name);
        const safeName = name.replace(/'/g, "\\'");
        const label = p.label || name;
        const active = _workspaceDocPath === '__proxy__/' + name ? ' active' : '';
        html += `<button class="repo-tab${active}" onclick="openWorkspaceProxy('${safeName}')">&#x1F310; ${esc(label)} <span style="color:#484f58;font-size:10px">:${esc(String(p.port || ''))}</span></button>`;
      });
    }

    const focusOn = document.body.classList.contains('focus-mode');
    const keepAliveOn = document.body.classList.contains('keep-alive');
    const keepAliveTitle = keepAliveOn
      ? `Keep Alive is on — turn it off${focusOn ? ' (Focus mode will still keep the display awake)' : ''}`
      : (focusOn
        ? 'Turn on Keep Alive to stay awake after leaving Focus mode'
        : 'Prevent the display and computer from sleeping');
    html += `<button class="repo-tab keep-alive-toggle" role="switch" aria-checked="${keepAliveOn}" onclick="toggleKeepAlive()" title="${keepAliveTitle}"><span>Keep Alive</span><span class="keep-alive-switch" aria-hidden="true"></span></button>`;
    const linkedSyncTitle = _linkedTerminalSyncOn
      ? 'Linked file and terminal selections follow each other — turn off to keep navigation independent'
      : 'Keep linked files and terminals independent until this is turned on';
    html += `<button class="repo-tab linked-terminal-sync-toggle" role="switch" aria-checked="${_linkedTerminalSyncOn}" onclick="toggleLinkedTerminalSync()" title="${linkedSyncTitle}"><span>Sync linked</span><span class="linked-terminal-sync-switch" aria-hidden="true"></span></button>`;
    if (typeof LAB_IS_ADMIN === 'undefined' || LAB_IS_ADMIN) {
      const lidAwakeOn = _lidAwakeIsActive();
      const lidAwakeTitle = !_lidAwakeSupported
        ? 'Lid Awake is available only on macOS'
        : (lidAwakeOn
          ? 'Mac stays running with the lid closed; choose a new time or cancel'
          : 'Keep this Mac running with the lid closed for 15, 30, or 60 minutes');
      html += `<button class="repo-tab lid-awake-toggle${lidAwakeOn ? ' active' : ''}${_lidAwakeBusy ? ' busy' : ''}" data-testid="lid-awake-toggle" onclick="toggleLidAwakeMenu(event)" aria-haspopup="dialog" aria-expanded="${_lidAwakeMenuOpen}" aria-label="${lidAwakeOn ? `${_lidAwakeLabel()}; choose a new time or cancel` : 'Start Lid Awake timer'}" title="${lidAwakeTitle}"${!_lidAwakeSupported ? ' disabled' : ''}><span class="lid-awake-label">${_lidAwakeLabel()}</span></button>`;
    }
    html += `<button class="repo-tab focus-toggle" onclick="toggleFocusMode()" title="${focusOn ? (keepAliveOn ? 'Exit fullscreen focus (Keep Alive will remain on)' : 'Exit fullscreen focus and allow display sleep again (Esc)') : 'Enter fullscreen focus and keep the display awake'}">${focusOn ? '✖ Exit focus' : '⛶ Focus mode'}</button>`;

    container.innerHTML = html;
    _renderLidAwakeMenu();
  }

  function showScopedCodeSearch() {
    if (!currentWorkspace || !currentWorkspace.path) return;
    _contextSubView = 'code-search';
    _termSelectHomeSection();
    if (document.body.classList.contains('self-active')) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'productivity');
      url.searchParams.set('subview', 'code-search');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
    currentRepo = null;
    _workspaceDocPath = null;
    renderRepoTabs();
    const kind = document.body.classList.contains('self-active')
      ? 'framework'
      : document.body.classList.contains('vault-active') ? 'vault' : 'workspace';
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="context-placeholder">
        <div class="eyebrow">${esc(kind)} search</div>
        <h1>Code Search is in development</h1>
        <p>This tab will use AI to find and explain code only inside the path selected by the current tab.</p>
        <span class="context-path">${esc(currentWorkspace.path)}</span>
      </div>`;
  }
  window.showScopedCodeSearch = showScopedCodeSearch;

  let _workspaceDocPath = null;
  let _workspaceDocRoot = null; // alternate file root selected by the worktree picker
  let _workspaceDocContent = null;
  let _workspaceDocEditing = false;
  let _workspaceDocEditContainer = null; // container that holds the active edit textarea
  let _workspaceComments = [];
  let _workspaceDocArtifact = null;  // workspace.json.artifacts[] entry whose `file` matches the open doc
  // Doc-content cache for warm tab switches: key `${workspace.path}|${filepath}`
  // → {content, comments, artifact}. Lets openWorkspaceDoc paint a remembered
  // file synchronously while the three /api/workspace-* fetches reconcile in
  // the background. Only used for the text/markdown/csv/json path inside
  // _renderDocInto — notebooks/HTML/images have their own renderers and
  // are excluded. Survives tab switches; reset on full page reload.
  const _workspaceDocCache = new Map();
  function _workspaceDocCacheKey(workspacePath, filepath) {
    return (workspacePath || '') + '|' + (filepath || '');
  }
  // Sidebar payload cache keyed by `currentWorkspace.path`. Stores the
  // last-known `{files, pinned, references}` triple so warm switches
  // can re-render the file tree synchronously from memory instead of
  // waiting on /api/workspace-files + /api/workspace-info every time.
  // `_refreshWorkspaceSidebar` reconciles against the server in the
  // background after a warm paint and writes through to this map.
  const _workspaceSidebarCache = new Map();
  // Same idea for the workspace server bar. Keyed by absolute workspace path.
  const _workspaceAttrsCache = new Map();

  // Per-workspace memory of the last file the user had open. Survives
  // tab switches and reloads; map keyed by absolute workspace path.
  const LAST_DOC_KEY = 'labLastDoc-v1';
  function _lastDocMap() {
    try { return JSON.parse(localStorage.getItem(LAST_DOC_KEY) || '{}') || {}; }
    catch { return {}; }
  }
  function setLastWorkspaceDoc(workspacePath, docPath) {
    if (!workspacePath) return;
    const m = _lastDocMap();
    if (docPath) m[workspacePath] = docPath; else delete m[workspacePath];
    try { localStorage.setItem(LAST_DOC_KEY, JSON.stringify(m)); } catch {}
  }
  function getLastWorkspaceDoc(workspacePath) {
    return _lastDocMap()[workspacePath] || null;
  }

  // Notebook selection is remembered separately from the last ordinary
  // workspace document. A user can move from a notebook to README.md and still
  // return to the same live kernel with one click on the built-in Jupyter tab.
  const LAST_NOTEBOOK_KEY = 'labLastNotebook-v1';
  function _lastNotebookMap() {
    try { return JSON.parse(localStorage.getItem(LAST_NOTEBOOK_KEY) || '{}') || {}; }
    catch { return {}; }
  }
  function setLastWorkspaceNotebook(workspacePath, notebookPath) {
    if (!workspacePath || !notebookPath) return;
    const m = _lastNotebookMap();
    m[workspacePath] = notebookPath;
    try { localStorage.setItem(LAST_NOTEBOOK_KEY, JSON.stringify(m)); } catch {}
  }
  function getLastWorkspaceNotebook(workspacePath) {
    return _lastNotebookMap()[workspacePath] || null;
  }

  function _workspaceNotebookEntries(files) {
    return (Array.isArray(files) ? files : [])
      .filter(f => f && f.type !== 'dir' && typeof f.path === 'string'
        && f.path.toLowerCase().endsWith('.ipynb'))
      .sort((a, b) => Number(b.mtime || 0) - Number(a.mtime || 0)
        || a.path.localeCompare(b.path));
  }

  async function _loadWorkspaceNotebookEntries(workspacePath) {
    const cached = _workspaceSidebarCache.get(workspacePath);
    if (cached && Array.isArray(cached.files)) return _workspaceNotebookEntries(cached.files);
    const response = await fetch(`/api/workspace-files?path=${encodeURIComponent(workspacePath)}`);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Could not list notebooks (${response.status})`);
    }
    return _workspaceNotebookEntries(await response.json());
  }

  function _renderWorkspaceNotebookLauncher(notebooks) {
    const content = document.getElementById('content');
    if (!content) return;
    const workspaceName = currentWorkspace ? _workspaceDisplayName(currentWorkspace) : 'this workspace';
    const workspacePath = currentWorkspace && currentWorkspace.path ? currentWorkspace.path : '';
    const cards = notebooks.map(entry => {
      const path = String(entry.path || '');
      const safePath = path.replace(/'/g, "\\'");
      const updated = entry.mtime
        ? `updated ${new Date(Number(entry.mtime) * 1000).toLocaleString()}`
        : 'not run yet';
      return `<button type="button" onclick="openWorkspaceDoc('${safePath}')" style="display:flex;align-items:center;gap:14px;width:100%;text-align:left;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:14px 16px;cursor:pointer">
        <span style="font-size:22px;color:var(--accent)">&#x25C9;</span>
        <span style="min-width:0;flex:1"><strong style="display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(path.split('/').pop() || path)}</strong><span style="display:block;color:var(--text-dim);font:11px ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px">${esc(path)}</span></span>
        <span style="color:var(--text-dim);font-size:11px;white-space:nowrap">${esc(updated)}</span>
      </button>`;
    }).join('');
    content.innerHTML = `<div style="padding:28px;max-width:900px">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:22px">
        <div style="flex:1"><h1 style="color:var(--text-primary);font-size:24px;margin:0 0 5px">Jupyter <span style="color:var(--text-dim);font-weight:400">· ${esc(workspaceName)}</span></h1><p style="color:var(--text-secondary);font-size:13px;margin:0">Notebooks are scoped to this workspace. Every .ipynb keeps its own kernel; people and agents share it by file path.</p>${workspacePath ? `<code style="display:block;color:var(--text-dim);font-size:11px;margin-top:6px;overflow-wrap:anywhere">${esc(workspacePath)}</code>` : ''}</div>
        <button type="button" onclick="openNewNotebookDialog()" style="background:var(--accent);color:#fff;border:0;border-radius:6px;padding:8px 13px;cursor:pointer">+ Notebook</button>
      </div>
      ${notebooks.length
        ? `<div style="display:flex;flex-direction:column;gap:9px">${cards}</div>`
        : `<div style="border:1px dashed var(--border);border-radius:8px;padding:36px;text-align:center;color:var(--text-dim)">No .ipynb files in <strong style="color:var(--text-secondary)">${esc(workspaceName)}</strong> yet.<div style="font-size:12px;margin-top:7px">A notebook created in another workspace appears in that workspace's Jupyter tab.</div><button type="button" onclick="openNewNotebookDialog()" style="margin-top:14px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;padding:7px 12px;cursor:pointer">Create the first notebook here</button></div>`}
    </div>`;
  }

  async function openWorkspaceNotebooks({showLauncher = false} = {}) {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    const workspacePath = currentWorkspace.path;
    if (!showLauncher && typeof _workspaceDocPath === 'string'
        && _workspaceDocPath.toLowerCase().endsWith('.ipynb')) {
      return openWorkspaceDoc(_workspaceDocPath);
    }
    _contextSubView = 'notebooks';
    currentRepo = null;
    currentRepoInWorkspace = null;
    _repoFileRoot = null;
    _workspaceDocPath = '__notebooks__';
    _workspaceDocRoot = workspacePath;
    renderRepoTabs();
    _sidebarApplyForView();
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="loading">Loading notebooks...</div>';
    try {
      const notebooks = await _loadWorkspaceNotebookEntries(workspacePath);
      if (!currentWorkspace || currentWorkspace.path !== workspacePath || _workspaceDocPath !== '__notebooks__') return;
      const remembered = getLastWorkspaceNotebook(workspacePath);
      const preferred = !showLauncher && remembered
        ? notebooks.find(entry => entry.path === remembered)
        : null;
      if (preferred) return openWorkspaceDoc(preferred.path);
      if (!showLauncher && notebooks.length === 1) return openWorkspaceDoc(notebooks[0].path);
      _renderWorkspaceNotebookLauncher(notebooks);
    } catch (err) {
      if (content && currentWorkspace && currentWorkspace.path === workspacePath
          && _workspaceDocPath === '__notebooks__') {
        content.innerHTML = `<div class="no-repo"><p>Error: ${esc(err.message || err)}</p></div>`;
      }
    }
  }
  window.openWorkspaceNotebooks = openWorkspaceNotebooks;

  let _docModalEscHandler = null;

  async function openWorkspaceDocModal(filepath, { editing = false, root = null } = {}) {
    if (!currentWorkspace) return;
    _workspaceDocRoot = root || currentWorkspace.path;
    const modal = document.getElementById('docViewModal');
    const body = document.getElementById('docModalBody');
    const titleEl = document.getElementById('docModalTitle');
    titleEl.textContent = filepath;
    body.innerHTML = '<div class="loading" style="padding:24px">Loading…</div>';
    modal.classList.add('active');
    if (_docModalEscHandler) document.removeEventListener('keydown', _docModalEscHandler);
    _docModalEscHandler = (e) => { if (e.key === 'Escape') closeDocModal(); };
    document.addEventListener('keydown', _docModalEscHandler);
    _workspaceDocEditing = editing;
    _workspaceDocEditContainer = editing ? body : null;
    await _renderDocInto(filepath, body);
    if (!editing) _workspaceDocEditing = false;
  }

  function closeDocModal() {
    if (_workspaceDocEditing) {
      _workspaceDocEditing = false;
      _workspaceDocEditContainer = null;
    }
    const modal = document.getElementById('docViewModal');
    if (modal) modal.classList.remove('active');
    if (_docModalEscHandler) {
      document.removeEventListener('keydown', _docModalEscHandler);
      _docModalEscHandler = null;
    }
  }

  // Shared render helper: handles all file types and writes into `container`.
  // Sets the module-level _workspaceDocContent / _workspaceComments / _workspaceDocArtifact globals
  // that renderWorkspaceDoc reads. Does NOT touch navigation state (_workspaceDocPath,
  // sidebar active highlights, setLastWorkspaceDoc) — callers handle that.
  // Renders an HTML file in the workspace doc pane with a Rendered/Code
  // toggle. Mirrors cerebroRenderHtml; the pref is shared via
  // localStorage so opening the same file in Cerebro keeps the same view.
  async function _workspaceRenderHtml(container, filepath, absKey, mode) {
    // Race guard against the user navigating away mid-fetch — same
    // shape as the one in _renderDocInto.
    const _navWorkspacePath = (currentWorkspace && currentWorkspace.path) || null;
    const docRoot = _workspaceDocRoot || _navWorkspacePath;
    const _stillActiveNav = () => (
      _workspaceDocPath === filepath
      && currentWorkspace
      && currentWorkspace.path === _navWorkspacePath
      && (_workspaceDocRoot || currentWorkspace.path) === docRoot
    );
    const toolbar = `
      <div style="display:flex;align-items:center;gap:8px;margin:0 0 12px">
        <span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span>
        <span class="html-toolbar" style="display:flex;gap:4px">
          <button class="html-toggle ${mode==='rendered'?'active':''}" data-mode="rendered">🖼 Rendered</button>
          <button class="html-toggle ${mode==='code'?'active':''}" data-mode="code">&lt;/&gt; Code</button>
        </span>
      </div>`;
    if (mode === 'rendered') {
      const src = `/api/workspace-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      // Skip the re-mount when the iframe is already pointed at this src
      // (and the toolbar reflects 'rendered'). The WS index-updated event
      // re-runs this render path on every save anywhere in content/, and
      // re-creating the iframe causes a visible white flash while the new
      // document loads. The existing iframe is still live — leave it.
      const existing = container.querySelector('iframe.html-iframe');
      const activeBtn = container.querySelector('.html-toolbar .html-toggle.active');
      if (existing && existing.getAttribute('src') === src
          && activeBtn && activeBtn.getAttribute('data-mode') === 'rendered') {
        return;
      }
      if (!_stillActiveNav()) return;
      container.innerHTML = `<div style="padding:24px">${toolbar}<iframe class="html-iframe" src="${src}" onload="applyIframeDarkMode(this)"></iframe></div>`;
    } else {
      try {
        const r = await fetch(`/api/workspace-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`);
        if (!_stillActiveNav()) return;
        if (!r.ok) {
          const msg = await r.json().catch(() => ({}));
          container.innerHTML = `<div style="padding:24px">${toolbar}<p style="color:var(--red)">Error: ${esc(msg.detail || r.statusText)}</p></div>`;
        } else {
          const data = await r.json();
          if (!_stillActiveNav()) return;
          await ensureHighlight().catch(() => {});
          container.innerHTML = `<div style="padding:24px">${toolbar}<pre style="background:var(--bg-secondary);padding:14px;border-radius:6px;overflow:auto"><code class="language-html">${esc(data.content || '')}</code></pre></div>`;
          if (window.hljs) {
            container.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
          }
        }
      } catch (e) {
        if (!_stillActiveNav()) return;
        container.innerHTML = `<div style="padding:24px">${toolbar}<p style="color:var(--red)">Error: ${esc(e.message || e)}</p></div>`;
      }
    }
    container.querySelectorAll('.html-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = btn.getAttribute('data-mode');
        if (next === mode) return;
        setHtmlViewPref(absKey, next);
        _workspaceRenderHtml(container, filepath, absKey, next);
      });
    });
  }

  async function _renderDocInto(filepath, container, { preserveScroll = false } = {}) {
    // Capture the workspace that owned this render call so an async paint
    // landing AFTER the user has switched away to a different workspace
    // (or a different file in the same workspace) bails instead of
    // stomping the new view's content. _workspaceDocPath is set
    // synchronously by openWorkspaceDoc / selectRepo before this function
    // is called, so a mismatch here means a newer navigation has
    // already taken over `container` and we must not paint.
    const _navWorkspacePath = (currentWorkspace && currentWorkspace.path) || null;
    const docRoot = _workspaceDocRoot || _navWorkspacePath;
    const _stillActiveNav = () => (
      _workspaceDocPath === filepath
      && currentWorkspace
      && currentWorkspace.path === _navWorkspacePath
      && (_workspaceDocRoot || currentWorkspace.path) === docRoot
    );

    // Image files
    const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
    if (imageExts.some(ext => filepath.toLowerCase().endsWith(ext))) {
      if (!_stillActiveNav()) return;
      const src = `/api/workspace-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      container.innerHTML = `<div style="padding:24px;max-width:900px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:16px"><span style="font-size:12px;color:#484f58;font-family:monospace;flex:1">${esc(filepath)}</span></div><img src="${src}" style="max-width:100%;border-radius:4px"></div>`;
      return;
    }

    // PDF files: hand the raw bytes to the browser's built-in PDF viewer via
    // an iframe. /api/workspace-asset serves them as application/pdf with no
    // attachment disposition, so they display inline (zoom/page/print come
    // from the browser's own viewer chrome). Same anti-flicker guard as the
    // HTML viewer: the WS index-updated event re-runs this render on every
    // save under content/, and re-creating the iframe flashes + resets the
    // user's scroll/zoom — so leave a live iframe already pointed here alone.
    if (filepath.toLowerCase().endsWith('.pdf')) {
      if (!_stillActiveNav()) return;
      const src = `/api/workspace-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      const existing = container.querySelector('iframe.pdf-iframe');
      if (existing && existing.getAttribute('src') === src) return;
      container.innerHTML = `<div style="padding:24px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px"><span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span><a href="${src}" target="_blank" rel="noopener" style="font-size:11px;color:var(--text-secondary)">open ↗</a></div><iframe class="pdf-iframe" src="${esc(src)}" title="${esc(filepath)}"></iframe></div>`;
      return;
    }

    // Video files: native <video> player streaming from /api/workspace-asset.
    // FileResponse supports HTTP Range requests, so seeking works without
    // downloading the whole file. Same anti-flicker guard as the PDF
    // iframe: watcher-triggered re-renders (workspace mtime poll, WS events)
    // must leave an already-mounted player alone — recreating the element
    // would restart playback mid-watch.
    const videoExts = ['.mp4', '.webm', '.mov', '.m4v'];
    if (videoExts.some(ext => filepath.toLowerCase().endsWith(ext))) {
      if (!_stillActiveNav()) return;
      const src = `/api/workspace-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      const existing = container.querySelector('video.workspace-video');
      if (existing && existing.getAttribute('src') === src) return;
      container.innerHTML = `<div style="padding:24px;max-width:1100px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
          <span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span>
          <a href="${esc(src)}" target="_blank" rel="noopener" style="font-size:11px;color:var(--text-secondary)">open ↗</a>
        </div>
        <video class="workspace-video" src="${esc(src)}" controls playsinline preload="metadata" style="width:100%;max-height:calc(100vh - 220px);background:#000;border-radius:6px;outline:none"></video>
      </div>`;
      return;
    }

    // HTML files: rendered iframe by default, with a "Code" toggle to
    // view source instead. Choice is sticky per file via localStorage.
    if (/\.(html|htm)$/i.test(filepath)) {
      const absKey = docRoot + '/' + filepath;
      const mode = getHtmlViewPref(absKey);
      _workspaceRenderHtml(container, filepath, absKey, mode);
      return;
    }

    // Saved unified patches use the same file headers, line gutters,
    // word-level highlights, and Unified/Split layouts as live Git changes.
    if (/\.(diff|patch)$/i.test(filepath)) {
      try {
        await ensureHighlight().catch(() => {});
        const response = await fetch(`/api/workspace-diff-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`);
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || `Failed to load diff (${response.status})`);
        }
        const data = await response.json();
        if (!_stillActiveNav()) return;
        renderStoredDiffDocument(filepath, data, container);
      } catch (err) {
        if (!_stillActiveNav()) return;
        container.innerHTML = `<div class="no-repo"><p>Error: ${esc(err.message || err)}</p></div>`;
      }
      return;
    }

    // Notebooks: render cells via /api/nb — activateNotebookScripts runs post-inject.
    // A trailing editor lets you POST new cells to /api/nb/exec; the resulting
    // .ipynb write triggers the watcher, every open viewer re-renders.
    if (filepath.toLowerCase().endsWith('.ipynb')) {
      try {
        // Execution is vault-scoped, but notebooks in the framework Home
        // or another repository root are still useful documents. Render those
        // through the generic repository notebook endpoint without Run/Delete
        // controls; only a notebook inside the active vault gets a kernel.
        const notebookVault = _notebookVaultContext(currentWorkspace);
        const notebookVaultQuery = notebookVault.vaultId
          ? `&vault=${encodeURIComponent(notebookVault.vaultId)}` : '';
        const relPath = docRoot === currentWorkspace.path
          ? _vaultRelativeNotebookPathOrNull(
              currentWorkspace.path, filepath, notebookVault.vaultRoot,
            )
          : null;
        if (!relPath) {
          const readOnlyRes = await fetch(`/api/notebook?repo=${encodeURIComponent(docRoot)}&path=${encodeURIComponent(filepath)}`);
          if (!readOnlyRes.ok) {
            const detail = await readOnlyRes.json().catch(() => ({}));
            throw new Error(detail.detail || `Failed to load notebook (${readOnlyRes.status})`);
          }
          const readOnlyCells = await readOnlyRes.json();
          await Promise.all([
            ensureMarked().catch(() => {}),
            ensureHighlight().catch(() => {}),
          ]);
          if (!_stillActiveNav()) return;
          const readOnlyHeader = `<div class="nb-notebook-header"><span class="nb-notebook-path">${esc(filepath)}</span><span class="nb-kernel-badge">read-only notebook</span><span class="nb-notebook-updated">Move or copy into a vault workspace to execute</span></div>`;
          container.innerHTML = `<div style="padding:24px">${_renderNbJumpControls(readOnlyCells.length, _isNotebookCodeHidden(docRoot, filepath))}${readOnlyHeader}<div class="nb-container">${readOnlyCells.map((c, i) => renderNotebookCell(c, null, i)).join('')}</div></div>`;
          activateNotebookScripts(container);
          _bindNbNavigation(container, docRoot, filepath, { restore: !preserveScroll });
          return;
        }

        // A brand-new notebook 404s on /api/nb; treat that as "empty, ready to
        // receive its first cell" rather than an error.
        const [nbRes, sessRes, runtimeRes] = await Promise.all([
          fetch(`/api/nb?path=${encodeURIComponent(relPath)}${notebookVaultQuery}`),
          fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}${notebookVaultQuery}`),
          fetch(`/api/nb/runtime?path=${encodeURIComponent(relPath)}${notebookVaultQuery}`),
        ]);
        let nb = { path: relPath, cells: [], mtime: null };
        let notFound = false;
        if (nbRes.ok) {
          nb = await nbRes.json();
        } else if (nbRes.status === 404) {
          notFound = true;
        } else {
          const e = await nbRes.json().catch(() => ({}));
          throw new Error(e.detail || ('Failed to load notebook (' + nbRes.status + ')'));
        }
        const sessionInfo = sessRes.ok ? await sessRes.json() : {};
        const session = sessionInfo.session || '';
        const provider = sessionInfo.provider || 'local';
        const runtime = runtimeRes.ok ? await runtimeRes.json() : { status: 'unavailable', spec: null };
        // Fetch replay state after the durable notebook response. The live API
        // cross-checks each run against its on-disk marker, which makes this
        // pair a consistent view even during the final-cell replacement.
        const liveRes = await fetch(
          `/api/nb/live?path=${encodeURIComponent(relPath)}${notebookVaultQuery}`,
        );
        const liveInfo = liveRes.ok ? await liveRes.json() : { executions: [] };
        if ((liveInfo.executions || []).length === 0
            && (nb.cells || []).some(cell => cell?.metadata?.lab_pending === true)) {
          // The file may have completed between the first /nb response and the
          // /live cross-check. Refetch once so that race cannot leave a newly
          // opened view showing a stale spinner with no live run behind it.
          const latestNbRes = await fetch(
            `/api/nb?path=${encodeURIComponent(relPath)}${notebookVaultQuery}`,
            { cache: 'no-store' },
          );
          if (latestNbRes.ok) nb = await latestNbRes.json();
        }
        const notebookLiveKey = _nbLiveKey(notebookVault.vaultId, relPath);
        if ((liveInfo.executions || []).length > 0) _nbLivePaths.add(notebookLiveKey);
        else _nbLivePaths.delete(notebookLiveKey);

        // Baseline "seen" state for any cell we haven't observed before so the
        // first render of a notebook is calm (nothing flagged NEW). Subsequent
        // execs bump cell.execution_count past the baseline → NEW indicator.
        //
        // Two guards on when to baseline:
        //   1. !preserveScroll — watcher-triggered re-renders after a Run
        //      must not stamp the new exec count; that would auto-acknowledge
        //      the output the user hasn't actually seen yet.
        //   2. First-EVER open of this notebook (_nbGetLastViewed == 0).
        //      On any later open we deliberately leave the baselines alone:
        //      if Claude (or a previous tab) ran cells while the user was
        //      looking elsewhere, the freshly bumped exec_counts must stay
        //      above the stored baselines so _isCellSeen reports false and
        //      the green NEW edge appears on those cells. Without this
        //      guard, every reopen would re-baseline to the current count
        //      and the user could never see what changed in their absence.
        const everViewed = _nbGetLastViewed(filepath) > 0;
        if (!preserveScroll && !everViewed) {
          (nb.cells || []).forEach((c, i) => _baselineSeenIfNew(relPath, c.id || i, c.execution_count));
        }
        // Stamp this open as "viewed" so the sidebar's amber unseen-results
        // dot disappears for this file. Use the current file mtime so any
        // FUTURE mtime advance (new cell, new outputs) re-triggers the dot.
        // Skip on `preserveScroll` (the mtime poller's auto-refresh path) —
        // otherwise we'd keep restamping the timestamp on every poll while
        // the file is open, and the amber "new results" dot would never
        // appear for the currently-focused notebook even though new cells
        // are landing.
        if (nb.mtime && !preserveScroll) _nbMarkViewed(filepath, nb.mtime);

        const updatedLabel = nb.mtime
          ? 'updated ' + new Date(nb.mtime * 1000).toLocaleString()
          : (notFound ? 'new notebook' : '');
        const kernelLabel = 'Workspace Jupyter kernel';
        const sessionBadge = session
          ? `<span title="Dedicated kernel session pinned to this .ipynb file path; another notebook gets another kernel" class="nb-kernel-badge">${kernelLabel} · ${esc(session)}</span>`
          : '';
        const runtimeLabel = `Runtime: ${runtime.status || 'unconfigured'}`;
        const runtimeBadge = `<button class="nb-runtime-open nb-runtime-status-${esc(runtime.status || 'unconfigured')}" type="button" data-nb-tooltip="${escAttr(runtimeLabel)}" aria-label="${escAttr(runtimeLabel)}"><span aria-hidden="true">⚙</span></button>`;
        const notebookRunAllActive = _nbRunAllState.has(
          _nbRunAllKey(relPath, notebookVault.vaultId),
        );
        const restartBtnHtml = session
          ? `<button class="nb-restart-kernel" type="button" data-nb-tooltip="Restart kernel" aria-label="Restart kernel"${notebookRunAllActive ? ' disabled' : ''}><span aria-hidden="true">↻</span></button>`
          : '';
        const interruptBtnHtml = provider === 'local'
          ? `<button class="nb-interrupt-kernel" type="button" data-nb-tooltip="Interrupt kernel" aria-label="Interrupt kernel"><span aria-hidden="true">■</span></button>`
          : '';
        const runAllButtonsHtml = renderNbRunAllButtons(
          relPath,
          notebookVault.vaultId,
          (nb.cells || []).filter(cell => cell && cell.cell_type === 'code').length,
          (liveInfo.executions || []).length > 0,
        );
        const toolbarActionsHtml = `${runtimeBadge}${runAllButtonsHtml}${interruptBtnHtml}${restartBtnHtml}`;
        const notebookListBtnHtml = `<button class="nb-notebook-list" type="button" onclick="openWorkspaceNotebooks({showLauncher:true})" title="Show every notebook in this workspace">☷ All notebooks</button>`;
        const header = `<div class="nb-notebook-header"><span class="nb-notebook-path">${esc(filepath)}</span>${notebookListBtnHtml}${sessionBadge}<span class="nb-notebook-updated">${updatedLabel}</span></div>`;
        const pendingList = _readPending(relPath);
        const liveByCell = new Map(
          (liveInfo.executions || [])
            .filter(run => run && run.cell_id)
            .map(run => [String(run.cell_id), run])
        );
        // Reconnect/open resilience: overlay the server's in-memory execution
        // snapshot onto the atomically-checkpointed .ipynb placeholder. A
        // browser that arrives halfway through a 30-minute query immediately
        // sees every output collected so far, then continues with WS deltas.
        const realCells = (nb.cells || []).map((cell) => {
          const live = cell && cell.id ? liveByCell.get(String(cell.id)) : null;
          if (!live) return cell;
          return {
            ...cell,
            source: live.source != null ? live.source : cell.source,
            outputs: Array.isArray(live.outputs) ? live.outputs : cell.outputs,
            execution_count: live.execution_count != null
              ? live.execution_count : cell.execution_count,
            metadata: {
              ...(cell.metadata || {}),
              lab_pending: true,
              lab_run_id: live.run_id,
              lab_actor: live.actor,
              lab_action: cell.metadata?.lab_pending
                ? cell.metadata.lab_action : 'modified',
              lab_started_at: live.started_at,
            },
          };
        });
        // A created cell can land between the /nb response and the later /live
        // response. Materialize that snapshot too; otherwise the viewer would
        // know a run exists but have no DOM cell for its subsequent deltas.
        for (const live of (liveInfo.executions || [])) {
          if (!live?.cell_id || realCells.some(cell => String(cell?.id || '') === String(live.cell_id))) {
            continue;
          }
          const at = Math.max(0, Math.min(Number(live.cell_index) || 0, realCells.length));
          realCells.splice(at, 0, {
            id: live.cell_id,
            cell_type: 'code',
            source: live.source || '',
            outputs: Array.isArray(live.outputs) ? live.outputs : [],
            execution_count: live.execution_count ?? null,
            metadata: {
              lab_pending: true,
              lab_run_id: live.run_id,
              lab_actor: live.actor,
              lab_action: 'created',
              lab_started_at: live.started_at,
            },
          });
        }
        await Promise.all([
          ensureMarked().catch(() => {}),
          ensureHighlight().catch(() => {}),
        ]);
        // Build the cells host: an "insert here" bar before every real cell,
        // any pending cells targeting that position, the real cell itself,
        // a final inserter after the last real cell, and finally any pending
        // cells with no insertAt (append-style).
        function _renderPendingFor(at) {
          return pendingList
            .filter((p) => (at == null ? (p.insertAt == null) : (p.insertAt === at)))
            .map((p) => {
              const blank = { cell_type: 'code', source: p.code || '', outputs: [], execution_count: null };
              return renderNbCellInteractive(blank, -1, relPath, {
                pending: true, pendingId: p.id, insertAt: p.insertAt,
              });
            }).join('');
        }
        function _inserter(at) {
          return `<div class="nb-cell-inserter" data-insert-at="${at}"><button class="nb-cell-insert-btn" type="button" title="Insert a new cell here">＋ insert cell</button></div>`;
        }
        // Pre-compute queue positions for the server-side running
        // placeholders so each one renders [1], [2], [3] in submission
        // order instead of all showing [*]. Cells appear in append order
        // in the .ipynb, so position-in-array == queue order.
        const _pendingPositions = {};
        let _qpos = 0;
        realCells.forEach((c, i) => {
          if (c && c.metadata && c.metadata.lab_pending === true) {
            _qpos += 1;
            _pendingPositions[i] = _qpos;
          }
        });
        let cellsHostHtml = '';
        realCells.forEach((c, i) => {
          cellsHostHtml += _inserter(i);
          cellsHostHtml += _renderPendingFor(i);
          const live = c && c.id ? liveByCell.get(String(c.id)) : null;
          cellsHostHtml += renderNbCellInteractive(c, i, relPath, {
            queuePos: _pendingPositions[i] || null,
            liveSequence: live ? live.sequence : null,
          });
        });
        cellsHostHtml += _inserter(realCells.length);
        cellsHostHtml += _renderPendingFor(null);

        const addBtnHtml = renderNbAddCellButton();
        // Race guard: notebook fetches can take seconds. If the user
        // navigated to a different file (or workspace) while we were
        // fetching, do NOT stomp the new view's content with this
        // notebook's HTML.
        if (!_stillActiveNav()) return;
        const notebookPositionScope = notebookVault.vaultId || notebookVault.vaultRoot;
        container.innerHTML = `<div style="padding:24px">${_renderNbJumpControls(realCells.length, _isNotebookCodeHidden(notebookPositionScope, relPath), toolbarActionsHtml)}${header}${renderNbRuntimePanel(runtime, relPath)}<div class="nb-container">${cellsHostHtml}</div>${addBtnHtml}</div>`;
        activateNotebookScripts(container);
        _ensureNbElapsedTicker();
        // Bind every interactive cell + inserters + the trailing add-cell
        // button + restart.
        container.querySelectorAll('.nb-cell-interactive').forEach((wrap) => {
          bindNbCellInteractive(
            wrap, relPath, filepath, null, notebookVault.vaultId,
          );
        });
        bindNbCellInserters(container, relPath, filepath, notebookVault.vaultId);
        bindNbAddCellButton(container, relPath, filepath, notebookVault.vaultId);
        bindNbRunAll(container, relPath, filepath, notebookVault.vaultId);
        bindNbRestartKernel(container, relPath, filepath, notebookVault.vaultId);
        bindNbInterruptKernel(container, relPath, notebookVault.vaultId);
        bindNbRuntimePanel(container, relPath, filepath, notebookVault.vaultId);
        _bindNbNavigation(
          container,
          notebookPositionScope,
          relPath,
          { restore: !preserveScroll },
        );
      } catch (err) {
        if (!_stillActiveNav()) return;
        container.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
      }
      return;
    }

    // All other files: fetch content + comments + artifact info, then renderWorkspaceDoc
    try {
      const lowerPath = filepath.toLowerCase();
      const needsMarked = /\.(md|markdown)$/.test(lowerPath);
      const needsHighlight = needsMarked || /\.json$/.test(lowerPath) || !!filenameLang(filepath);
      await Promise.all([
        needsMarked ? ensureMarked().catch(() => {}) : Promise.resolve(),
        needsHighlight ? ensureHighlight().catch(() => {}) : Promise.resolve(),
      ]);

      // Optimistic paint from the doc cache. When this file has been
      // opened earlier in the browser session, paint it synchronously
      // here so the user sees the page immediately. The three fetches
      // below still fire to reconcile; we only re-render if the fresh
      // data differs (skip-on-match avoids flicker for unchanged docs).
      const cacheKey = _workspaceDocCacheKey(docRoot, filepath);
      const cached = _workspaceDocCache.get(cacheKey);
      if (cached) {
        _workspaceDocContent = cached.content;
        _workspaceComments = cached.comments;
        _workspaceDocArtifact = cached.artifact;
        if (!_stillActiveNav()) return;
        renderWorkspaceDoc(filepath, container);
      }
      const [fileRes, commentsRes, infoRes] = await Promise.all([
        fetch(`/api/workspace-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`),
        fetch(`/api/workspace-comments?path=${encodeURIComponent(docRoot)}`),
        fetch(`/api/workspace-info?path=${encodeURIComponent(docRoot)}`),
      ]);
      if (!fileRes.ok) { const e = await fileRes.json(); throw new Error(e.detail); }
      const data = await fileRes.json();
      const newComments = (await commentsRes.json()).filter(c => c.file === filepath);
      const info = infoRes.ok ? await infoRes.json() : {};
      const artifacts = Array.isArray(info.artifacts) ? info.artifacts : [];
      const newArtifact = artifacts.find(a => a && a.file === filepath) || null;
      _workspaceDocCache.set(cacheKey, {content: data.content, comments: newComments, artifact: newArtifact});
      // Skip re-render if we already painted from cache and the server
      // returned identical data — avoids a flicker on every warm
      // switch when nothing has changed.
      if (cached
          && data.content === cached.content
          && JSON.stringify(newComments) === JSON.stringify(cached.comments)
          && JSON.stringify(newArtifact) === JSON.stringify(cached.artifact)) {
        return;
      }
      // Race guard: drop a late fetch if the user has navigated away.
      // (We still updated the cache above, so the next visit benefits.)
      if (!_stillActiveNav()) return;
      _workspaceDocContent = data.content;
      _workspaceComments = newComments;
      _workspaceDocArtifact = newArtifact;
      renderWorkspaceDoc(filepath, container);
    } catch (err) {
      if (!_stillActiveNav()) return;
      container.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
    }
  }

  function openWorkspaceDocFromFileClick(filepath, {root = null} = {}) {
    if (!currentWorkspace) return;
    const docRoot = root || currentWorkspace.path;
    _termCancelPendingLinkedFileOpen();
    _termSyncFromFileClick(docRoot, filepath);
    return openWorkspaceDoc(filepath, {root});
  }
  window.openWorkspaceDocFromFileClick = openWorkspaceDocFromFileClick;

  async function openWorkspaceDoc(filepath, {preserveScroll = false, root = null} = {}) {
    if (!currentWorkspace) return;
    _clearNbNavigation();
    // Pseudo-paths starting with `__proxy__/` are not real files — they
    // refer to a declared local-dev-server proxy. Route to the iframe
    // renderer; everything else (active highlight, last-opened memory)
    // is handled inside openWorkspaceProxy.
    if (typeof filepath === 'string' && filepath.startsWith('__proxy__/')) {
      const name = filepath.slice('__proxy__/'.length);
      return openWorkspaceProxy(name);
    }
    const docRoot = root || (preserveScroll && _workspaceDocRoot) || currentWorkspace.path;
    _workspaceDocRoot = docRoot;
    _contextSubView = 'document';
    _workspaceDocPath = filepath;
    if (document.body.classList.contains('assistant-active')) {
      window.LAB_ASSISTANT_DOCUMENT_OPEN = true;
    }
    if (filepath.toLowerCase().endsWith('.ipynb')) {
      setLastWorkspaceNotebook(currentWorkspace.path, filepath);
    }
    renderRepoTabs();
    _workspaceDocEditing = false;
    setLastWorkspaceDoc(docRoot, filepath);
    // Coming back from a server view (which collapses the sidebar by
    // default) — restore this workspace's own sidebar preference.
    _sidebarApplyForView();
    const content = document.getElementById('content');
    const prevScroll = preserveScroll ? content.scrollTop : 0;
    // Skip the "Loading..." flash when we have a cached copy of this
    // doc — _renderDocInto's text branch will paint synchronously from
    // the cache below. For cache misses (or non-text files we don't
    // cache: notebooks/HTML/images) we still show the spinner.
    if (!preserveScroll) {
      const cacheKey = _workspaceDocCacheKey(docRoot, filepath);
      if (!_workspaceDocCache.has(cacheKey)) {
        content.innerHTML = '<div class="loading">Loading...</div>';
      }
    }

    // Highlight active in sidebar. Match on data-filepath (exact path) so the
    // mark lands on a single entry even when multiple files share a basename.
    // The sidebar rebuilders (_refreshWorkspaceSidebar / selfPopulateSidebar)
    // also bake .active into the HTML they emit, so this is just for the
    // immediate click — we don't have to wait for the next rebuild to repaint.
    document.querySelectorAll('.sidebar-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll(`.sidebar-file[data-filepath="${CSS.escape(filepath)}"]`).forEach(el => el.classList.add('active'));

    // preserveScroll early-return: skip re-render when content/comments/artifact unchanged
    if (preserveScroll) {
      // Capture the workspace/file at entry so an async paint landing
      // after the user has navigated to a different file bails instead
      // of stomping the new view.
      const _navWorkspacePath = currentWorkspace.path;
      const _stillActiveNav = () => (
        _workspaceDocPath === filepath && currentWorkspace && currentWorkspace.path === _navWorkspacePath
        && _workspaceDocRoot === docRoot
      );
      // Notebooks, images, video, and HTML iframes have no meaningful _workspaceDocContent
      // to diff against — delegate straight to _renderDocInto so they get the correct
      // renderer (its per-type guards keep live players/iframes unmolested).
      const lower = filepath.toLowerCase();
      const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
      const videoExts = ['.mp4', '.webm', '.mov', '.m4v'];
      if (lower.endsWith('.ipynb') || lower.endsWith('.html') || lower.endsWith('.pdf') || lower.endsWith('.diff') || lower.endsWith('.patch') || imageExts.some(ext => lower.endsWith(ext)) || videoExts.some(ext => lower.endsWith(ext))) {
        await _renderDocInto(filepath, content, { preserveScroll: true });
        if (!_stillActiveNav()) return;
        content.scrollTop = prevScroll;
        return;
      }
      try {
        const [fileRes, commentsRes, infoRes] = await Promise.all([
          fetch(`/api/workspace-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`),
          fetch(`/api/workspace-comments?path=${encodeURIComponent(docRoot)}`),
          fetch(`/api/workspace-info?path=${encodeURIComponent(docRoot)}`),
        ]);
        if (!fileRes.ok) { const e = await fileRes.json(); throw new Error(e.detail); }
        const data = await fileRes.json();
        const newComments = (await commentsRes.json()).filter(c => c.file === filepath);
        const info = infoRes.ok ? await infoRes.json() : {};
        const artifacts = Array.isArray(info.artifacts) ? info.artifacts : [];
        const newArtifact = artifacts.find(a => a && a.file === filepath) || null;
        // Refresh the cache with the latest server state. Keeps warm
        // tab-switches in sync with WS-triggered refreshes — without
        // this write, the cache could stay stale after Claude/an
        // external editor edits the file while it's open.
        _workspaceDocCache.set(_workspaceDocCacheKey(docRoot, filepath),
          {content: data.content, comments: newComments, artifact: newArtifact});
        if (data.content === _workspaceDocContent
            && JSON.stringify(newComments) === JSON.stringify(_workspaceComments)
            && JSON.stringify(newArtifact) === JSON.stringify(_workspaceDocArtifact)) {
          return;
        }
        if (!_stillActiveNav()) return;
        _workspaceDocContent = data.content;
        _workspaceComments = newComments;
        _workspaceDocArtifact = newArtifact;
        renderWorkspaceDoc(filepath, content);
        content.scrollTop = prevScroll;
      } catch (err) {
        if (!_stillActiveNav()) return;
        content.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
      }
      return;
    }

    await _renderDocInto(filepath, content);
  }

  // ─── Workspace proxies (per-workspace reverse-proxy to a local dev server) ───
  // Backed by /api/proxy/<workspace>/<name>/<path> + /ws/proxy/... in
  // routes/proxy.py. Declared in servers.json (legacy workspace.json proxies
  // remain readable when the standalone file does not exist):
  //   {"servers": [{"name": "frontend", "host": "localhost", "port": 3000, "path": "/"}]}
  // The frontend treats each proxy as a pseudo-file so all the sidebar
  // active-highlighting, "last opened" persistence, and warm-switch
  // caching work without special-casing. The synthetic doc path is
  // `__proxy__/<name>` (chosen so it cannot collide with a real file
  // path since `__proxy__` starts with `__` which is reserved).
  function _proxyFromCachedSidebar(name) {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return null;
    const cached = _workspaceSidebarCache.get(currentWorkspace.path);
    if (!cached || !Array.isArray(cached.proxies)) return null;
    return cached.proxies.find(p => p && p.name === name) || null;
  }

  function _proxyMountPath(workspaceId, name, vaultId = null) {
    if (vaultId) {
      return `/api/vault-proxy/${encodeURIComponent(vaultId)}/${encodeURIComponent(workspaceId)}/${encodeURIComponent(name)}/`;
    }
    return `/api/proxy/${encodeURIComponent(workspaceId)}/${encodeURIComponent(name)}/`;
  }

  // Direct upstream URL (http://host:port/path) for a proxy entry,
  // regardless of proxy/direct mode. Returns null if there's no port.
  // Because the upstream runs on a *different port* it's a different
  // origin from the lab — so opening it escapes the installed-PWA scope
  // and Chrome gives it a real browser window (with the address bar)
  // instead of a frameless app popup. Used by "Pop out" and by
  // direct-mode iframes.
  function _proxyDirectUrl(p) {
    if (!p || !p.port) return null;
    let host = String(p.host || 'localhost').replace(/^https?:\/\//, '').replace(/\/+$/, '');
    if (!host || host === '0.0.0.0') host = 'localhost';
    const path = (p && p.path) ? String(p.path) : '/';
    const cleanPath = path.startsWith('/') ? path : '/' + path;
    return `http://${host}:${p.port}${cleanPath}`;
  }

  function _proxyInitialUrl(p, name) {
    const workspaceId = currentWorkspace && currentWorkspace.name;
    if (!workspaceId || !name) return null;
    // Direct mode: iframe straight to the upstream origin. Faster + no
    // path rewriting needed, but the browser must be able to reach
    // the upstream host:port directly (so won't work over an SSH
    // port-forward where only the lab port is exposed).
    if (p && p.mode === 'direct') return _proxyDirectUrl(p);
    const path = (p && p.path) ? String(p.path) : '/';
    const initial = path.replace(/^\/+/, '');
    return _proxyMountPath(workspaceId, name, _workspaceVaultId(currentWorkspace)) + initial;
  }

  // Inline iframe + controls bar. The controls let the user reload the
  // inner app, copy the proxied URL, pop it out into a new tab (so it
  // lives alongside other browser tabs), or expand into a borderless
  // fullscreen view that hides the rest of the lab UI chrome.
  async function openWorkspaceProxy(name) {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    if (!name) return;
    // The iframe hosts a live, stateful app — never rebuild it when this
    // proxy is already the active view (file-watcher refreshes, sidebar
    // re-clicks, and tab revisits all funnel here and used to reload the
    // inner app, losing its state). The toolbar "Reload" button is the
    // explicit way to restart it.
    const existingWrap = document.getElementById('proxyWrap');
    if (existingWrap && existingWrap.dataset.proxy === name && document.getElementById('proxyIframe')) {
      _workspaceDocPath = '__proxy__/' + name;
      renderRepoTabs();
      _sidebarApplyForView();
      return;
    }
    const p = _proxyFromCachedSidebar(name);
    const proxyPath = '__proxy__/' + name;
    _workspaceDocPath = proxyPath;
    _workspaceDocEditing = false;
    setLastWorkspaceDoc(currentWorkspace.path, proxyPath);
    // Server views default to a collapsed files sidebar so the embedded
    // app gets the full left + center width (per-view remembered state —
    // the Files edge handle still brings it back).
    _sidebarApplyForView();
    // The server view replaces whatever was in #content — if a repo diff
    // view was open, drop the repo selection and its diff tabs so the top
    // bar highlights this server's tab instead.
    currentRepo = null;
    currentRepoInWorkspace = null;
    const diffTabsEl = document.getElementById('diffTabs');
    if (diffTabsEl) diffTabsEl.style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    renderRepoTabs();
    const content = document.getElementById('content');
    if (!content) return;
    const url = _proxyInitialUrl(p, name);
    if (!url) { content.innerHTML = `<div class="no-repo"><p>Proxy ${esc(name)} not configured.</p></div>`; return; }

    // Highlight active row in sidebar.
    document.querySelectorAll('.sidebar-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll(`.sidebar-file[data-filepath="${CSS.escape(proxyPath)}"]`).forEach(el => el.classList.add('active'));

    const host = (p && p.host) || 'localhost';
    const port = (p && p.port) || '?';
    const label = (p && p.label) || name;
    const safeName = name.replace(/'/g, "\\'");
    content.innerHTML = `
      <div id="proxyWrap" data-proxy="${esc(name)}" style="display:flex;flex-direction:column;height:calc(100vh - 130px);min-height:480px">
        <div class="proxy-toolbar" style="display:flex;align-items:center;gap:8px;padding:6px 12px;background:var(--bg-secondary);border-bottom:1px solid var(--border);flex-shrink:0">
          <span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace">${esc(label)}</span>
          <span style="font-size:11px;color:var(--text-dim);font-family:ui-monospace,monospace">→ ${esc(host)}:${esc(String(port))}</span>
          <span style="flex:1"></span>
          <button onclick="reloadWorkspaceProxy('${safeName}')" title="Reload" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x21BB; Reload</button>
          <button onclick="openWorkspaceProxyTab('${safeName}')" title="Open in new browser tab" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">Pop out &#x2197;</button>
          <button onclick="copyWorkspaceProxyInstallCmd('${safeName}', this)" title="Copy osacompile command to create a Chrome standalone-window app for this URL" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x1F4E6; Install</button>
          <button onclick="copyWorkspaceProxyUninstallCmd('${safeName}', this)" title="Copy command to remove the installed Chrome app from $HOME/Applications" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x1F5D1; Uninstall</button>
          <button onclick="toggleWorkspaceProxyFullscreen()" id="proxyFullscreenBtn" title="Expand to fill the viewport (Esc to exit)" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x26F6; Fullscreen</button>
        </div>
        <iframe id="proxyIframe" src="${esc(url)}" style="flex:1;width:100%;border:0;background:#fff" onload="applyIframeDarkMode(this)"></iframe>
      </div>
    `;
  }

  function reloadWorkspaceProxy(name) {
    const iframe = document.getElementById('proxyIframe');
    if (!iframe) return openWorkspaceProxy(name);
    // Force a full reload (drops the HMR client too) instead of just
    // re-pointing the src — bypasses cached errored states.
    try { iframe.contentWindow.location.reload(); }
    catch { iframe.src = iframe.src; }
  }

  function openWorkspaceProxyTab(name) {
    const p = _proxyFromCachedSidebar(name);
    // Pop out via the same-origin /api/proxy mount so the new tab stays
    // on the lab origin (shared cookies, reachable wherever the lab is
    // reachable). Falls back to the direct upstream URL only if we
    // can't build a proxy mount (no current workspace id).
    const url = _proxyInitialUrl(p, name) || _proxyDirectUrl(p);
    if (url) window.open(url, '_blank', 'noopener');
  }

  function _workspaceProxyAppName(name) {
    return String(name || '').replace(/[^A-Za-z0-9_-]/g, '');
  }

  function _copyWorkspaceProxyCommand(cmd, btn) {
    const done = () => {
      if (!btn) return;
      const original = btn.innerHTML;
      btn.innerHTML = '&#x2713; Copied';
      setTimeout(() => { btn.innerHTML = original; }, 1200);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(cmd).then(done, () => {});
    } else {
      // Fallback for non-secure contexts where the async Clipboard API
      // isn't available.
      const ta = document.createElement('textarea');
      ta.value = cmd; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); done(); } catch {}
      document.body.removeChild(ta);
    }
  }

  function copyWorkspaceProxyInstallCmd(name, btn) {
    const p = _proxyFromCachedSidebar(name);
    const rel = _proxyInitialUrl(p, name);
    // Absolute URL: relative proxy mount paths become absolute by joining
    // with the lab origin; direct URLs are already absolute.
    const url = rel && rel.startsWith('/') ? location.origin + rel : (rel || _proxyDirectUrl(p));
    if (!url) return;
    // osacompile command that builds a Chrome standalone-window .app
    // pointing at this proxy URL. Proxy names created from the modal are
    // already limited to [A-Za-z0-9_-]; keep the generated filename under
    // that same contract so install and uninstall target the same path.
    const safeName = _workspaceProxyAppName(name);
    if (!safeName) return;
    const safeUrl = String(url).replace(/["\\]/g, '');
    // Find-or-focus: `open -na ... --app=` ALWAYS spawns a new window, so
    // launching the .app repeatedly (Alfred, Spotlight) piled up duplicate
    // instances. The applet now scans Chrome's windows for a tab already on
    // this URL and raises it; only when none exists does it open a fresh
    // app window. First launch prompts once to allow controlling Chrome.
    const slashUrl = safeUrl.endsWith('/') ? safeUrl : safeUrl + '/';
    const bareUrl = slashUrl.slice(0, -1);
    const cmd = [
      `osacompile -o "$HOME/Applications/${safeName}.app"`,
      `-e 'set appUrl to "${slashUrl}"'`,
      `-e 'if application "Google Chrome" is running then'`,
      `-e 'tell application "Google Chrome"'`,
      `-e 'repeat with w in windows'`,
      `-e 'repeat with t in tabs of w'`,
      `-e 'if (URL of t is "${bareUrl}") or (URL of t starts with appUrl) then'`,
      `-e 'set minimized of w to false'`,
      `-e 'set index of w to 1'`,
      `-e 'activate'`,
      `-e 'return'`,
      `-e 'end if'`,
      `-e 'end repeat'`,
      `-e 'end repeat'`,
      `-e 'end tell'`,
      `-e 'end if'`,
      `-e 'do shell script "open -na \\"Google Chrome\\" --args --app=\\"" & appUrl & "\\""'`,
    ].join(' ');
    _copyWorkspaceProxyCommand(cmd, btn);
  }

  function copyWorkspaceProxyUninstallCmd(name, btn) {
    const safeName = _workspaceProxyAppName(name);
    if (!safeName) return;
    const cmd = `rm -rf "$HOME/Applications/${safeName}.app"`;
    _copyWorkspaceProxyCommand(cmd, btn);
  }

  // Fullscreen: hide the sidebar, term panel, attrs/repo/diff strips so
  // the iframe fills the viewport. Esc exits. Same effect as the user's
  // browser fullscreen but keeps the lab origin (cookies, lab UI WS).
  let _proxyEscHandler = null;
  function toggleWorkspaceProxyFullscreen() {
    const wrap = document.getElementById('proxyWrap');
    if (!wrap) return;
    const on = document.body.classList.toggle('proxy-fullscreen');
    const btn = document.getElementById('proxyFullscreenBtn');
    if (btn) btn.innerHTML = on ? '&#x26F6; Exit fullscreen' : '&#x26F6; Fullscreen';
    if (on) {
      _proxyEscHandler = (ev) => {
        if (ev.key === 'Escape') toggleWorkspaceProxyFullscreen();
      };
      document.addEventListener('keydown', _proxyEscHandler);
    } else if (_proxyEscHandler) {
      document.removeEventListener('keydown', _proxyEscHandler);
      _proxyEscHandler = null;
    }
  }

  // Sidebar "blue dot" entry point — open the notebook AND scroll the first
  // unread cell into view. Defaults to the same openWorkspaceDoc path so the
  // file lands the same way the user would by clicking the row, then waits
  // one paint to make sure the cell HTML is in the DOM before scrolling.
  // Used as the dot's onclick (with event.stopPropagation() at the call site
  // so the surrounding row click doesn't double-fire).
  async function openWorkspaceDocAndJumpToUnseen(filepath, root = null) {
    await openWorkspaceDoc(filepath, root ? {root} : {});
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const target = document.querySelector('#content .nb-cell-unseen');
        if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
      });
    });
  }

  function toggleCommentsPanel(btn) {
    const collapsed = localStorage.getItem('workspaceDocCommentsCollapsed') === '0' ? '1' : '0';
    localStorage.setItem('workspaceDocCommentsCollapsed', collapsed);
    // Scope lookups to the same render container as the clicked button so
    // inline-pane and modal don't interfere when both are in the DOM.
    const root = (btn && btn.closest('#content, #docModalBody')) || document;
    const panel = root.querySelector('#commentsMargin');
    if (!panel) return;
    if (collapsed === '1') {
      panel.style.display = 'none';
      btn.title = 'Show comments';
    } else {
      panel.style.display = '';
      btn.title = 'Hide comments';
    }
    const hasComments = panel.querySelectorAll('.comment-card').length > 0;
    btn.style.color = (collapsed === '0' && hasComments) ? '#388bfd' : '#8b949e';
    btn.style.borderColor = (collapsed === '0' && hasComments) ? '#388bfd' : '#30363d';
  }

  function _resolveRelPath(baseDir, href) {
    // Normalize ".." and "." segments in a relative path.
    // baseDir: directory of the source file (e.g. "docs"), no trailing slash, may be "".
    // href: relative href (e.g. "../assets/foo.png" or "./img.png" or "img.png").
    // Returns a clean path like "assets/foo.png".
    if (!href || href.startsWith('/')) return href;
    const parts = (baseDir ? baseDir.split('/') : []).concat(href.split('/'));
    const out = [];
    for (const p of parts) {
      if (p === '' || p === '.') continue;
      if (p === '..') { out.pop(); continue; }
      out.push(p);
    }
    return out.join('/');
  }

  function renderWorkspaceDoc(filepath, container) {
    if (!container) container = document.getElementById('content');
    const fn = filepath.replace(/'/g, "\\'");
    const commentsCollapsed = localStorage.getItem('workspaceDocCommentsCollapsed') !== '0';

    // Two-column: doc left, comments right
    let html = `<div style="display:flex;gap:0;position:relative">`;

    // Doc column
    html += `<div class="workspace-content" style="padding:24px;flex:1;min-width:0">`;
    // Header with edit/save buttons
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">`;
    html += `<span style="font-size:12px;color:#484f58;font-family:monospace;flex:1">${esc(filepath)}</span>`;
    if (!_workspaceDocEditing) {
      html += `<button onclick="copyForGDocs(event)" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">&#x1F4CB; Copy</button>`;
      html += `<button onclick="startWorkspaceDocEdit()" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Edit</button>`;
      html += `<button onclick="linkWorkspaceDocArtifact('${fn}')" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer" title="Attach the online URL (Google Doc, etc.) that mirrors this file">&#x1F517; Link</button>`;
      const toggleColor = (!commentsCollapsed && _workspaceComments.length > 0) ? '#388bfd' : '#8b949e';
      const toggleBorder = (!commentsCollapsed && _workspaceComments.length > 0) ? '#388bfd' : '#30363d';
      const toggleTitle = commentsCollapsed ? 'Show comments' : 'Hide comments';
      const commentCount = _workspaceComments.length > 0 ? ` (${_workspaceComments.length})` : '';
      html += `<button id="commentsToggleBtn" onclick="toggleCommentsPanel(this)" style="background:#21262d;color:${toggleColor};border:1px solid ${toggleBorder};padding:4px 10px;border-radius:4px;font-size:12px;cursor:pointer" title="${toggleTitle}">&#x1F4AC;${commentCount}</button>`;
    } else {
      html += `<button onclick="saveWorkspaceDoc('${fn}')" style="background:#238636;color:#fff;border:1px solid #238636;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Save</button>`;
      html += `<button onclick="cancelWorkspaceDocEdit('${fn}')" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Cancel</button>`;
    }
    html += `</div>`;

    // "Published at" banner — surfaces the workspace.json.artifacts[] entry
    // whose `file` field matches this doc. Reminds the user that this
    // local file has a canonical online version (GDoc, Confluence, etc.)
    // so edits can be mirrored there.
    if (_workspaceDocArtifact && _workspaceDocArtifact.url) {
      const label = _workspaceDocArtifact.title || _workspaceDocArtifact.type || 'online version';
      html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:16px;background:#0d1b2a;border:1px solid #1f3a5f;border-radius:6px;font-size:13px">`;
      html += `<span style="opacity:.7">&#x1F4CE; Published at</span>`;
      html += `<a href="${esc(_workspaceDocArtifact.url)}" target="_blank" rel="noopener" style="color:#58a6ff;text-decoration:none;word-break:break-all;flex:1">${esc(label)}</a>`;
      html += `<button onclick="linkWorkspaceDocArtifact('${fn}')" style="background:transparent;color:#8b949e;border:1px solid #30363d;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer" title="Replace">Edit</button>`;
      html += `<button onclick="unlinkWorkspaceDocArtifact(${_workspaceDocArtifact.id})" style="background:transparent;color:#8b949e;border:1px solid #30363d;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer" title="Remove link">&#x2716;</button>`;
      html += `</div>`;
    }

    if (_workspaceDocEditing) {
      html += `<textarea id="workspaceDocEditor" spellcheck="false" style="width:100%;min-height:500px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:15px;line-height:1.6;resize:vertical;outline:none;tab-size:4">${esc(_workspaceDocContent)}</textarea>`;
    } else {
      let rendered = _workspaceDocContent;
      if (filepath.endsWith('.md')) {
        try {
          const renderer = new marked.Renderer();
          renderer.image = function(href, title, text) {
            if (href && !href.startsWith('http') && !href.startsWith('data:') && currentWorkspace) {
              const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
              const resolvedHref = _resolveRelPath(dir, href);
              href = `/api/workspace-asset?path=${encodeURIComponent(_workspaceDocRoot || currentWorkspace.path)}&file=${encodeURIComponent(resolvedHref)}&t=${_lastWorkspaceMtime || Date.now()}`;
            }
            return `<img src="${href}" alt="${text || ''}"${title ? ` title="${title}"` : ''} style="max-width:100%;border-radius:4px;margin:8px 0">`;
          };
          rendered = LabMarkdown.render(_workspaceDocContent, { renderer });
          // Rewrite relative src in iframes/embeds to use workspace-asset API
          rendered = rendered.replace(/<iframe([^>]*) src="([^"]+)"([^>]*)>/g, (match, pre, src, post) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            const newSrc = `/api/workspace-asset?path=${encodeURIComponent(_workspaceDocRoot || currentWorkspace.path)}&file=${encodeURIComponent(resolved)}`;
            return `<iframe${pre} src="${newSrc}"${post} onload="applyIframeDarkMode(this)">`;
          });
          // Also rewrite other relative src (img etc) not already handled
          rendered = rendered.replace(/ src="([^"]+)"/g, (match, src) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            return ` src="/api/workspace-asset?path=${encodeURIComponent(_workspaceDocRoot || currentWorkspace.path)}&file=${encodeURIComponent(resolved)}"`;
          });
        } catch(e) {
          rendered = `<pre>${esc(_workspaceDocContent)}</pre>`;
        }
      } else if (filepath.endsWith('.json')) {
        try {
          const formatted = JSON.stringify(JSON.parse(_workspaceDocContent), null, 2);
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto">${hlLine(formatted, 'json')}</pre>`;
        } catch(e) {
          rendered = `<pre>${esc(_workspaceDocContent)}</pre>`;
        }
      } else {
        const lang = filenameLang(filepath);
        if (lang) {
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto;line-height:1.5">${hlLine(_workspaceDocContent, lang)}</pre>`;
        } else {
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto">${esc(_workspaceDocContent)}</pre>`;
        }
      }
      // Inline highlighting happens after innerHTML via highlightComments()
      // below. A plain string replace on the rendered HTML fails whenever a
      // selection crosses inline tags (e.g. "a **bold** word" renders as
      // `a <strong>bold</strong> word` — no substring match), so we walk
      // live text nodes instead and wrap a Range, which tolerates tags.
      html += `<div id="workspaceDocBody" class="nb-markdown">${rendered}</div>`;
    }
    html += `</div>`;

    // Comments margin (right side). Collapsible; default hidden.
    const marginDisplay = commentsCollapsed ? 'none' : '';
    html += `<div id="commentsMargin" style="width:300px;min-width:300px;padding:12px;border-left:1px solid #21262d;display:${marginDisplay}">`;
    // Header row with title + close button — gives users a clear escape hatch
    // without needing to find the toolbar toggle button.
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #21262d">`;
    html += `<span style="font-size:12px;color:#8b949e;font-weight:500;flex:1">Comments</span>`;
    html += `<button onclick="toggleCommentsPanel(this)" style="background:none;border:none;color:#484f58;font-size:16px;line-height:1;cursor:pointer;padding:0 2px" title="Close comments">&times;</button>`;
    html += `</div>`;
    if (_workspaceComments.length > 0) {
      _workspaceComments.forEach(c => {
        html += `<div class="comment-card" data-comment-id="${c.id}" style="border:1px solid #30363d;border-radius:8px;padding:12px;margin-bottom:10px;background:#161b22;font-size:14px">`;
        if (c.text) html += `<div style="color:#d29922;font-size:12px;margin-bottom:6px;font-style:italic">"${esc(c.text.substring(0, 60))}${c.text.length > 60 ? '...' : ''}"</div>`;
        html += `<div style="color:#e6edf3;line-height:1.5">${esc(c.comment)}</div>`;
        html += `<div style="display:flex;align-items:center;justify-content:space-between;margin-top:8px">`;
        html += `<span style="color:#484f58;font-size:11px">${c.created || ''}</span>`;
        html += `<button onclick="resolveComment(${c.id})" style="background:#21262d;border:1px solid #30363d;color:#8b949e;cursor:pointer;font-size:11px;padding:2px 8px;border-radius:4px" title="Resolve">Resolve</button>`;
        html += `</div></div>`;
      });
    }
    // Inline comment input (hidden by default)
    html += `<div id="commentInputBox" style="display:none;border:1px solid #388bfd;border-radius:8px;padding:12px;background:#161b22">`;
    html += `<div id="commentSelectedText" style="color:#d29922;font-size:12px;margin-bottom:8px;font-style:italic"></div>`;
    html += `<textarea id="commentInput" placeholder="Add a comment..." style="width:100%;min-height:60px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:8px;font-size:14px;line-height:1.5;resize:vertical;outline:none;font-family:inherit"></textarea>`;
    html += `<div style="display:flex;gap:8px;justify-content:flex-end;margin-top:8px">`;
    html += `<button onclick="cancelInlineComment(this)" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Cancel</button>`;
    html += `<button onclick="submitInlineComment('${fn}',this)" style="background:#388bfd;color:#fff;border:1px solid #388bfd;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Comment</button>`;
    html += `</div></div>`;

    html += `</div>`;

    html += `</div>`; // end flex container
    container.innerHTML = html;

    // Apply comment highlights after innerHTML so we can wrap Ranges that
    // span formatting tags (bold/italic/links) — not possible with string
    // replace on the raw HTML.
    if (!_workspaceDocEditing) {
      const docBody = container.querySelector('#workspaceDocBody');
      if (docBody) {
        if (filepath.endsWith('.md')) docBody.querySelectorAll('h2,h3').forEach(heading => {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'markdown-copy-action';
          button.textContent = 'Copy';
          button.title = 'Copy this section, excluding collapsed blocks';
          button.addEventListener('click', () => copySectionByHeading(button));
          heading.appendChild(button);
        });
        _workspaceComments.forEach(c => { if (c.text) highlightCommentInNode(docBody, c.text, c.id); });
        renderMermaidBlocks(docBody);
      }
    }

    if (_workspaceDocEditing) {
      const ta = container.querySelector('#workspaceDocEditor');
      ta.addEventListener('keydown', function(e) {
        if (e.key === 'Tab') {
          e.preventDefault();
          const s = this.selectionStart, end = this.selectionEnd;
          this.value = this.value.substring(0, s) + '    ' + this.value.substring(end);
          this.selectionStart = this.selectionEnd = s + 4;
        }
      });
      ta.focus();
    } else {
      // Right-click on selected text to comment. Wrap the selection in a
      // pending <mark> right away so the user sees what they're commenting
      // on while composing. Cleared on cancel; replaced by the saved mark
      // on submit via re-render.
      const docBody = container.querySelector('#workspaceDocBody');
      if (docBody) {
        docBody.addEventListener('contextmenu', (e) => {
          const sel = window.getSelection();
          const text = sel ? sel.toString().trim() : '';
          if (text.length === 0) return;
          e.preventDefault();
          // Drop any leftover pending mark from a previous abandoned draft.
          removePendingCommentMark();
          try {
            const range = sel.getRangeAt(0);
            const mark = document.createElement('mark');
            mark.setAttribute('data-comment-pending', '1');
            mark.style.cssText = 'background:#5c4b00;color:#e6edf3;border-radius:2px';
            try { range.surroundContents(mark); }
            catch (_) {
              const frag = range.extractContents();
              mark.appendChild(frag);
              range.insertNode(mark);
            }
            _pendingCommentMark = mark;
            sel.removeAllRanges();
          } catch (_) {}
          showInlineCommentBox(text, container);
        });
      }
    }
  }

  // Wrap the first occurrence of `targetText` inside `root` in a <mark>.
  // Operates on text nodes via TreeWalker so the match survives inline
  // formatting tags (bold/italic/links/code).
  //
  // Two key robustness moves:
  //  1. Whitespace is normalized before matching. Selection.toString()
  //     inserts "\n" between block elements (h2/p/li) but DOM textContent
  //     concatenates without separators. Collapsing every whitespace run
  //     to a single space on both sides makes multi-paragraph comments
  //     match the way a human would expect.
  //  2. Text already inside another <mark> is still enumerated, so an
  //     overlapping/substring comment can nest inside a broader one
  //     rather than being silently skipped. Pending marks (still being
  //     composed) are excluded — those aren't saved yet.
  function highlightCommentInNode(root, targetText, commentId) {
    if (!targetText) return false;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement && n.parentElement.closest('mark[data-comment-pending]'))
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
    });
    const chunks = [];
    let total = '';
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      chunks.push({ node: n, start: total.length });
      total += n.data;
    }
    // Build a whitespace-normalized version of `total`, plus a map from
    // each normalized index back to its original index. A whitespace run
    // collapses to one space, which always maps to the first char of the
    // run so setStart/setEnd land on a real text-node boundary.
    const normMap = [];
    let norm = '';
    for (let i = 0; i < total.length; i++) {
      const ch = total[i];
      if (/\s/.test(ch)) {
        if (norm.endsWith(' ')) continue;
        norm += ' ';
        normMap.push(i);
      } else {
        norm += ch;
        normMap.push(i);
      }
    }
    const targetNorm = targetText.replace(/\s+/g, ' ').trim();
    if (!targetNorm) return false;
    const hitNorm = norm.indexOf(targetNorm);
    if (hitNorm < 0) return false;
    const startOrig = normMap[hitNorm];
    const endOrig = normMap[hitNorm + targetNorm.length - 1] + 1;
    const startChunk = chunks.find(c => startOrig >= c.start && startOrig < c.start + c.node.data.length);
    const endChunk = [...chunks].reverse().find(c => endOrig > c.start && endOrig <= c.start + c.node.data.length);
    if (!startChunk || !endChunk) return false;
    const range = document.createRange();
    range.setStart(startChunk.node, startOrig - startChunk.start);
    range.setEnd(endChunk.node, endOrig - endChunk.start);
    const mark = document.createElement('mark');
    mark.setAttribute('data-comment-id', String(commentId));
    mark.style.cssText = 'background:#5c4b00;color:#e6edf3;border-radius:2px;cursor:pointer';
    try {
      range.surroundContents(mark);
    } catch (_) {
      // Range crosses element boundaries — extract the fragment, wrap it,
      // reinsert at the same position.
      const frag = range.extractContents();
      mark.appendChild(frag);
      range.insertNode(mark);
    }
    return true;
  }

  let _pendingCommentText = '';
  let _pendingCommentMark = null;  // <mark data-comment-pending> wrapping the user's current selection

  // Unwrap the pending-comment <mark> if one is open. Called on cancel and
  // before right-click wraps a fresh selection so old drafts don't leak.
  function removePendingCommentMark() {
    if (!_pendingCommentMark) return;
    const mark = _pendingCommentMark;
    _pendingCommentMark = null;
    const parent = mark.parentNode;
    if (!parent) return;
    while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
    parent.removeChild(mark);
    // Collapse any split text nodes the removal just created so subsequent
    // highlightCommentInNode() walks see contiguous text.
    try { parent.normalize(); } catch (_) {}
  }

  function showInlineCommentBox(selectedText, ctr) {
    _pendingCommentText = selectedText;
    const root = ctr || document;
    const q = (id) => root.querySelector('#' + id);
    // Auto-expand the comments panel if it's currently collapsed
    if (localStorage.getItem('workspaceDocCommentsCollapsed') !== '0') {
      localStorage.setItem('workspaceDocCommentsCollapsed', '0');
      const panel = q('commentsMargin');
      const btn = q('commentsToggleBtn');
      if (panel) panel.style.display = '';
      if (btn) {
        btn.title = 'Hide comments';
        btn.style.color = '#388bfd';
        btn.style.borderColor = '#388bfd';
      }
    }
    const box = q('commentInputBox');
    const label = q('commentSelectedText');
    const input = q('commentInput');
    if (!box || !label || !input) return;
    label.textContent = '"' + selectedText.substring(0, 80) + (selectedText.length > 80 ? '...' : '') + '"';
    input.value = '';
    box.style.display = 'block';
    input.focus();
  }

  function cancelInlineComment(el) {
    _pendingCommentText = '';
    removePendingCommentMark();
    const root = (el && el.closest('#content, #docModalBody')) || document;
    const box = root.querySelector('#commentInputBox');
    if (box) box.style.display = 'none';
  }

  async function submitInlineComment(filepath, el) {
    const root = (el && el.closest('#content, #docModalBody')) || document;
    const input = root.querySelector('#commentInput');
    const comment = input.value.trim();
    if (!comment) return;
    if (!currentWorkspace) return;
    try {
      await fetch('/api/workspace-comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _workspaceDocRoot || currentWorkspace.path, file: filepath, text: _pendingCommentText, comment }),
      });
      _pendingCommentText = '';
      _pendingCommentMark = null;  // the upcoming re-render rebuilds the DOM from scratch
      openWorkspaceDoc(filepath);
    } catch (err) { alert('Error: ' + err.message); }
  }

  function startWorkspaceDocEdit() {
    if (!_workspaceDocPath) return;
    openWorkspaceDocModal(_workspaceDocPath, { editing: true, root: _workspaceDocRoot || currentWorkspace.path });
  }

  function cancelWorkspaceDocEdit(filepath) {
    const editCtr = _workspaceDocEditContainer;
    _workspaceDocEditing = false;
    _workspaceDocEditContainer = null;
    if (editCtr) renderWorkspaceDoc(filepath, editCtr);
  }

  async function saveWorkspaceDoc(filepath) {
    const editCtr = _workspaceDocEditContainer;
    const ta = editCtr ? editCtr.querySelector('#workspaceDocEditor') : document.getElementById('workspaceDocEditor');
    if (!ta || !currentWorkspace) return;
    try {
      const res = await fetch('/api/workspace-file', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _workspaceDocRoot || currentWorkspace.path, file: filepath, content: ta.value }),
      });
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Error saving'); return; }
      _workspaceDocContent = ta.value;
      _workspaceDocEditing = false;
      _workspaceDocEditContainer = null;
      // Re-render modal in read mode with saved content, then refresh inline pane.
      if (editCtr) renderWorkspaceDoc(filepath, editCtr);
      const content = document.getElementById('content');
      if (content) _renderDocInto(filepath, content);
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function resolveComment(commentId) {
    if (!currentWorkspace) return;
    try {
      await fetch('/api/workspace-comments', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _workspaceDocRoot || currentWorkspace.path, comment_id: commentId }),
      });
      openWorkspaceDoc(_workspaceDocPath);
    } catch (err) { alert('Error: ' + err.message); }
  }

  let _completeActionId = null;

  function completeAction(actionId) {
    if (!currentWorkspace) return;
    _completeActionId = actionId;
    // Show floating completion box near the clicked item
    let box = document.getElementById('actionCompleteBox');
    if (!box) {
      box = document.createElement('div');
      box.id = 'actionCompleteBox';
      box.style.cssText = 'position:fixed;z-index:500;width:380px;background:var(--bg-secondary);border:1px solid var(--accent);border-radius:10px;padding:16px;box-shadow:0 8px 24px rgba(0,0,0,0.3);';
      box.innerHTML = `
        <div style="font-size:14px;font-weight:600;color:var(--text-primary);margin-bottom:8px">Mark as done</div>
        <div style="font-size:12px;color:var(--text-secondary);margin-bottom:10px">Paste any artifacts (URLs, notes, content). Leave empty if none.</div>
        <textarea id="actionArtifactsInput" placeholder="https://github.com/...\nAPI key configured\nSlack thread: ..." style="width:100%;min-height:80px;background:var(--bg-primary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;padding:8px;font-size:13px;line-height:1.5;resize:vertical;outline:none;font-family:inherit"></textarea>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:10px">
          <button onclick="cancelCompleteAction()" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);padding:5px 14px;border-radius:6px;font-size:12px;cursor:pointer">Cancel</button>
          <button onclick="submitCompleteAction()" style="background:#238636;color:#fff;border:1px solid #238636;padding:5px 14px;border-radius:6px;font-size:12px;cursor:pointer">Done</button>
        </div>`;
      document.body.appendChild(box);
    }
    // Position in center of viewport
    box.style.display = 'block';
    box.style.top = '50%';
    box.style.left = '50%';
    box.style.transform = 'translate(-50%, -50%)';
    const input = document.getElementById('actionArtifactsInput');
    input.value = '';
    input.focus();
  }

  function cancelCompleteAction() {
    _completeActionId = null;
    const box = document.getElementById('actionCompleteBox');
    if (box) box.style.display = 'none';
  }

  async function submitCompleteAction() {
    if (!currentWorkspace || !_completeActionId) return;
    const input = document.getElementById('actionArtifactsInput');
    const artifacts = input.value.split('\n').map(s => s.trim()).filter(Boolean);
    try {
      await fetch('/api/workspace-action-complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentWorkspace.path, action_id: _completeActionId, artifacts }),
      });
      _completeActionId = null;
      document.getElementById('actionCompleteBox').style.display = 'none';
      showWorkspaceInfo();
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function copyForGDocs(e) {
    const root = document.getElementById('workspaceDocBody') || document.getElementById('content');
    return LabMarkdown.copy(root, {button: e && e.target.closest('button')});
  }

  async function copySectionByHeading(button) {
    return LabMarkdown.copy(document.getElementById('workspaceDocBody'), {
      heading: button.closest('h1,h2,h3,h4,h5,h6'), button,
    });
  }

  // Attach (or replace) the online URL for the current doc. Writes into
  // workspace.json.artifacts[]. Same storage the `lab artifact add --file`
  // CLI touches, so either entry point is fine. Detects the artifact type
  // from the URL host for convenience.
  async function linkWorkspaceDocArtifact(filepath) {
    if (!currentWorkspace) return;
    const existing = _workspaceDocArtifact && _workspaceDocArtifact.url ? _workspaceDocArtifact.url : '';
    const url = prompt('Online URL for ' + filepath + ' (Google Doc / Confluence / etc.)', existing);
    if (url === null) return;
    const clean = url.trim();
    if (!clean) return;
    const title = prompt('Title (optional)', (_workspaceDocArtifact && _workspaceDocArtifact.title) || filepath.split('/').pop()) || '';
    const inferredType = (() => {
      if (/docs\.google\.com/.test(clean)) return 'google_doc';
      if (/sheets\.google\.com/.test(clean)) return 'spreadsheet';
      if (/confluence/i.test(clean)) return 'confluence';
      if (/github\.com/.test(clean)) return 'github';
      if (/jira/i.test(clean)) return 'jira';
      if (/slack\.com/.test(clean)) return 'slack';
      return 'url';
    })();
    try {
      const infoRes = await fetch(`/api/workspace-info?path=${encodeURIComponent(currentWorkspace.path)}`);
      const info = await infoRes.json();
      const arts = Array.isArray(info.artifacts) ? [...info.artifacts] : [];
      const existingIdx = arts.findIndex(a => a && a.file === filepath);
      const nextId = 1 + arts.reduce((m, a) => Math.max(m, a.id || 0), 0);
      const entry = {
        id: existingIdx >= 0 ? arts[existingIdx].id : nextId,
        type: inferredType,
        url: clean,
        title: title,
        description: existingIdx >= 0 ? (arts[existingIdx].description || '') : '',
        added: existingIdx >= 0 ? arts[existingIdx].added : new Date().toISOString().slice(0, 10),
        file: filepath,
      };
      if (existingIdx >= 0) arts[existingIdx] = entry;
      else arts.push(entry);
      info.artifacts = arts;
      await fetch(`/api/workspace-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentWorkspace.path, data: info }),
      });
      openWorkspaceDoc(filepath, { preserveScroll: true });
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function unlinkWorkspaceDocArtifact(artifactId) {
    if (!currentWorkspace || !artifactId) return;
    if (!confirm('Remove the online-version link from this doc?')) return;
    try {
      const infoRes = await fetch(`/api/workspace-info?path=${encodeURIComponent(currentWorkspace.path)}`);
      const info = await infoRes.json();
      const arts = Array.isArray(info.artifacts) ? info.artifacts.filter(a => a && a.id !== artifactId) : [];
      info.artifacts = arts;
      await fetch(`/api/workspace-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentWorkspace.path, data: info }),
      });
      openWorkspaceDoc(_workspaceDocPath, { preserveScroll: true });
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function togglePin(filename) {
    if (!currentWorkspace) return;
    try {
      const infoRes = await fetch(`/api/workspace-info?path=${encodeURIComponent(currentWorkspace.path)}`);
      const info = await infoRes.json();
      let pinned = Array.isArray(info.pinned) ? [...info.pinned] : [];
      const idx = pinned.indexOf(filename);
      if (idx >= 0) {
        pinned.splice(idx, 1);
      } else {
        pinned.push(filename);
      }
      info.pinned = pinned;
      await fetch(`/api/workspace-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentWorkspace.path, data: info }),
      });
      showWorkspaceInfo();
    } catch(e) {}
  }

  function showWorkspaceDashboard() {
    if (document.body.classList.contains('assistant-active') && window.AssistantView) {
      window.AssistantView.setSection('overview');
      return;
    }
    _contextSubView = 'overview';
    currentRepo = null;
    currentRepoInWorkspace = null;
    _repoFileRoot = null;
    // Clear the doc path BEFORE rendering tabs — the Overview tab's active
    // state (and the sidebar view suffix) both read it. User explicitly
    // chose Dashboard, so also drop the remembered doc for this workspace.
    if (currentWorkspace) setLastWorkspaceDoc(currentWorkspace.path, null);
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    renderRepoTabs();
    // Restore the workspace's own sidebar preference (a server view may
    // have collapsed it).
    _sidebarApplyForView();
    // Hide diff tabs when on dashboard
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    showWorkspaceInfo();
  }

  function selectWorkspaceRepo(repoPath) {
    _contextSubView = 'repository';
    currentRepoInWorkspace = currentWorkspace.repos.find(r => r.path === repoPath);
    currentRepo = repoPath;
    _repoFileRoot = null;
    // The diff view replaces any open doc/server view — clear the doc path
    // so the server tab un-highlights and the sidebar preference resets.
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    renderRepoTabs();
    _sidebarApplyForView();
    // Show diff tabs when viewing a repo
    document.getElementById('diffTabs').style.display = 'flex';
    document.body.classList.add('has-diff-tabs');
    diffCache = { uncommitted: null, branch: null };
    loadCommitTabs();
    loadDiff();
  }

  // Per-file "recently pending" tracker. The mtime poller refreshes at
  // 1s; a short Python cell can be written → executed → finalized in
  // under that window, which means the running dot would flicker (or
  // miss entirely) without persistence. Once a file is seen pending,
  // we keep showing the dot for at least `_PENDING_GRACE_MS` after the
  // flag clears so even instant cells still surface in the UI.
  const _recentlyPending = new Map();
  const _PENDING_GRACE_MS = 3000;

  // Per-file "last viewed mtime" tracker. Persisted in localStorage so
  // the unseen-results indicator survives reloads. When a notebook is
  // opened (openWorkspaceDoc) we stamp its current mtime; any subsequent
  // mtime advance means there are unseen outputs → amber dot.
  function _nbLastViewedKey(path) {
    return 'nbLastViewed:' + (currentWorkspace ? currentWorkspace.path : '') + '|' + path;
  }
  function _nbGetLastViewed(path) {
    try {
      const v = localStorage.getItem(_nbLastViewedKey(path));
      return v ? parseFloat(v) : 0;
    } catch { return 0; }
  }
  function _nbMarkViewed(path, mtime) {
    try { localStorage.setItem(_nbLastViewedKey(path), String(mtime || Date.now() / 1000)); } catch {}
  }

  // ─── Sidebar git decorations (VS Code Explorer-style) ───────────────────
  // Per-file status from GET /api/git-status?repo=<workspace path> (short-TTL
  // cached server-side). Applied by MUTATING row classes/badges in place —
  // never by rebuilding the tree — so open folders, scroll position, and
  // hover state all survive a repaint.
  const _gitStatusByPath = new Map();  // workspace path -> {files, ignored, ts}
  let _gitStatusInFlight = false;
  const _GIT_STATUS_MIN_MS = 5000;     // client-side floor between fetches
  const _GIT_ROW_CLASSES = ['git-m', 'git-a', 'git-u', 'git-d', 'git-r', 'git-ignored'];
  const _GIT_BADGE_TITLES = {M: 'Modified', A: 'Added', U: 'Untracked', D: 'Deleted', R: 'Renamed'};

  function _gitRowClass(status) {
    return status === 'M' ? 'git-m'
      : status === 'A' ? 'git-a'
      : status === 'U' ? 'git-u'
      : status === 'D' ? 'git-d'
      : status === 'R' ? 'git-r'
      : '';
  }

  function _gitSetRowClass(row, cls) {
    _GIT_ROW_CLASSES.forEach(c => { if (c !== cls) row.classList.remove(c); });
    if (cls) row.classList.add(cls);
  }

  function _sidebarPlaceGitBadge(row, badge) {
    // History is the permanent right-edge action on recent-file rows. Keep
    // the variable-width Git status immediately before it so every GitHub
    // icon lands in the same final column.
    const actions = row.querySelector('.sidebar-actions');
    if (actions) row.insertBefore(badge, actions);
    else row.appendChild(badge);
  }

  function _sidebarApplyGitStatus(entry) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const files = (entry && entry.files) || {};
    const ignored = (entry && entry.ignored) || [];
    const keys = Object.keys(files);
    const isIgnored = p => ignored.some(pre => {
      const base = pre.replace(/\/+$/, '');
      return base && (p === base || p.startsWith(base + '/'));
    });
    // Untracked directories come back as ONE entry ("newdir": "U") with no
    // per-file children — decorations inherit down to everything under it.
    const statusFor = p => {
      if (files[p]) return files[p];
      for (const k of keys) {
        if ((files[k] === 'U' || files[k] === 'A') && p.startsWith(k + '/')) return files[k];
      }
      return '';
    };

    sidebar.querySelectorAll('.sidebar-file[data-filepath]').forEach(row => {
      const p = row.getAttribute('data-filepath');
      if (!p || p.startsWith('__proxy__/')) return;
      const st = statusFor(p);
      const cls = st ? _gitRowClass(st) : (isIgnored(p) ? 'git-ignored' : '');
      _gitSetRowClass(row, cls);
      const want = st && cls && cls !== 'git-ignored' ? st : '';
      let badge = row.querySelector('.git-badge');
      if (want) {
        if (!badge) {
          badge = document.createElement('span');
          badge.className = 'git-badge';
        }
        _sidebarPlaceGitBadge(row, badge);
        if (badge.textContent !== want) badge.textContent = want;
        badge.title = _GIT_BADGE_TITLES[want] || want;
      } else if (badge) {
        badge.remove();
      }
    });

    // Folders: tint like VS Code — gold when anything under them is
    // modified/deleted/renamed, green when only added/untracked, dim when
    // gitignored — plus a right-edge dot badge. Workspace-scoped folders only
    // (the shared `.claude/`, `.agents/`, `code/` meta trees live outside
    // the workspace and keep their plain styling).
    sidebar.querySelectorAll('.sidebar-folder[data-tree-scope^="workspace:"]').forEach(row => {
      const p = row.getAttribute('data-tree-path') || '';
      let cls = '';
      if (p && statusFor(p)) {
        cls = _gitRowClass(statusFor(p));
      } else if (p && isIgnored(p)) {
        cls = 'git-ignored';
      } else if (p) {
        let worst = '';
        for (const k of keys) {
          if (k.startsWith(p + '/')) {
            const s = files[k];
            if (s === 'M' || s === 'D' || s === 'R') { worst = 'M'; break; }
            worst = 'U';
          }
        }
        cls = worst === 'M' ? 'git-m' : worst === 'U' ? 'git-u' : '';
      }
      _gitSetRowClass(row, cls);
      const wantDot = !!cls && cls !== 'git-ignored';
      let dot = row.querySelector('.git-dot');
      if (wantDot && !dot) {
        dot = document.createElement('span');
        dot.className = 'git-dot';
        dot.title = 'Contains changes';
        row.appendChild(dot);
      } else if (!wantDot && dot) {
        dot.remove();
      }
    });
  }

  // Repaints synchronously from cache (a sidebar rebuild wipes the DOM
  // classes), then refreshes from the server unless the cache is fresh.
  async function _sidebarGitStatusRefresh() {
    if (!currentWorkspace || !currentWorkspace.is_workspace || !currentWorkspace.path) return;
    const basePath = currentWorkspace.path;
    const path = _sidebarScopedRoot(basePath);
    const cached = _gitStatusByPath.get(path);
    if (cached) _sidebarApplyGitStatus(cached);
    if (cached && (Date.now() - cached.ts) < _GIT_STATUS_MIN_MS) return;
    if (_gitStatusInFlight) return;
    _gitStatusInFlight = true;
    try {
      const r = await fetch(`/api/git-status?repo=${encodeURIComponent(path)}`);
      if (!r.ok) return;
      const data = await r.json();
      const entry = {files: data.files || {}, ignored: data.ignored || [], ts: Date.now()};
      _gitStatusByPath.set(path, entry);
      if (currentWorkspace && currentWorkspace.path === basePath && _sidebarScopedRoot(basePath) === path) {
        _sidebarApplyGitStatus(entry);
      }
    } catch (e) {
      // Network hiccup — decorations just go stale until the next tick.
    } finally {
      _gitStatusInFlight = false;
    }
  }

  // Re-renders just the workspace file sidebar from scratch. Pulled out
  // of showWorkspaceInfo so the mtime poller can call it independently
  // when a doc is open (otherwise newly added files don't appear in the
  // sidebar until the user navigates away and back).
  async function _refreshWorkspaceSidebar({preserveScroll = false, _data = null} = {}) {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const prevSidebarScroll = preserveScroll ? sidebar.scrollTop : 0;
    const workspacePath = currentWorkspace.path;
    const isAssistant = document.body.classList.contains('assistant-active');
    await _sidebarEnsureWorktrees(workspacePath);
    const fileRoot = _sidebarScopedRoot(workspacePath);
    if (_data && _data.fileRoot !== fileRoot) _data = null;

    // Warm switch: when no `_data` override is passed but the cache has
    // a payload for this workspace, paint instantly from the cache and
    // then reconcile against the server in the background. The
    // recursive call with `_data` set skips the fetches entirely so
    // the second paint only re-runs the render body (no network).
    if (!_data) {
      const cachedPayload = _workspaceSidebarCache.get(workspacePath);
      if (cachedPayload && cachedPayload.fileRoot !== fileRoot) _workspaceSidebarCache.delete(workspacePath);
      if (cachedPayload && cachedPayload.fileRoot === fileRoot) {
        // Synchronous warm paint — recursive call returns a Promise but
        // because `_data` short-circuits both fetches, all the render
        // work happens in the synchronous prefix.
        _refreshWorkspaceSidebar({preserveScroll, _data: cachedPayload});
        // Background reconcile.
        Promise.resolve().then(async () => {
          try {
            const files = await _sidebarFetchWorkspaceFiles(fileRoot);
            const recentFiles = await _sidebarResolveRecentFiles(files, fileRoot);
            let pinned = [], references = [], proxies = [];
            try {
              const infoRes = await fetch(`/api/workspace-info?path=${encodeURIComponent(workspacePath)}`);
              if (infoRes.ok) {
                const info = await infoRes.json();
                if (Array.isArray(info.pinned)) pinned = info.pinned;
                if (Array.isArray(info.references)) references = info.references;
                if (Array.isArray(info.proxies)) proxies = info.proxies;
              }
            } catch {}
            const fresh = {files, recentFiles, pinned, references, proxies, fileRoot};
            if (!currentWorkspace || currentWorkspace.path !== workspacePath
                || _sidebarScopedRoot(workspacePath) !== fileRoot) return;
            const prev = _workspaceSidebarCache.get(workspacePath);
            _workspaceSidebarCache.set(workspacePath, fresh);
            // Re-render only if (a) the data actually changed and (b)
            // the user is still on this workspace.
            if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
            _refreshWorkspaceSidebar({preserveScroll: true, _data: fresh});
          } catch (e) {
            console.error('[_refreshWorkspaceSidebar] reconcile failed:', e && e.stack || e);
          }
        });
        return;
      }
    }

    try {
      let files, recentFiles, pinnedNames, references, proxies;
      if (_data) {
        // Render from pre-loaded payload — cache hit or reconcile path.
        files = _data.files;
        pinnedNames = _data.pinned || [];
        references = _data.references || [];
        proxies = _data.proxies || [];
        recentFiles = Array.isArray(_data.recentFiles)
          ? _data.recentFiles
          : (_sidebarCurrentRecentMode() === 'mtime' ? _sidebarRecentFiles(files) : []);
      } else {
        // Cold path: fetch fresh + write to cache.
        files = await _sidebarFetchWorkspaceFiles(fileRoot);
        recentFiles = await _sidebarResolveRecentFiles(files, fileRoot);
        pinnedNames = [];
        references = [];
        proxies = [];
        try {
          const infoRes = await fetch(`/api/workspace-info?path=${encodeURIComponent(currentWorkspace.path)}`);
          if (infoRes.ok) {
            const info = await infoRes.json();
            if (Array.isArray(info.pinned)) pinnedNames = info.pinned;
            if (Array.isArray(info.references)) references = info.references;
            if (Array.isArray(info.proxies)) proxies = info.proxies;
          }
        } catch(e) {}
        _workspaceSidebarCache.set(workspacePath, {files, recentFiles, pinned: pinnedNames, references, proxies, fileRoot});
      }
      _rememberNotebookFolders(fileRoot, files);
      const fileEntries = (files || []).filter(f => f && f.type !== 'dir');
      const dirEntries = (files || []).filter(f => f && f.type === 'dir');
      const pinnedSet = new Set(pinnedNames);
      const filesByName = new Map(fileEntries.map(f => [f.name, f]));
      const worktreeSelected = fileRoot !== workspacePath;
      const pinnedFiles = worktreeSelected ? [] : pinnedNames.filter(n => fileEntries.some(f => f.name === n));
      // Pinned rows are shortcuts, not a move operation. Keep every pinned
      // file in the normal folder tree as well so its original context never
      // disappears when the shortcut is created.
      const otherFiles = fileEntries;
      _sidebarRememberAvailableExtensions(fileEntries);
      _sidebarMaybeLogRecentDiagnostics(fileEntries, fileRoot);

      // Only agent instruction documents belong in Meta. Workspace settings
      // and local skills stay in Files, rooted at the selected folder/worktree.
      const META_FILES = new Set(['AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md']);
      // Folders that should open automatically — docs is where 95% of the
      // reading lives, so showing it collapsed by default hides everything.
      const AUTO_OPEN_FOLDERS = new Set(['docs', 'notebooks', 'links']);

      const metaFiles = otherFiles.filter(f => META_FILES.has(f.path));
      const mainFiles = otherFiles.filter(f => !META_FILES.has(f.path));

      // Active-file highlighting is baked into the rendered HTML (data-filepath
      // + .active class) so periodic sidebar rebuilds — from the mtime poller
      // and the index-updated WS event — preserve the red selection bar
      // instead of dropping it and waiting for openWorkspaceDoc to re-add it,
      // which made the selection blink.
      const activePath = _workspaceDocRoot === fileRoot ? (_workspaceDocPath || null) : null;
      const dashActive = !activePath && (!isAssistant || (window.AssistantView && window.AssistantView.section() === 'overview')) ? ' active' : '';
      const dashboardLabel = isAssistant ? 'Overview' : 'Dashboard';
      let sbHtml = `<div class="sidebar-overview-row"><a class="sidebar-file${dashActive}" data-dashboard="1" onclick="showWorkspaceDashboard()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">&#x1F4CB; ${dashboardLabel}</span></a>${_sidebarFileConfigCogHtml()}</div>`;
      sbHtml += _sidebarRecentSelectorsHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(workspacePath);
      sbHtml += _sidebarWorktreePickerHtml(workspacePath);
      sbHtml += symlinkLegendHtml();
      if (pinnedFiles.length) sbHtml += `<div class="sidebar-title">Pinned <span class="sidebar-title-count">${pinnedFiles.length}</span></div>`;
      pinnedFiles.forEach(name => {
        const f = filesByName.get(name) || {name, path: name};
        const safeName = name.replace(/'/g, "\\'");
        const label = name.replace(/\.md$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const activeCls = activePath === name ? ' active' : '';
        sbHtml += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(name)}" data-entry-kind="file" data-entry-path="${escAttr(name)}"${symlinkTitle(f)} onclick="openWorkspaceDoc('${safeName}')" ondblclick="event.stopPropagation();openWorkspaceDocModal('${safeName}')" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">${symlinkMarker(f)}&#x1F4CC; ${label}</span><span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${safeName}')" title="Unpin">&#x2716;</button></span></a>`;
      });
      // Servers — proxied local dev servers declared in servers.json (or
      // legacy workspace.json proxies). Each entry opens
      // an inline iframe through /api/proxy/<id>/<name>/<path>, with the
      // terminal panel still visible alongside so the user can iterate
      // (start/stop the server, tail logs, etc.) without leaving the
      // tab. Double-click pops the same URL out into a new browser tab.
      if (Array.isArray(proxies) && proxies.length > 0) {
        sbHtml += '<div class="sidebar-title">Servers</div>';
        proxies.forEach(p => {
          if (!p || !p.name) return;
          const name = String(p.name);
          const safeName = name.replace(/'/g, "\\'");
          const port = p.port || '';
          const host = p.host || 'localhost';
          const label = p.label || name;
          const proxyPath = '__proxy__/' + name;
          const activeCls = activePath === proxyPath ? ' active' : '';
          const title = `${host}:${port}${p.path || '/'} — click to open inline · dbl-click to pop out`;
          sbHtml += `<a class="sidebar-file${activeCls}" data-filepath="${esc(proxyPath)}" onclick="openWorkspaceProxy('${safeName}')" ondblclick="event.stopPropagation();openWorkspaceProxyTab('${safeName}')" title="${esc(title)}"><span class="sidebar-fname">&#x1F310; ${esc(label)}<span style="color:var(--text-dim);font-size:10px;margin-left:6px">:${esc(String(port))}</span></span></a>`;
        });
      }
      // Tree scope key for the persistent folder-open state. Declared
      // OUTSIDE the `mainFiles.length > 0` block because the
      // external-references and shared `.claude/` blocks below also call
      // `_treeIsOpen(_workspaceTreeScope, …)`. A workspace with no mainFiles but
      // some references (or just the shared CLAUDE.md row) would otherwise
      // hit `ReferenceError: _workspaceTreeScope is not defined` and blow out
      // the whole sidebar via the catch handler.
      const _workspaceTreeScope = 'workspace:' + (currentWorkspace && currentWorkspace.name ? currentWorkspace.name : '') + ':' + fileRoot;
      sbHtml += _sidebarWorktreeScopeStartHtml(workspacePath);
      sbHtml += _sidebarRecentSectionHtml(recentFiles, activePath, fileRoot, {resolved: true});
      sbHtml += _sidebarFilesTitle(fileRoot);
      if (mainFiles.length > 0 || dirEntries.length > 0) {
        const tree = buildSidebarTree([...dirEntries, ...mainFiles]);
        function renderTree(node, depth, parentPath) {
          let html = '';
          // Render folders first
          const folders = treeFolderNames(node, _sidebarCurrentSortMode('files'));
          folders.forEach(folder => {
            const fid = 'folder-' + Math.random().toString(36).substr(2, 6);
            const fullPath = parentPath ? `${parentPath}/${folder}` : folder;
            const d = treeFolderEntry(node, folder, fullPath);
            const autoOpen = depth === 0 && AUTO_OPEN_FOLDERS.has(folder);
            const open = _treeIsOpen(_workspaceTreeScope, fullPath, autoOpen);
            const arrowCls = open ? ' open' : '';
            const childrenCls = open ? ' open' : '';
            html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(_workspaceTreeScope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}" data-entry-kind="folder" data-entry-path="${escAttr(fullPath)}" data-entry-root="${escAttr(fileRoot)}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">\u25B6</span>${symlinkMarker(d)}${esc(folder)}/</div>`;
            html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
            html += renderTree(node[folder], depth + 1, fullPath);
            html += '</div>';
          });
          // Then files
          treeFiles(node, _sidebarCurrentSortMode('files')).forEach(f => {
            const safePath = f.path.replace(/'/g, "\\'");
            const safeRoot = fileRoot.replace(/'/g, "\\'");
            const fname = f.path.split('/').pop();
            const icon = fileIconHtml(fname, f);
            // Notebook activity indicators — running (green pulse) and
            // unseen-results (amber static). Running wins if both apply
            // since "actively running" is the more urgent state.
            //
            // RUNNING: backend reports `pending: true`. We OR it with a
            // grace window so a fast Python cell can finish between two
            // polls and the user still sees the indicator briefly.
            if (f.pending) _recentlyPending.set(f.path, Date.now());
            const recent = _recentlyPending.get(f.path);
            const stillFresh = recent && (Date.now() - recent) < _PENDING_GRACE_MS;
            const isRunning = f.pending || stillFresh;
            if (recent && !isRunning) _recentlyPending.delete(f.path);
            //
            // UNSEEN: compare current file mtime to per-file last-viewed
            // timestamp in localStorage. If the file changed since the
            // last time the user opened it, show an amber dot.
            const lastViewed = (fname.endsWith('.ipynb') && f.mtime) ? _nbGetLastViewed(f.path) : 0;
            const hasUnseen = !isRunning && f.mtime && lastViewed && f.mtime > lastViewed + 0.5;
            let dotHtml = '';
            if (isRunning) {
              const dotTitle = f.pending ? 'A cell is currently running' : 'Cell just finished';
              dotHtml = `<span class="nb-running-dot" title="${dotTitle}"></span>`;
            } else if (hasUnseen) {
              dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openWorkspaceDocAndJumpToUnseen('${safePath}','${safeRoot}')"></span>`;
            }
            const activeCls = activePath === f.path ? ' active' : '';
            const isPinned = pinnedSet.has(f.name);
            const pinHtml = worktreeSelected ? '' : `<span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${f.name.replace(/'/g, "\\'")}')" title="${isPinned ? 'Unpin' : 'Pin to top'}">${isPinned ? '&#x2716;' : '&#x1F4CC;'}</button></span>`;
            html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}" data-entry-kind="file" data-entry-path="${escAttr(f.path)}" data-entry-root="${escAttr(fileRoot)}"${symlinkTitle(f)} onclick="openWorkspaceDocFromFileClick('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openWorkspaceDocModal('${safePath}',{root:'${safeRoot}'})"><span class="sidebar-fname">${dotHtml}${icon}${fname}</span>${pinHtml}</a>`;
          });
          return html;
        }
        sbHtml += renderTree(tree, 0, '');
      }
      sbHtml += _sidebarWorktreeScopeEndHtml(workspacePath);

      // Virtual ``external-references/`` folder — URLs from
      // workspace.json.references[]. They open in a new tab (not in the
      // doc pane) since they're real external links. The folder is
      // auto-expanded like docs/ so curated reading lives in plain sight.
      if (references.length > 0) {
        const extId = 'folder-ext-' + Math.random().toString(36).substr(2, 6);
        const _extOpen = _treeIsOpen(_workspaceTreeScope, 'external-references', true);
        const _extArrow = _extOpen ? ' open' : '';
        const _extChildren = _extOpen ? ' open' : '';
        sbHtml += `<div class="sidebar-folder" data-tree-scope="${escAttr(_workspaceTreeScope)}" data-tree-path="external-references" data-tree-target="${extId}" onclick="_treeToggleFolder(this)"><span class="folder-arrow${_extArrow}">▶</span>external-references/</div>`;
        sbHtml += `<div class="sidebar-folder-children${_extChildren}" id="${extId}">`;
        references.forEach(r => {
          const safeUrl = (r.url || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
          const title = r.title || r.url || '(untitled)';
          const safeTitle = String(title).replace(/</g, '&lt;').replace(/>/g, '&gt;');
          sbHtml += `<a class="sidebar-file" href="${safeUrl}" target="_blank" rel="noopener" title="${safeTitle}&#10;${r.url || ''}"><span class="sidebar-fname">\u{1F517} ${safeTitle}</span></a>`;
        });
        sbHtml += '</div>';
      }

      sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
      if (!isAssistant) sbHtml += _agentContextMetaHtml();
      metaFiles.forEach(f => {
        const action = `openWorkspaceDoc(${JSON.stringify(f.path)}, {root:${JSON.stringify(fileRoot)}})`;
        const modalAction = `event.stopPropagation();openWorkspaceDocModal(${JSON.stringify(f.path)}, {root:${JSON.stringify(fileRoot)}})`;
        const activeCls = activePath === f.path ? ' active' : '';
        sbHtml += `<a class="sidebar-file sidebar-file-meta${activeCls}${symlinkClass(f)}" data-filepath="${escAttr(f.path)}" data-entry-kind="file" data-entry-root="${escAttr(fileRoot)}" data-entry-path="${escAttr(f.path)}"${symlinkTitle(f)} onclick="${escAttr(action)}" ondblclick="${escAttr(modalAction)}"><span class="sidebar-fname">${fileIconHtml(f.name, f)}${esc(f.path)}</span></a>`;
      });
      sidebar.innerHTML = sbHtml;
      if (preserveScroll) sidebar.scrollTop = prevSidebarScroll;
      // Server tabs on the top bar are derived from the same proxies list
      // rendered above — re-sync so they appear/update as soon as the list
      // is known (cold load fetch or background reconcile).
      renderRepoTabs();
      // Git decorations: the rebuild wiped the row classes — repaint from
      // cache synchronously, then fetch fresh in the background if stale.
      _sidebarGitStatusRefresh();
    } catch(e) {
      // Surface the underlying failure so it lands in the browser console
      // AND the server-side client-errors log (window.onerror -> /api/log).
      // Without this the catch silently degrades the sidebar to a bare
      // "Workspace" title and we lose the actual reason every time.
      console.error('[_refreshWorkspaceSidebar] failed:', e && e.stack || e);
      // Only wipe the sidebar if it's empty — otherwise we'd nuke the
      // previously-rendered file tree the user is still looking at, which
      // is strictly worse than leaving the old list visible while we log
      // the underlying error.
      if (!sidebar.children.length) {
        sidebar.innerHTML = '<div class="sidebar-title">Workspace</div>';
      }
    }
  }

  function paintWorkspaceShell() {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    const content = document.getElementById('content');
    if (!content) return;
    const repos = Array.isArray(currentWorkspace.repos) ? currentWorkspace.repos : [];
    const desc = currentWorkspace.description || 'Workspace dashboard';
    content.innerHTML = `
      <div style="padding:24px;max-width:900px">
        <div style="margin-bottom:28px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <h1 style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(_workspaceDisplayName(currentWorkspace))}</h1>
            ${currentWorkspace.status ? `<span style="color:var(--accent);font-size:13px;font-weight:600;background:rgba(88,166,255,.12);padding:2px 10px;border-radius:12px">${esc(currentWorkspace.status)}</span>` : ''}
          </div>
          <p style="color:var(--text-secondary);font-size:16px;line-height:1.6;margin:0">${esc(desc)}</p>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">
          <div style="border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--bg-secondary)">
            <h3 style="color:var(--text-primary);margin-bottom:12px;font-size:16px">Action Items</h3>
            <p style="color:var(--text-dim);font-size:13px;margin:0">Loading details...</p>
          </div>
          <div style="border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--bg-secondary)">
            <h3 style="color:var(--text-primary);margin-bottom:12px;font-size:14px">Repositories <span style="color:var(--text-dim);font-weight:400">${repos.length}</span></h3>
            ${repos.length
              ? repos.map(r => `<div style="padding:6px 8px;margin-bottom:4px;border:1px solid var(--border);border-radius:6px;font-size:13px"><div style="color:var(--accent);font-family:monospace">${esc(r.name || '')}</div><div style="color:var(--text-dim);font-size:11px">${esc(r.branch || '')}</div></div>`).join('')
              : '<p style="color:var(--text-dim);font-size:13px;font-style:italic;margin:0">No repos yet</p>'}
          </div>
        </div>
      </div>`;
  }

  function _setWorkspaceDisplayName(workspacePath, displayName) {
    const update = workspace => {
      if (workspace && workspace.path === workspacePath) workspace.display_name = displayName;
    };
    (workspacesList || []).forEach(update);
    (workspaceTabsAll || []).forEach(update);
    (vaultCatalog || []).forEach(vault => {
      (vault.workspace_rows || []).forEach(update);
    });
    update(currentWorkspace);
  }

  async function workspaceSaveDisplayName(event) {
    if (event) event.preventDefault();
    if (!currentWorkspace || !currentWorkspace.is_workspace) return false;
    const input = document.getElementById('workspaceDisplayName');
    const status = document.getElementById('workspaceDisplayNameStatus');
    const workspaceId = currentWorkspace.name;
    const workspacePath = currentWorkspace.path;
    const vaultId = _workspaceVaultId(currentWorkspace);
    const displayName = String(input && input.value || '').trim() || workspaceId;
    if (status) status.textContent = 'Saving…';
    try {
      const suffix = vaultId ? '?vault=' + encodeURIComponent(vaultId) : '';
      const r = await fetch('/api/workspaces/' + encodeURIComponent(workspaceId) + '/field' + suffix, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field: 'name', value: displayName}),
      });
      const updated = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(updated.detail || 'Could not save the workspace name');
      const savedName = String(updated.name || workspaceId);
      _setWorkspaceDisplayName(workspacePath, savedName);
      if (input) input.value = savedName;
      if (currentWorkspace && currentWorkspace.path === workspacePath) {
        const heading = document.querySelector('[data-workspace-display-title]');
        if (heading) heading.textContent = savedName;
        document.title = savedName;
      }
      workspaceTabsRender();
      if (status) status.textContent = 'Saved';
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.workspaceSaveDisplayName = workspaceSaveDisplayName;

  async function showWorkspaceInfo({preserveScroll = false, keepShell = false} = {}) {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    const workspacePath = currentWorkspace.path;
    const content = document.getElementById('content');
    const prevContentScroll = preserveScroll ? content.scrollTop : 0;
    if (!preserveScroll && !keepShell) content.innerHTML = '<div class="loading">Loading workspace dashboard...</div>';
    await _refreshWorkspaceSidebar({preserveScroll});

    try {
      const [infoRes, actionsRes, onepagerRes, artifactsRes, alertsRes] = await Promise.all([
        fetch(`/api/workspace-info?path=${encodeURIComponent(workspacePath)}`),
        fetch(`/api/workspace-actions?path=${encodeURIComponent(workspacePath)}`),
        fetch(`/api/workspace-onepager?path=${encodeURIComponent(workspacePath)}`),
        fetch(`/api/workspace-artifacts?path=${encodeURIComponent(workspacePath)}`),
        fetch(`/api/workspace-alerts?path=${encodeURIComponent(workspacePath)}`),
      ]);

      const info = await infoRes.json();
      const actions = await actionsRes.json();
      const onepager = await onepagerRes.json();
      const artifacts = await artifactsRes.json();
      const alerts = await alertsRes.json();
      if (!currentWorkspace || currentWorkspace.path !== workspacePath) return;

      // workspace-info is the authoritative workspace.json read. Reconcile its
      // display name into every tab cache so a stale catalog response cannot
      // leave the active tab showing the folder id after Overview has updated.
      const workspaceDisplayName = String(info.name || info.id || currentWorkspace.name);
      _setWorkspaceDisplayName(workspacePath, workspaceDisplayName);
      document.title = workspaceDisplayName;
      workspaceTabsRender();

      // Status color
      const statusColor = info.status === 'active' ? '#3fb950' : info.status === 'paused' ? '#d29922' : '#8b949e';

      let html = '<div style="padding:24px;max-width:900px">';

      // Header with prominent TLDR.
      html += `<div style="margin-bottom:28px">`;
      html += `<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">`;
      html += `<h1 data-workspace-display-title style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(info.name || info.id)}</h1>`;
      html += `<span style="color:${statusColor};font-size:13px;font-weight:600;background:${statusColor}18;padding:2px 10px;border-radius:12px">${info.status}</span>`;
      html += `<button onclick="copyForGDocs(event)" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">&#x1F4CB; Copy</button>`;
      html += `</div>`;
      if (info.description) {
        html += `<p style="color:var(--text-primary);font-size:20px;line-height:1.7;margin-bottom:16px">${esc(info.description)}</p>`;
      }
      html += `<div style="display:flex;gap:16px;font-size:13px;color:var(--text-dim)">`;
      html += `<span>Created: ${info.created}</span>`;
      html += `<span>Updated: ${info.updated}</span>`;
      html += `</div></div>`;

      // The visible name is independent from the stable folder/workspace id.
      // Saving goes through `lab workspace set`, never a direct workspace.json write.
      html += `<form onsubmit="return workspaceSaveDisplayName(event)" style="display:flex;align-items:end;gap:10px;flex-wrap:wrap;border:1px solid var(--border);border-radius:8px;padding:12px 14px;background:var(--bg-secondary);margin:-12px 0 24px">`;
      html += `<label style="display:flex;flex-direction:column;gap:4px;color:var(--text-secondary);font-size:11px;min-width:220px;flex:1">Name shown in tabs<input id="workspaceDisplayName" type="text" value="${escAttr(info.name || info.id)}" maxlength="80" placeholder="${escAttr(info.id)}" style="background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:6px 8px"></label>`;
      html += `<button type="submit" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:6px 10px;cursor:pointer">Save name</button>`;
      html += `<span id="workspaceDisplayNameStatus" style="color:var(--text-dim);font-size:11px;min-width:42px"></span>`;
      html += `<span style="width:100%;color:var(--text-dim);font-size:11px">Folder / workspace id stays <code>${esc(info.id)}</code>.</span>`;
      html += `</form>`;

      // Alerts banner
      const unresolvedAlerts = alerts.filter(a => a.status !== 'resolved');
      if (unresolvedAlerts.length > 0) {
        const priorityOrder = {critical: 0, high: 1, medium: 2};
        unresolvedAlerts.sort((a, b) => (priorityOrder[a.priority] || 9) - (priorityOrder[b.priority] || 9));
        const borderColor = unresolvedAlerts.some(a => a.priority === 'critical') ? '#f85149' : '#d29922';
        html += `<div style="border:2px solid ${borderColor};border-radius:8px;padding:16px;background:${borderColor}0d;margin-bottom:24px">`;
        html += `<h3 style="color:${borderColor};margin-bottom:10px;font-size:14px">&#x26A0; Needs Attention <span style="font-weight:400;color:var(--text-dim)">${unresolvedAlerts.length}</span></h3>`;
        unresolvedAlerts.forEach(a => {
          const pColor = a.priority === 'critical' ? '#f85149' : a.priority === 'high' ? '#d29922' : '#8b949e';
          const sourceLabel = a.source === 'intake' ? 'from intake' : a.source === 'local' ? 'from local resources' : 'from research';
          html += `<div style="padding:6px 0;font-size:13px;border-bottom:1px solid ${borderColor}20">`;
          html += `<div style="display:flex;align-items:start;gap:8px">`;
          html += `<span style="color:${pColor};font-size:11px;font-weight:600;background:${pColor}18;padding:1px 6px;border-radius:3px;flex-shrink:0">${esc(a.priority)}</span>`;
          html += `<div style="flex:1">`;
          html += `<span style="color:var(--text-primary);font-family:monospace">${esc(a.table || a.subject || '')}</span>`;
          html += `<span style="color:var(--text-dim);font-size:11px;margin-left:8px">${sourceLabel}</span>`;
          html += `<div style="color:var(--text-secondary);font-size:12px;margin-top:2px">${esc(a.message || a.error || '')}</div>`;
          html += `</div></div></div>`;
        });
        html += `</div>`;
      }

      // Two-column layout: actions + MPs
      html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:24px">`;

      // Actions column
      html += `<div style="border:1px solid #30363d;border-radius:8px;padding:16px;background:#161b22">`;
      html += `<h3 style="color:#e6edf3;margin-bottom:12px;font-size:16px">`;
      if (actions.length > 0) {
        const done = actions.filter(a => a.status === 'done').length;
        html += `Action Items <span style="color:#484f58;font-weight:400">${done}/${actions.length}</span>`;
      } else {
        html += `Action Items`;
      }
      html += `</h3>`;
      if (actions.length > 0) {
        actions.forEach(a => {
          const isDone = a.status === 'done';
          const icon = isDone ? '&#x2714;' : a.status === 'in_progress' ? '&#x25B6;' : '&#x25CB;';
          const color = isDone ? '#3fb950' : a.status === 'in_progress' ? '#d29922' : '#484f58';
          const textStyle = isDone ? 'text-decoration:line-through;color:#484f58' : 'color:#e6edf3';

          html += `<div style="padding:6px 0;font-size:13px;border-bottom:1px solid #21262d">`;
          html += `<div style="display:flex;align-items:start;gap:6px">`;
          // Clickable icon to toggle done
          if (!isDone) {
            html += `<span style="color:${color};cursor:pointer;flex-shrink:0" onclick="completeAction(${a.id})" title="Mark done">${icon}</span>`;
          } else {
            html += `<span style="color:${color};flex-shrink:0">${icon}</span>`;
          }
          html += `<span style="${textStyle};flex:1">${esc(a.text)}</span>`;
          html += `</div>`;
          if (a.blocker) html += `<div style="color:#d29922;font-size:11px;margin-left:20px;margin-top:2px">&#x26A0; ${esc(a.blocker)}</div>`;
          // Show artifacts if any
          if (a.artifacts && a.artifacts.length > 0) {
            html += `<div style="margin-left:20px;margin-top:4px">`;
            a.artifacts.forEach(art => {
              if (art.match(/^https?:\/\//)) {
                html += `<div style="font-size:11px"><a href="${esc(art)}" target="_blank" style="color:#58a6ff;text-decoration:none">&#x1F517; ${esc(art)}</a></div>`;
              } else {
                html += `<div style="font-size:11px;color:#8b949e;background:#21262d;padding:2px 6px;border-radius:3px;margin-top:2px;white-space:pre-wrap">${esc(art)}</div>`;
              }
            });
            html += `</div>`;
          }
          html += `</div>`;
        });
      } else {
        html += `<p style="color:#484f58;font-size:13px;font-style:italic">No action items yet</p>`;
      }
      html += `</div>`;

      // MPs column
      html += `<div style="border:1px solid #30363d;border-radius:8px;padding:16px;background:#161b22">`;
      html += `<h3 style="color:#e6edf3;margin-bottom:12px;font-size:14px">Repositories <span style="color:#484f58;font-weight:400">${currentWorkspace.repos.length}</span></h3>`;
      currentWorkspace.repos.forEach(r => {
        html += `<div style="padding:6px 8px;margin-bottom:4px;border:1px solid #30363d;border-radius:6px;cursor:pointer;font-size:13px" onmouseover="this.style.background='#21262d'" onmouseout="this.style.background=''" onclick="selectWorkspaceRepo('${r.path}')">`;
        html += `<div style="color:#58a6ff;font-family:monospace">${esc(r.name)}</div>`;
        html += `<div style="color:#484f58;font-size:11px">${esc(r.branch)}</div>`;
        html += `</div>`;
      });
      if (currentWorkspace.repos.length === 0) {
        html += `<p style="color:#484f58;font-size:13px;font-style:italic">No repos yet</p>`;
      }
      html += `</div>`;

      html += `</div>`; // end grid

      // PRs section
      if (info.prs && info.prs.length > 0) {
        html += `<div style="border:1px solid #30363d;border-radius:8px;padding:16px;background:#161b22;margin-bottom:24px">`;
        html += `<h3 style="color:#e6edf3;margin-bottom:12px;font-size:14px">Pull Requests</h3>`;
        info.prs.forEach(pr => {
          const icon = pr.status === 'merged' ? '\u{1F7E3}' : pr.status === 'open' ? '\u{1F535}' : '\u{1F534}';
          const statusStyle = pr.status === 'merged' ? 'color:#a371f7' : pr.status === 'open' ? 'color:#58a6ff' : 'color:#f85149';
          html += `<div style="padding:4px 0;font-size:13px">${icon} <span style="color:#e6edf3">${esc(pr.title)}</span> <span style="color:#484f58">(${esc(pr.mp)})</span> <span style="${statusStyle};font-size:11px">${pr.status}</span>`;
          if (pr.url) html += ` <a href="${esc(pr.url)}" target="_blank" style="color:#484f58;text-decoration:none;font-size:11px">&#x2197;</a>`;
          html += `</div>`;
        });
        html += `</div>`;
      }

      // Artifacts / Sources section
      if (artifacts.length > 0) {
        html += `<div style="border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--bg-secondary);margin-bottom:24px">`;
        html += `<h3 style="color:var(--text-primary);margin-bottom:12px;font-size:14px">Sources & Artifacts <span style="color:var(--text-dim);font-weight:400">${artifacts.length}</span></h3>`;
        artifacts.forEach(a => {
          const typeIcons = { google_doc: '\u{1F4DD}', retina_chart: '\u{1F4CA}', jira: '\u{1F3AB}', confluence: '\u{1F4D6}', slack: '\u{1F4AC}', github: '\u{1F4BB}', spreadsheet: '\u{1F4CA}', url: '\u{1F517}' };
          const icon = typeIcons[a.type] || '\u{1F517}';
          const typeLabel = (a.type || 'link').replace(/_/g, ' ');
          html += `<div style="padding:8px 0;border-bottom:1px solid var(--bg-tertiary)">`;
          html += `<div style="display:flex;align-items:start;gap:8px">`;
          html += `<span style="flex-shrink:0;font-size:14px">${icon}</span>`;
          html += `<div style="flex:1;min-width:0">`;
          if (a.url) {
            html += `<a href="${esc(a.url)}" target="_blank" style="color:var(--accent);text-decoration:none;font-size:13px;font-weight:500">${esc(a.title || a.url)}</a>`;
          } else {
            html += `<span style="color:var(--text-primary);font-size:13px;font-weight:500">${esc(a.title || 'Untitled')}</span>`;
          }
          html += `<span style="color:var(--text-dim);font-size:11px;margin-left:8px">${typeLabel}</span>`;
          if (a.description) {
            html += `<div style="color:var(--text-secondary);font-size:12px;margin-top:2px;line-height:1.4">${esc(a.description)}</div>`;
          }
          html += `</div></div></div>`;
        });
        html += `</div>`;
      }

      html += '</div>';
      // Race guard: showWorkspaceInfo fires several async fetches and only
      // writes to `content` at the end. If the user clicked a repo tab
      // mid-flight, selectWorkspaceRepo + loadDiff already painted the diff.
      // Also bail if `_workspaceDocPath` is set — selectRepo now fires
      // showWorkspaceInfo and openWorkspaceDoc in parallel, and the doc paint
      // owns `content` whenever a remembered doc was found.
      if (currentRepo || _workspaceDocPath) return;
      content.innerHTML = html;
      if (preserveScroll) content.scrollTop = prevContentScroll;

    } catch (err) {
      if (currentRepo) return;
      content.innerHTML = `<div class="no-repo"><p>Error loading workspace dashboard: ${err.message}</p></div>`;
    }
  }

  // ─── Theme + Settings ───
  const THEME_KEY = 'gdiff-theme';
  const AGENT_LABELS = { claude: 'Claude Code', codex: 'Codex', copilot: 'Copilot' };
  // Best-effort model suggestions per agent. Stored free-form server-side, so an
  // unknown saved model is preserved (added as an extra option below).
  const MODEL_OPTIONS = {
    claude: ['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5'],
    codex: ['gpt-5-codex', 'gpt-5'],
    copilot: ['claude-sonnet-4-6', 'gpt-5', 'gpt-4.1'],
  };
  let _settings = { defaultAgent: 'claude', model: null, theme: 'dark' };
  let _vaultAgentPolicy = null; // {supported: string[], default: string}
  let _setDraft = null;      // {defaultAgent, model, theme} while the modal is open
  let _setWorkspaceDraft = null;  // {agent, model} override for the active workspace

  async function loadVaultAgentPolicy({force = false} = {}) {
    const vaultId = _termVaultId();
    if (_vaultAgentPolicy && _vaultAgentPolicy.vault === vaultId && !force) return _vaultAgentPolicy;
    try {
      const suffix = vaultId ? '?vault=' + encodeURIComponent(vaultId) : '';
      const r = await fetch('/api/vault/agents' + suffix);
      if (r.ok) {
        const policy = await r.json();
        const supported = Array.isArray(policy.supported)
          ? policy.supported.filter(a => Object.prototype.hasOwnProperty.call(AGENT_LABELS, a))
          : [];
        if (supported.length) {
          _vaultAgentPolicy = {
            vault: vaultId,
            supported,
            default: supported.includes(policy.default) ? policy.default : supported[0],
          };
          return _vaultAgentPolicy;
        }
      }
    } catch {}
    return {supported: Object.keys(AGENT_LABELS), default: _settings.defaultAgent || 'claude'};
  }

  function supportedAgentIds() {
    return (_vaultAgentPolicy && _vaultAgentPolicy.supported) || Object.keys(AGENT_LABELS);
  }

  function applyTheme(theme) {
    const light = theme === 'light';
    document.body.classList.toggle('light-mode', light);
    try { localStorage.setItem(THEME_KEY, light ? 'light' : 'dark'); } catch {}
  }
  // Fast-path: apply the cached theme before the settings fetch resolves (no flash).
  applyTheme(localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark');

  async function loadSettings() {
    try {
      const r = await fetch('/api/settings');
      if (r.ok) {
        _settings = await r.json();
        if (_settings.theme) applyTheme(_settings.theme);
      }
    } catch {}
  }

  function _fillModelSelect(sel, agent, selected) {
    const opts = MODEL_OPTIONS[agent] || [];
    const seen = new Set(opts);
    let html = '<option value="">Default (let agent decide)</option>';
    for (const m of opts) html += `<option value="${m}">${m}</option>`;
    if (selected && !seen.has(selected)) html += `<option value="${selected}">${selected}</option>`;
    sel.innerHTML = html;
    sel.value = selected || '';
  }

  function _buildSeg(containerId, options, current, onPick) {
    const c = document.getElementById(containerId);
    c.innerHTML = '';
    for (const o of options) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'seg-btn' + (o.value === current ? ' active' : '');
      b.textContent = o.label;
      b.onclick = () => onPick(o.value);
      c.appendChild(b);
    }
  }

  function _renderAutopilotRow() {
    const c = document.getElementById('setAutopilotRow');
    if (!c) return;
    const flags = _settings.autopilotFlags || {};
    c.innerHTML = '';
    for (const a of supportedAgentIds()) {
      const label = document.createElement('label');
      label.className = 'autopilot-check';
      label.title = flags[a]
        ? `Launch ${AGENT_LABELS[a]} with ${flags[a]}`
        : `Launch ${AGENT_LABELS[a]} with its auto flag`;
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = !!(_setDraft.autopilot && _setDraft.autopilot[a]);
      cb.onchange = () => { _setDraft.autopilot[a] = cb.checked; };
      label.appendChild(cb);
      label.appendChild(document.createTextNode(AGENT_LABELS[a]));
      c.appendChild(label);
    }
  }

  function _renderSettingsGlobal() {
    _buildSeg('setAgentSeg',
      supportedAgentIds().map(a => ({ value: a, label: AGENT_LABELS[a] })),
      _setDraft.defaultAgent,
      (a) => { _setDraft.defaultAgent = a; _setAgentTouched = true; _renderSettingsGlobal(); });
    _renderAutopilotRow();
    const modelSel = document.getElementById('setModel');
    _fillModelSelect(modelSel, _setDraft.defaultAgent, _setDraft.model);
    modelSel.onchange = (e) => { _setDraft.model = e.target.value || null; };
    _buildSeg('setThemeSeg',
      [{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }],
      _setDraft.theme,
      (t) => { _setDraft.theme = t; applyTheme(t); _renderSettingsGlobal(); });
  }

  // Dirty flags: the drafts CLAMP stored values that are vault-disabled
  // (for display), so saving must only write back fields the user actually
  // touched — otherwise saving a theme tweak would silently rewrite the
  // default agent or clear a workspace override.
  let _setAgentTouched = false;
  let _setWorkspaceTouched = false;

  async function openSettings() {
    const policy = await loadVaultAgentPolicy();
    _setAgentTouched = false;
    _setWorkspaceTouched = false;
    _setDraft = {
      defaultAgent: policy.supported.includes(_settings.defaultAgent)
        ? _settings.defaultAgent
        : policy.default,
      model: _settings.model || null,
      theme: document.body.classList.contains('light-mode') ? 'light' : 'dark',
      autopilot: { ...(_settings.autopilot || {}) },
    };
    _renderSettingsGlobal();

    // Per-workspace override (only when a real workspace tab is active).
    const sec = document.getElementById('setWorkspaceSection');
    _setWorkspaceDraft = null;
    const currentPid = (typeof currentWorkspace !== 'undefined' && currentWorkspace) ? currentWorkspace.name : null;
    const pid = currentPid && !currentPid.startsWith('__') ? currentPid : null;
    if (pid) {
      document.getElementById('setWorkspaceName').textContent = pid;
      sec.style.display = 'flex';
      const pAgent = document.getElementById('setWorkspaceAgent');
      const pModel = document.getElementById('setWorkspaceModel');
      pAgent.innerHTML = '<option value="">Inherit vault default</option>'
        + policy.supported.map(a => `<option value="${a}">${AGENT_LABELS[a]}</option>`).join('');
      pAgent.value = '';
      _fillModelSelect(pModel, _setDraft.defaultAgent, '');
      try {
        const r = await fetch('/api/workspaces/' + encodeURIComponent(pid));
        if (r.ok) {
          const workspace = await r.json();
          _setWorkspaceDraft = {
            agent: policy.supported.includes(workspace.agent) ? workspace.agent : '',
            model: workspace.model || '',
          };
          pAgent.value = _setWorkspaceDraft.agent || '';
          _fillModelSelect(pModel, _setWorkspaceDraft.agent || _setDraft.defaultAgent, _setWorkspaceDraft.model);
        }
      } catch {}
      pAgent.onchange = (e) => {
        _setWorkspaceDraft = _setWorkspaceDraft || { agent: '', model: '' };
        _setWorkspaceDraft.agent = e.target.value;
        _setWorkspaceTouched = true;
        _fillModelSelect(pModel, e.target.value || _setDraft.defaultAgent, _setWorkspaceDraft.model);
      };
      pModel.onchange = (e) => {
        _setWorkspaceDraft = _setWorkspaceDraft || { agent: '', model: '' };
        _setWorkspaceDraft.model = e.target.value;
        _setWorkspaceTouched = true;
      };
    } else {
      sec.style.display = 'none';
    }

    document.getElementById('settingsError').classList.remove('on');
    document.getElementById('settingsModal').classList.add('active');
  }

  function closeSettings() {
    document.getElementById('settingsModal').classList.remove('active');
  }

  async function saveSettings() {
    const btn = document.getElementById('setSaveBtn');
    const err = document.getElementById('settingsError');
    err.classList.remove('on');
    btn.disabled = true;
    try {
      const patch = {
        model: _setDraft.model || null,
        theme: _setDraft.theme,
        autopilot: _setDraft.autopilot || {},
      };
      // Only write the default agent back when the user picked one — the
      // draft may hold a display-only clamp of a vault-disabled value.
      if (_setAgentTouched || _setDraft.defaultAgent === _settings.defaultAgent) {
        patch.defaultAgent = _setDraft.defaultAgent;
      }
      const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'save failed');
      _settings = await r.json();
      applyTheme(_settings.theme);

      const pid = (typeof currentWorkspace !== 'undefined' && currentWorkspace) ? currentWorkspace.name : null;
      if (_setWorkspaceDraft && _setWorkspaceTouched && pid) {
        const pr = await fetch('/api/workspaces/' + encodeURIComponent(pid) + '/agent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent: _setWorkspaceDraft.agent || null,
            model: _setWorkspaceDraft.model || null,
          }),
        });
        if (!pr.ok) throw new Error((await pr.json().catch(() => ({}))).detail || 'workspace override failed');
      }
      closeSettings();
    } catch (e) {
      err.textContent = String(e.message || e);
      err.classList.add('on');
    } finally {
      btn.disabled = false;
    }
  }

  async function resyncAgents() {
    const btn = document.getElementById('setResyncBtn');
    const hint = document.getElementById('setResyncHint');
    const old = hint.textContent;
    btn.disabled = true;
    hint.textContent = 'checking…';
    try {
      const r = await fetch('/api/agents/context');
      if (!r.ok) throw new Error('context check failed');
      const data = await r.json();
      hint.textContent = data.ok ? 'Lab context is ready for new agent sessions.' : 'Lab context is missing; reinstall the Lab CLI.';
    } catch (e) {
      hint.textContent = 'check failed: ' + (e.message || e);
    } finally {
      btn.disabled = false;
      setTimeout(() => { hint.textContent = old; }, 6000);
    }
  }

  afterPageQuiet(loadSettings);

  // ─── Init ───
  // Drop the pre-paint "hide the placeholder" class now that JS owns
  // the page — error-state .no-repo messages can surface normally.
  document.documentElement.classList.remove('loading');
  const urlWorkspace = new URLSearchParams(location.search).get('workspace');
  // When ?ui_check=1, skip all persistent timers + WS so Chrome's --dump-dom
  // can reach network idle and exit promptly. See scripts/check-ui.sh.
  const UI_CHECK = new URLSearchParams(location.search).get('ui_check') === '1';

  // Workspace tab-strip state. MUST be declared before workspaceTabsRefresh() is
  // called below, or `let` TDZ throws "Cannot access X before initialization".
  let workspaceTabsAll = [];           // workspaces from every registered vault
  let workspaceTabsRefreshTimer = null;
  const _vaultResourceRequests = new Set();
  let workspaceTabsOrder = [];        // user-chosen order (from /api/ui/tab-order)
  let workspaceTabsOrderReady = false;
  let workspaceTabsOrderLoad = null;
  let workspaceTabsOrderSave = Promise.resolve();
  let workspaceTabsDragId = null;      // absolute workspace path being dragged
  let _contextSubView = 'overview';
  function _vaultById(vaultId) {
    return (vaultCatalog || []).find(vault => vault && vault.id === vaultId) || null;
  }

  function _workspaceVaultId(workspace) {
    if (!workspace) return null;
    if (workspace.vault_id) return workspace.vault_id;
    if (workspace.vault) return workspace.vault;
    const known = [...(workspacesList || []), ...(workspaceTabsAll || [])]
      .find(candidate => candidate && candidate.path === workspace.path);
    if (known && (known.vault_id || known.vault)) {
      return known.vault_id || known.vault;
    }
    const normalizedPath = String(workspace.path || '').replace(/\/+$/, '');
    const owner = (vaultCatalog || []).find(vault => {
      const root = String(vault && vault.path || '').replace(/\/+$/, '');
      return root && (normalizedPath === root || normalizedPath.startsWith(root + '/'));
    });
    return owner ? owner.id : null;
  }

  function _vaultForWorkspace(workspace) {
    if (!workspace) return null;
    const vaultId = _workspaceVaultId(workspace);
    return _vaultById(vaultId) || {
      id: vaultId || '',
      name: workspace.vault_name || vaultId || '',
      color: workspace.vault_color || '#8b949e',
      path: workspace.vault_path || '',
    };
  }

  function _termHomeViewActive() {
    return document.body.classList.contains('self-active')
      || document.body.classList.contains('vault-active');
  }

  function _termVaultId() {
    if (_termHomeViewActive()) return null;
    if (document.body.classList.contains('assistant-active')) return ASSISTANT_VAULT_ID;
    return _workspaceVaultId(currentWorkspace);
  }

  function _vaultQuery(vaultId = _termVaultId()) {
    return vaultId ? '&vault=' + encodeURIComponent(vaultId) : '';
  }

  function _termSessionsKey(workspaceId, vaultId = _termVaultId()) {
    return String(vaultId || 'framework') + '::' + String(workspaceId || '');
  }

  // Home owns one terminal pool. Section associations and recency only select
  // from that pool; moving a label never moves a process or changes its cwd.
  function _termHomeSection() {
    if (!_termHomeViewActive()) return null;
    if (document.body.classList.contains('vault-active')) {
      const vault = _workspaceVaultId(currentWorkspace);
      return vault ? 'vault:' + vault : 'home';
    }
    return _contextSubView === 'logs' ? 'logs' : 'home';
  }

  function _termReadHomeAssociations() {
    try {
      const value = JSON.parse(localStorage.getItem('labTermHomeAssociations') || '{}');
      return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
    } catch { return {}; }
  }

  function _termHomeAssociation(session, state = _termReadHomeAssociations()) {
    const stored = state[session?.logical_name];
    if (typeof stored?.section === 'string') return stored.section;
    // Existing sessions linked to a vault folder already have an owner.
    const root = session?.linked_scope?.root || '';
    const vault = (vaultCatalog || []).filter(v => v.path &&
      (root === v.path || root.startsWith(v.path.replace(/\/+$/, '') + '/')))
      .sort((a, b) => b.path.length - a.path.length)[0];
    return vault ? 'vault:' + vault.id : 'home';
  }

  function _termHomeAssociationOptions() {
    return [{id: 'home', name: 'Home', color: '#8b949e'},
      ...(vaultCatalog || []).map(v => ({id: 'vault:' + v.id, name: v.name || v.id,
        color: /^#[0-9a-f]{6}$/i.test(v.color || '') ? v.color : '#8b949e'})),
      {id: 'logs', name: 'Logs', color: '#f85149'}];
  }

  function _termSaveHomeAssociation(logical, section, usedAt = Date.now()) {
    if (!logical || !section) return;
    const state = _termReadHomeAssociations();
    state[logical] = {section, usedAt};
    try { localStorage.setItem('labTermHomeAssociations', JSON.stringify(state)); } catch {}
  }

  function _termHomeRestoreName() {
    const section = _termHomeSection();
    if (!section) return null;
    const state = _termReadHomeAssociations();
    const sessions = (termSessions || []).filter(s => _termHomeAssociation(s, state) === section);
    sessions.sort((a, b) => (Number(state[b.logical_name]?.usedAt) || 0)
      - (Number(state[a.logical_name]?.usedAt) || 0));
    return sessions[0]?.name || null;
  }

  function _termSelectHomeSection() {
    const name = _termHomeRestoreName();
    // Calling attach even for the mounted session also invalidates any older
    // in-flight section selection; its warm path keeps the connection intact.
    if (name) void termAttach(name, '__self__');
  }

  let _termTabActivationSeq = 0;

  async function _termActivateTab(name) {
    const request = ++_termTabActivationSeq;
    const workspaceId = _termActiveWorkspaceId();
    const session = (termSessions || []).find(row => row.name === name);
    if (!session || !workspaceId) return;
    if (workspaceId === '__self__') {
      const section = _termHomeAssociation(session);
      // Remember the exact clicked session before navigation restores the
      // section's latest terminal (there may be several with the same badge).
      _termRememberLast(workspaceId, session.logical_name);
      if (section !== _termHomeSection()) {
        if (section.startsWith('vault:')) await goToVault(section.slice(6));
        else await goToProductivity({subview: section === 'logs' ? 'logs' : 'overview'});
      } else if (section === 'home' && (_contextSubView !== 'overview' || _workspaceDocPath || currentRepo)) {
        selfShowWorkbench();
      }
      if (section !== _termHomeSection()) return;
    }
    if (request !== _termTabActivationSeq || !_termIsScopeActive(workspaceId)) return;
    void _termOpenLinkedFile(session);
    // A click is an explicit retry, including when the socket died while parked.
    if (termDeadSessions.has(name)) {
      _termClearDead(name);
      delete _termAutoRestoreAt[name];
      let refreshOk = false;
      try { refreshOk = !!(await _termRefreshSessionsForWorkspaceId(workspaceId)); } catch {}
      if (request !== _termTabActivationSeq || !_termIsScopeActive(workspaceId)) return;
      if (!termSessions.some(s => s.name === name)) {
        if (refreshOk) _termSessionGone(name, workspaceId);
        else termShowRecovery();
        return;
      }
    }
    // The mounted-session fast path also cancels an older pending attach.
    await termAttach(name, workspaceId);
  }

  function _termHomeAssociationHtml(session) {
    if (_termActiveWorkspaceId() !== '__self__') return '';
    const id = _termHomeAssociation(session);
    const association = _termHomeAssociationOptions().find(item => item.id === id)
      || {name: id.replace(/^vault:/, ''), color: '#8b949e'};
    return `<span class="term-home-association" style="--term-association-color:${association.color}" title="Associated with ${termSessEsc(association.name)}"><span>${termSessEsc(association.name)}</span></span>`;
  }

  // Which tab (if any) looks blocked because a recent fetch for it hit
  // fsguard's 503 (stalled vault volume). error-report.js can't know
  // which workspace a given fetch belongs to, so it just dispatches the
  // event and we mark whatever workspace tab is currently active -- good
  // enough to answer "is my SSD read stuck?" without precise attribution.
  // Cleared as soon as any later fetch succeeds.
  let tabBlocked = { pid: null, detail: null };
  window.addEventListener('lab:resource-unavailable', (ev) => {
    const pid = (currentWorkspace && currentWorkspace.is_workspace) ? currentWorkspace.name : null;
    if (!pid) return;
    tabBlocked = { pid, detail: (ev.detail && ev.detail.message) || 'resource is not available' };
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
  });
  window.addEventListener('lab:resource-available', () => {
    if (!tabBlocked.pid) return;
    tabBlocked = { pid: null, detail: null };
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
  });

  // Workspace tabs the user has opened. The durable bit still lives in each
  // workspace's own workspace.json. Vaults are sections inside Home.
  function workspaceTabsOpenIds() {
    return (workspaceTabsAll || []).filter(p => p && p.tab_open).map(p => p.path);
  }
  async function workspaceTabsSetOpen(workspacePath, open) {
    if (!workspacePath) return;
    try {
      const infoRes = await fetch('/api/workspace-info?path=' + encodeURIComponent(workspacePath));
      if (!infoRes.ok) throw new Error('workspace not found');
      const info = await infoRes.json();
      info.tab_open = !!open;
      await fetch('/api/workspace-info', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: workspacePath, data: info}),
      });
    } catch (e) { /* best-effort; next refresh will pick up the truth */ }
    const p = (workspaceTabsAll || []).find(x => x && x.path === workspacePath);
    if (p) p.tab_open = !!open;
  }
  // Knowledge-view state. Same hoisting rule — initCerebro uses these.
  const CEREBRO_WORKSPACE_ID = '__cerebro__';
  let cerebroTreeData = [];
  let _cerebroTreePromise = null;
  let _cerebroTreeFetchedAt = 0;
  const CEREBRO_TREE_TTL_MS = 15000;
  let cerebroActivePath = null;
  // Hydrate from localStorage so folded/unfolded state survives reloads.
  // Persisted in lockstep on every toggle below.
  const cerebroExpanded = _treeLoadOpenSet('cerebro');  // dir paths currently open

  // Productivity self-view: the monorepo itself (commits + uncommitted + tasks).
  // Pseudo-workspace like Cerebro; no folder under knowledge/workspaces/.
  const SELF_WORKSPACE_ID = '__self__';
  const SELF_REPO_PATH = window.LAB_MONOREPO_ROOT || '';  // populated by index.html
  const VAULT_ROOT = window.LAB_VAULT_ROOT || '';  // active vault; may differ from framework root
  const ASSISTANT_WORKSPACE_ID = '__assistant__';
  const ASSISTANT_VAULT_ID = '__assistant__';
  let ASSISTANT_ROOT = window.LAB_ASSISTANT_ROOT || '';

  // Vault view: one management surface per registered vault. The
  // selected vault id travels in the URL and requests; no global switch.
  const VAULT_WORKSPACE_ID = '__vault__';
  let _vaultCurrent = null;  // last `current` row painted by initVaultView

  // Per-workspace session pill cache (warm-switch fast path). Declared up
  // here — alongside the other pseudo-workspace consts — instead of with
  // the rest of the terminal-panel state lower in the script, because
  // initCerebro/initSelf now read it synchronously before their first
  // await. The terminal state block at ~line 5780 still hosts the rest
  // of the related globals; this is the one that needs to win the TDZ.
  const _termSessionsCache = new Map(); // workspaceId -> sessions[]

  // localStorage key prefix for per-view terminal-visibility. Same
  // hoisting rule as the consts above — the visibility helpers are
  // called from termOpenForSelf/Cerebro during the initial URL
  // dispatch (`?view=…`), which runs before the helper definitions
  // further down the script. Without this hoist the helpers hit a
  // TDZ on `_TERM_VIS_KEY_PREFIX`.
  const _TERM_VIS_KEY_PREFIX = 'labTermShown:';
  const _TERM_SESSION_ORIENTATION_KEY = 'labTermSessionOrientation';
  const _TERM_SESSION_WIDTH_KEY = 'labTermSessionWidth';
  const _TERM_GROUPS_KEY = 'labTermGroups-v1';
  const _TERM_RECENT_MINUTES_KEY = 'labTermRecentMinutes';
  // Dots start green instead of inheriting the old bar/background color.
  const _TERM_RECENT_COLOR_KEY = 'labTermRecentDotColor';
  const _TERM_RECENT_ACTIVITY_KEY = 'labTermRecentActivity-v1';
  const _TERM_RECENT_MINUTE_OPTIONS = [15, 30, 60, 180, 360, 720, 1440];
  const _TERM_GROUP_COLORS = ['#58a6ff', '#a371f7', '#3fb950', '#d29922', '#f85149', '#db61a2', '#39c5cf', '#8b949e'];
  let termSessionOrientation = 'vertical';
  let termSessionWidth = null;
  let termRecentMinutes = 60;
  let termRecentColor = '#3fb950';
  let termRecentActivity = {};
  try {
    if (localStorage.getItem(_TERM_SESSION_ORIENTATION_KEY) === 'horizontal') {
      termSessionOrientation = 'horizontal';
    }
    const storedWidth = parseFloat(localStorage.getItem(_TERM_SESSION_WIDTH_KEY));
    if (Number.isFinite(storedWidth)) termSessionWidth = Math.max(62, Math.min(220, storedWidth));
    // Preserve the old compact preference as an initial width, then use drag sizing.
    else if (localStorage.getItem('labTermSessionDetail') === 'compact') termSessionWidth = 62;
    const storedRecentMinutes = localStorage.getItem(_TERM_RECENT_MINUTES_KEY);
    if (storedRecentMinutes !== null) termRecentMinutes = _termNormalizeRecentMinutes(storedRecentMinutes);
    termRecentColor = _termNormalizeRecentColor(localStorage.getItem(_TERM_RECENT_COLOR_KEY));
    const storedRecentActivity = JSON.parse(localStorage.getItem(_TERM_RECENT_ACTIVITY_KEY) || '{}');
    if (storedRecentActivity && typeof storedRecentActivity === 'object' && !Array.isArray(storedRecentActivity)) {
      termRecentActivity = storedRecentActivity;
    }
  } catch {}

  function _termNormalizeRecentMinutes(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return 60;
    return _TERM_RECENT_MINUTE_OPTIONS.reduce((nearest, option) =>
      Math.abs(option - parsed) < Math.abs(nearest - parsed) ? option : nearest
    , 60);
  }

  function _termNormalizeRecentColor(value) {
    const color = String(value || '').trim().toLowerCase();
    return /^#[0-9a-f]{6}$/.test(color) ? color : '#3fb950';
  }

  function _termRecentWindowLabel(minutes = termRecentMinutes) {
    return minutes < 60 ? `${minutes}m` : `${Math.round(minutes / 60)}h`;
  }

  function _termRecentScopeKey(workspaceId = _termActiveWorkspaceId(), vaultId = _termVaultId()) {
    return _termSessionsKey(workspaceId, vaultId);
  }

  function _termMarkRecent(workspaceId, sessionName, vaultId = _termVaultId(), usedAt = Date.now()) {
    if (!workspaceId || !sessionName) return;
    const session = (termSessions || []).find(item => item && item.name === sessionName);
    const logical = session && session.logical_name;
    if (!logical) return;
    const scope = _termRecentScopeKey(workspaceId, vaultId);
    const scoped = termRecentActivity[scope] && typeof termRecentActivity[scope] === 'object'
      ? termRecentActivity[scope] : {};
    scoped[logical] = Number(usedAt) || Date.now();
    termRecentActivity[scope] = scoped;
    try { localStorage.setItem(_TERM_RECENT_ACTIVITY_KEY, JSON.stringify(termRecentActivity)); } catch {}
  }

  function _termSessionRecentMeta(session, now = Date.now()) {
    if (!(session && session.logical_name)) return null;
    const scoped = termRecentActivity[_termRecentScopeKey()];
    const usedAt = Number(scoped && scoped[session.logical_name]);
    if (!Number.isFinite(usedAt) || usedAt <= 0) return null;
    const ageMs = Math.max(0, Number(now) - usedAt);
    if (ageMs > termRecentMinutes * 60 * 1000) return null;
    const ageMinutes = Math.floor(ageMs / 60000);
    return {
      usedAt,
      label: ageMinutes < 1 ? 'used just now' : `used ${ageMinutes}m ago`,
    };
  }

  function _termApplyRecentSettings() {
    const btn = document.getElementById('termRecentSettingsBtn');
    const label = document.getElementById('termRecentButtonLabel');
    const select = document.getElementById('termRecentMinutes');
    const colorInput = document.getElementById('termRecentColor');
    const colorValue = document.getElementById('termRecentColorValue');
    const panel = document.getElementById('termPanel');
    const windowLabel = _termRecentWindowLabel();
    if (btn) btn.title = `Recent terminal highlight: ${windowLabel}`;
    if (label) label.textContent = windowLabel;
    if (select && String(select.value) !== String(termRecentMinutes)) select.value = String(termRecentMinutes);
    if (colorInput && colorInput.value.toLowerCase() !== termRecentColor) colorInput.value = termRecentColor;
    if (colorValue) colorValue.textContent = termRecentColor;
    if (panel && panel.style) panel.style.setProperty('--term-recent-color', termRecentColor);
  }

  function termSetRecentMinutes(value) {
    termRecentMinutes = _termNormalizeRecentMinutes(value);
    try { localStorage.setItem(_TERM_RECENT_MINUTES_KEY, String(termRecentMinutes)); } catch {}
    _termApplyRecentSettings();
    termRenderSessionList();
  }

  function termSetRecentColor(value) {
    termRecentColor = _termNormalizeRecentColor(value);
    try { localStorage.setItem(_TERM_RECENT_COLOR_KEY, termRecentColor); } catch {}
    _termApplyRecentSettings();
    termRenderSessionList();
  }

  function termCloseRecentSettings() { termCloseSettings(); }

  let _termSettingsReturnFocus = null;
  function termOpenSettings() {
    termCloseGroupMenu();
    document.getElementById('termNewPicker')?.classList.remove('open');
    _termSettingsReturnFocus = document.activeElement;
    _termRenderNewOptionsSettings();
    _termApplyRecentSettings();
    document.getElementById('termOrientationSelect').value = termSessionOrientation;
    document.getElementById('termSettingsModal').classList.add('active');
    document.getElementById('termOrientationSelect').focus();
  }

  function termCloseSettings() {
    const modal = document.getElementById('termSettingsModal');
    if (!modal?.classList.contains('active')) return;
    modal.classList.remove('active');
    _termSettingsReturnFocus?.focus();
  }

  document.addEventListener('keydown', event => {
    const modal = document.getElementById('termSettingsModal');
    if (event.key === 'Escape') {
      termCloseSettings();
      termCloseGroupMenu();
      if (event.target.closest?.('#termSessionList, #termGroupMenu')) _termSelectTab(null);
      document.getElementById('termNewPicker')?.classList.remove('open');
    }
    if (event.key !== 'Tab' || !modal?.classList.contains('active')) return;
    const controls = [...modal.querySelectorAll('button:not(:disabled), select, input')];
    const first = controls[0], last = controls[controls.length - 1];
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });

  function termSetSessionView(setting, value) {
    if (setting === 'orientation' && ['vertical', 'horizontal'].includes(value)) {
      termSessionOrientation = value;
      try { localStorage.setItem(_TERM_SESSION_ORIENTATION_KEY, value); } catch {}
    }
    _termApplySessionView();
  }

  function _termSessionWidthBounds(panelWidth) {
    return {min: 62, max: Math.max(62, Math.min(220, panelWidth - 180))};
  }

  function _termApplySessionView(refit = true) {
    const panel = document.getElementById('termPanel');
    const sessionList = document.getElementById('termSessionList');
    const resizer = document.getElementById('termSessionsResizer');
    const horizontal = termSessionOrientation === 'horizontal';
    const panelWidth = panel?.getBoundingClientRect().width || 640;
    const bounds = _termSessionWidthBounds(panelWidth);
    const preferred = termSessionWidth ?? Math.max(160, Math.min(220, panelWidth * .34));
    const width = Math.max(bounds.min, Math.min(bounds.max, preferred));
    if (panel) {
      panel.style.setProperty('--term-sessions-width', width + 'px');
      panel.classList.toggle('term-sessions-horizontal', horizontal);
      panel.classList.toggle('term-sessions-full', horizontal ? panelWidth >= 420 : width >= 112);
      panel.classList.toggle('term-sessions-narrow', !horizontal && width < 180);
    }
    if (sessionList) sessionList.setAttribute('aria-orientation', horizontal ? 'horizontal' : 'vertical');
    if (resizer) {
      resizer.setAttribute('aria-valuemax', String(bounds.max));
      resizer.setAttribute('aria-valuenow', String(Math.round(width)));
    }
    if (!refit) return;
    requestAnimationFrame(() => {
      if (termXterm && termFitAddon) {
        try { termFitAddon.fit(); } catch {}
        termSendResize();
      }
    });
  }

  function termToggleSessionOrientation() {
    termSetSessionView('orientation', termSessionOrientation === 'horizontal' ? 'vertical' : 'horizontal');
  }

  function _termInitSessionResize() {
    const panel = document.getElementById('termPanel');
    const rail = document.getElementById('termSessionList');
    const resizer = document.getElementById('termSessionsResizer');
    if (!panel || !rail || !resizer) return;
    let drag = null;
    let frame = null;
    const apply = () => {
      if (frame !== null) return;
      frame = requestAnimationFrame(() => { frame = null; _termApplySessionView(); });
    };
    const setWidth = value => {
      const bounds = _termSessionWidthBounds(panel.getBoundingClientRect().width);
      termSessionWidth = Math.max(bounds.min, Math.min(bounds.max, value));
      apply();
    };
    const save = () => {
      try { localStorage.setItem(_TERM_SESSION_WIDTH_KEY, String(termSessionWidth)); } catch {}
    };
    resizer.addEventListener('pointerdown', event => {
      if (event.button !== 0 || drag || termSessionOrientation !== 'vertical') return;
      drag = {id: event.pointerId, x: event.clientX, width: rail.getBoundingClientRect().width, previous: termSessionWidth};
      resizer.setPointerCapture(event.pointerId);
      resizer.focus();
      resizer.classList.add('dragging');
      document.body.classList.add('term-resizing');
      event.preventDefault();
    });
    document.addEventListener('pointermove', event => {
      if (!drag || event.pointerId !== drag.id) return;
      setWidth(drag.width + event.clientX - drag.x);
    });
    const finish = (event, cancel = false) => {
      if (!drag || event.pointerId !== drag.id) return;
      if (cancel) { termSessionWidth = drag.previous; apply(); }
      else { setWidth(drag.width + event.clientX - drag.x); save(); }
      drag = null;
      resizer.classList.remove('dragging');
      document.body.classList.remove('term-resizing');
      if (resizer.hasPointerCapture(event.pointerId)) resizer.releasePointerCapture(event.pointerId);
    };
    document.addEventListener('pointerup', event => finish(event));
    document.addEventListener('pointercancel', event => finish(event, true));
    resizer.addEventListener('lostpointercapture', event => finish(event, true));
    resizer.addEventListener('keydown', event => {
      if (termSessionOrientation !== 'vertical') return;
      const bounds = _termSessionWidthBounds(panel.getBoundingClientRect().width);
      const width = rail.getBoundingClientRect().width;
      const next = {ArrowLeft: width - 10, ArrowRight: width + 10, Home: bounds.min, End: bounds.max}[event.key];
      if (next === undefined) return;
      event.preventDefault();
      setWidth(next);
      save();
    });
    // Also adapt when the surrounding terminal panel or browser changes size.
    new ResizeObserver(apply).observe(panel);
  }

  // Apply before the initial route dispatch so direct workspace/pseudo-workspace
  // loads never flash the default switcher shape. Refit is intentionally off:
  // terminal state is declared later and no xterm exists yet.
  _termApplySessionView(false);
  _termInitSessionResize();
  // Same TDZ hoist for the files-sidebar per-view persistence: the apply
  // helper runs inside _termApplyRememberedVisibility during the same
  // initial `?view=…` dispatch.
  const _SIDEBAR_VIS_KEY_PREFIX = 'labSidebarShown:';
  const _SIDEBAR_PCT_KEY_PREFIX = 'labSidebarPct:';
  _termApplyRecentSettings();

  // Productivity Admin's Servers / Terminals sections. Independent poll loop
  // and independent render targets keep those cards isolated from the rest of
  // the framework workbench.
  let _dashPollTimer = null;
  let _dashServersRows = [];
  let _dashServersAvailable = true;   // false once GET /api/servers 404s (not deployed yet)
  let _dashServersLoadErr = null;     // error from the GET (network/5xx)
  let _dashServersActionErr = null;   // error from the last start/stop
  const _dashServersPending = new Set();  // workspace_ids with an in-flight action
  let _dashTermsRows = [];
  let _dashTermsErr = null;
  const _dashTermsPending = new Set();    // session names / "group:<pid>" in-flight
  // Registered once at init (not per-paint, since document persists across
  // in-page navigation) — resumes the Servers/Terminals poll the instant the
  // tab regains focus rather than waiting out the rest of the 5s interval.
  // dashPollTick itself is a no-op when Admin isn't the active view.
  if (!UI_CHECK) {
    document.addEventListener('visibilitychange', () => { if (!document.hidden) dashPollTick(); });
  }

  // Auto-refresh workspace view when any file in the workspace folder changes (mtime check)
  let _lastWorkspaceMtime = 0;
  let _workspaceMtimeMissPath = null; // workspace path the miss counter applies to
  let _workspaceMtimeMisses = 0;      // consecutive "directory missing" responses
  let _workspaceMtimeTick = 0;
  let _workspaceMtimeInFlight = false;
  let _workspaceMtimeFailures = 0;
  let _workspaceMtimeRetryAt = 0;
  if (!UI_CHECK) setInterval(async () => {
    // A hidden tab can't show the refresh anyway, and the next visible
    // tick (≤1s away) catches up — don't let backgrounded windows keep
    // hitting the server (browser timer throttling made them poll ~1/min
    // forever, including tabs whose workspace no longer existed).
    if (document.hidden) return;
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    if (!currentWorkspace.path) return;
    if (currentRepo) return;
    if (_workspaceDocEditing) return;
    const workspacePath = currentWorkspace.path;
    const fileRoot = typeof _sidebarScopedRoot === 'function' ? _sidebarScopedRoot(workspacePath) : workspacePath;
    if (_workspaceMtimeMissPath !== fileRoot) {
      _workspaceMtimeMissPath = fileRoot;
      _workspaceMtimeMisses = 0;
      _workspaceMtimeFailures = 0;
      _workspaceMtimeRetryAt = 0;
      _lastWorkspaceMtime = 0;
    }
    // Never stack recursive filesystem walks. Previously the one-second
    // interval launched another request while the prior request was still
    // waiting on the 10-second filesystem guard. One timeout could therefore
    // leave dozens of queued requests, producing the 503 cascade seen in the
    // logs even after the original scan had already failed.
    if (_workspaceMtimeInFlight || Date.now() < _workspaceMtimeRetryAt) return;
    _workspaceMtimeTick += 1;
    // Workspace dir gone (deleted / volume unplugged): after a few misses,
    // probe only once a minute so it self-heals if the volume comes back.
    if (_workspaceMtimeMisses >= 3 && _workspaceMtimeTick % 60 !== 0) return;
    _workspaceMtimeInFlight = true;
    try {
      const res = await fetch(`/api/workspace-mtime?path=${encodeURIComponent(fileRoot)}`);
      if (!res.ok) throw new Error(`workspace mtime request failed (${res.status})`);
      const { mtime } = await res.json();
      // A request for a tab we just navigated away from must not overwrite
      // the new workspace's baseline or retry state.
      if (!currentWorkspace || currentWorkspace.path !== workspacePath
          || (typeof _sidebarScopedRoot === 'function' && _sidebarScopedRoot(workspacePath) !== fileRoot)) return;
      _workspaceMtimeFailures = 0;
      _workspaceMtimeRetryAt = 0;
      if (mtime == null) { _workspaceMtimeMisses += 1; return; }
      _workspaceMtimeMisses = 0;
      if (_lastWorkspaceMtime && mtime > _lastWorkspaceMtime) {
        const isSelf = document.body.classList.contains('self-active');
        const isVaultView = document.body.classList.contains('vault-active');
        const isAssistant = document.body.classList.contains('assistant-active');
        if (_workspaceDocPath) {
          // Refresh the doc AND the sidebar — files added/removed in
          // the workspace (e.g. a new HTML under tmp/) need to appear in
          // the sidebar without forcing the user to navigate away. The
          // self/vault views use their own sidebar renderers (no
          // workspace.json, no pinned/meta sections, no shared CLAUDE.md
          // / .claude shortcuts); calling _refreshWorkspaceSidebar here
          // would stomp them with the workspace layout.
          openWorkspaceDoc(_workspaceDocPath, {preserveScroll: true});
          if (isSelf) selfPopulateSidebar();
          else if (isVaultView) vaultPopulateSidebar();
          else _refreshWorkspaceSidebar({preserveScroll: true});
        } else if (isSelf) {
          // Self view, no doc open → just refresh the sidebar so new
          // files appear without a full page reload.
          selfPopulateSidebar();
        } else if (isVaultView) {
          vaultPopulateSidebar();
        } else if (isAssistant) {
          _refreshWorkspaceSidebar({preserveScroll: true});
          if (window.AssistantView) window.AssistantView.refresh();
        } else {
          showWorkspaceInfo({preserveScroll: true});
        }
      }
      _lastWorkspaceMtime = mtime;
    } catch(e) {
      if (currentWorkspace && currentWorkspace.path === workspacePath) {
        _workspaceMtimeFailures += 1;
        const backoffMs = Math.min(60_000, 1_000 * (2 ** _workspaceMtimeFailures));
        _workspaceMtimeRetryAt = Date.now() + backoffMs;
      }
    } finally {
      _workspaceMtimeInFlight = false;
    }
  }, 1000);

  // Sidebar git decorations poll. Separate from the 1s mtime poll above —
  // commits/checkouts only touch `.git/`, which the mtime walk skips — and
  // deliberately slower: the server caches `git status` for ~4s, so a 6s
  // cadence here means at most one subprocess per tick across all clients.
  if (!UI_CHECK) setInterval(() => {
    if (document.hidden) return;
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    if (currentRepo) return;
    _sidebarGitStatusRefresh();
  }, 6000);

  // ─── Terminal panel (tmux + PTY bridge) ───
  // Visible whenever a workspace is active; scoped to that workspace. xterm.js
  // and addons are vendored and lazy-loaded before the first attach. State
  // is initialized before the startup dispatch at the end of this script.

  let termXterm = null;         // xterm.js Terminal instance (active session)
  let termFitAddon = null;      // addon that sizes xterm to its container (active)
  let termWS = null;            // active WebSocket to /ws/term/<name>
  let termContainer = null;     // per-session <div> inside #termBody (active session)
  let termCurrentSession = null; // tmux session name currently attached
  let termCurrentWorkspaceId = null; // workspace/pseudo-workspace owning the active session
  let termSessions = [];        // last known list from /api/term/sessions
  let termUserDetached = false; // distinguishes user-initiated close from dropped WS
  let termRefreshTimer = null;  // periodic poll of /api/term/sessions
  let termReconnectTimer = null; // capped-backoff auto-reconnect loop
  let _termWheelListenerAdded = false; // wheel listener added once to termBody
  let _termPasteListenerAdded = false; // image paste listener added once to termBody
  let _termWheelAccum = 0;            // accumulated deltaY for scroll throttling
  let termAttachRequestSeq = 0;       // latest requested attach; prevents out-of-order switches
  // Per-session xterm+WS cache so SESSION-PILL switches (within the same
  // workspace, no navigation) don't wipe in-progress input.
  //
  // Workspace-tab clicks now navigate in-page, so this cache survives across
  // workspace switches. That makes the workspace id part of the identity: a
  // delayed attach from workspace A must never be allowed to display while
  // workspace B is active, even if both have a "claude" logical session.
  const _termCache = new Map(); // "workspaceId::name" -> {workspaceId, name, xterm, fitAddon, ws, container, parkedAt}
  // `_termSessionsCache` (workspaceId -> sessions[]) is the warm-switch
  // fast-path cache: it's declared at the top of the script (next to
  // CEREBRO_WORKSPACE_ID / SELF_WORKSPACE_ID) so initCerebro/initSelf can
  // read it synchronously without tripping the temporal dead zone.
  // Sessions the server has confirmed are gone ("no-session" exit frame)
  // OR that we've failed to reach N times in a row. While a name is in
  // this set, termAttach/onclose refuse to reconnect. Cleared only by an
  // explicit user action (new session, reload sessions, click the pill
  // again) or by the name disappearing from termSessions.
  const termDeadSessions = new Set();
  // Exponential backoff state per-session-name so dropped sessions don't
  // stack up one-shot timers faster than the server can accept them.
  const termReconnectAttempts = {};   // name -> consecutive failures
  const TERM_RECONNECT_BASE_MS = 800;
  const TERM_RECONNECT_CAP_MS = 30000;
  const TERM_FAST_PARK_MS = 10 * 60 * 1000;

  // Per-workspace "last selected" memory so leaving and returning to a workspace
  // (full page reload) restores whichever session pill the user had active
  // instead of snapping back to the canonical "claude" pill.
  //
  // Keyed by logical_name (not tmux name) because the logical name is the
  // workspace-relative identity and is stable across server/tmux restarts.
  // Stored as a single JSON map {workspaceId: logicalName}.
  const TERM_LAST_KEY = 'labTermLastSession';
  function _termActiveWorkspaceId() {
    if (document.body.classList.contains('cerebro-active')) return CEREBRO_WORKSPACE_ID;
    if (_termHomeViewActive()) return LAB_IS_ADMIN ? SELF_WORKSPACE_ID : null;
    if (document.body.classList.contains('assistant-active')) return ASSISTANT_WORKSPACE_ID;
    if (currentWorkspace && currentWorkspace.is_workspace) return currentWorkspace.name;
    return null;
  }
  async function termAutoSpawnEnabled(workspaceId, vaultId = _termVaultId()) {
    if (!workspaceId) return true;
    try {
      const r = await fetch('/api/ui/term-autospawn?workspace_id=' + encodeURIComponent(workspaceId) + _vaultQuery(vaultId));
      if (!r.ok) return true;
      const body = await r.json();
      return body.enabled !== false;
    } catch {
      return true;
    }
  }
  async function termSetAutoSpawnEnabled(workspaceId, enabled, vaultId = _termVaultId()) {
    if (!workspaceId) return;
    try {
      await fetch('/api/ui/term-autospawn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace_id: workspaceId, enabled: !!enabled, vault: vaultId}),
      });
    } catch {}
  }
  function _termRememberLast(workspaceId, logicalName) {
    if (workspaceId === '__self__') {
      const session = (termSessions || []).find(s => s.logical_name === logicalName);
      if (session) _termSaveHomeAssociation(logicalName, _termHomeAssociation(session));
    }
    if (!workspaceId || !logicalName) return;
    try {
      const raw = localStorage.getItem(TERM_LAST_KEY);
      const map = raw ? JSON.parse(raw) : {};
      if (map[workspaceId] === logicalName) return;
      map[workspaceId] = logicalName;
      localStorage.setItem(TERM_LAST_KEY, JSON.stringify(map));
    } catch {}
  }
  function _termRecallLast(workspaceId) {
    if (!workspaceId) return null;
    try {
      const raw = localStorage.getItem(TERM_LAST_KEY);
      if (!raw) return null;
      const map = JSON.parse(raw);
      return map[workspaceId] || null;
    } catch { return null; }
  }
  function _termPickRestoreName(workspaceId) {
    // Pick which session to attach when (re-)opening the panel: prefer the
    // user's last selection, fall back to canonical "claude", else first.
    if (!termSessions || termSessions.length === 0) return null;
    if (workspaceId === '__self__') {
      const sectionSession = _termHomeRestoreName();
      if (sectionSession) return sectionSession;
    }
    const lastLogical = _termRecallLast(workspaceId);
    if (lastLogical) {
      const hit = termSessions.find(s => s.logical_name === lastLogical);
      if (hit) return hit.name;
    }
    const claude = termSessions.find(s => s.logical_name === 'claude');
    return (claude || termSessions[0]).name;
  }
  function _termCacheKey(workspaceId, name) {
    return String(workspaceId || '') + '::' + String(name || '');
  }
  function _termCachedPaneIsFresh(cached) {
    if (!(cached && cached.ws && cached.ws.readyState === WebSocket.OPEN)) return false;
    if (cached.parkedAt && Date.now() - cached.parkedAt > TERM_FAST_PARK_MS) return false;
    return true;
  }
  function _termIsScopeActive(workspaceId) {
    return !!workspaceId && _termActiveWorkspaceId() === workspaceId;
  }
  function _termSessionMeta(name) {
    return (termSessions || []).find(s => s && s.name === name) || null;
  }
  function _termSessionBelongsTo(workspaceId, name) {
    const meta = _termSessionMeta(name);
    return !!meta && (!meta.workspace_id || meta.workspace_id === workspaceId);
  }
  function _termCanAttach(workspaceId, name) {
    return _termIsScopeActive(workspaceId) && _termSessionBelongsTo(workspaceId, name);
  }
  function _termAttachRequestIsCurrent(seq, workspaceId, name) {
    return seq === termAttachRequestSeq && _termCanAttach(workspaceId, name);
  }
  function _termSetPaneActive(container, active) {
    if (!container) return;
    if (!active && typeof container.contains === 'function') {
      const focused = document.activeElement;
      if (focused && container.contains(focused) && typeof focused.blur === 'function') {
        try { focused.blur(); } catch {}
      }
    }
    container.style.display = active ? 'block' : 'none';
    if (active) {
      if ('inert' in container) container.inert = false;
      if (typeof container.removeAttribute === 'function') container.removeAttribute('inert');
      if (typeof container.setAttribute === 'function') container.setAttribute('aria-hidden', 'false');
    } else {
      if ('inert' in container) container.inert = true;
      if (typeof container.setAttribute === 'function') container.setAttribute('inert', '');
      if (typeof container.setAttribute === 'function') container.setAttribute('aria-hidden', 'true');
    }
  }
  function _termHidePanesExcept(keep = null) {
    const body = document.getElementById('termBody');
    if (!body) return;
    for (const c of body.querySelectorAll('.term-pane')) {
      _termSetPaneActive(c, c === keep);
    }
  }
  function _termShowPane(pane) {
    _termHidePanesExcept(pane);
    _termSetPaneActive(pane, true);
  }
  function _termFocusActiveSoon(container = termContainer, xterm = termXterm) {
    setTimeout(() => {
      if (container !== termContainer || xterm !== termXterm) return;
      if (!termCurrentSession || !termCurrentWorkspaceId) return;
      try { xterm && xterm.focus && xterm.focus(); } catch {}
    }, 0);
  }

  // ─── Workspace tabs (Chrome-style) ───
  // State declarations are hoisted to the init block above (same TDZ reason
  // as the home view). Functions here; state is in the hoisted block so
  // workspaceTabsRefresh() can be called during init without tripping the
  // temporal dead zone on `workspaceTabsAll` / `workspaceTabsRefreshTimer`.

  function workspaceTabsLoadOrder() {
    if (!workspaceTabsOrderLoad) workspaceTabsOrderLoad = (async () => {
      try {
        const response = await fetch('/api/ui/tab-order');
        if (!response.ok) throw new Error('Could not load tab order');
        const order = await response.json();
        workspaceTabsOrder = Array.isArray(order) ? [...new Set(order.filter(key => typeof key === 'string' && key))] : [];
      } catch { /* use discovery order when saved state is unavailable */ }
      workspaceTabsOrderReady = true;
    })();
    return workspaceTabsOrderLoad;
  }

  function workspaceTabsSaveOrder() {
    const body = JSON.stringify({order: workspaceTabsOrder});
    // Serialize writes so a quick second drop cannot be overwritten by the first.
    workspaceTabsOrderSave = workspaceTabsOrderSave.catch(() => {}).then(() => fetch('/api/ui/tab-order', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body,
    })).catch(() => {});
    return workspaceTabsOrderSave;
  }

  async function workspaceTabsRefresh() {
    await workspaceTabsLoadOrder();
    try {
      const all = await fetchRepos();
      workspaceTabsAll = (Array.isArray(all) ? all : []).filter(p => p.is_workspace);
    } catch { /* leave stale state; next tick will retry */ }
    workspaceTabsRender();
    vaultRefreshWorkspaceResources();
  }

  function workspaceTabsRender() {
    const el = document.getElementById('workspaceTabs');
    if (!el || !workspaceTabsOrderReady || workspaceTabsDragId) return;
    const selfActive = document.body.classList.contains('self-active');
    const assistantActive = document.body.classList.contains('assistant-active');
    const vaultActive = document.body.classList.contains('vault-active');
    const activeWorkspacePath = document.body.classList.contains('workspace-active') && currentWorkspace
      ? currentWorkspace.path : null;
    const workspaceTabs = [];
    const seenPaths = new Set();
    const addWorkspace = workspace => {
      if (!workspace || !workspace.path || seenPaths.has(workspace.path)) return;
      seenPaths.add(workspace.path);
      workspaceTabs.push(workspace);
    };
    for (const path of workspaceTabsOpenIds()) addWorkspace((workspaceTabsAll || []).find(workspace => workspace.path === path));
    if (activeWorkspacePath) addWorkspace((workspaceTabsAll || []).find(workspace => workspace.path === activeWorkspacePath));
    const previousOrder = JSON.stringify(workspaceTabsOrder);
    // Old versions stored names. Migrate only unambiguous names across vaults.
    workspaceTabsOrder = [...new Set(workspaceTabsOrder.map(key => {
      const matches = workspaceTabsAll.filter(workspace => workspace.name === key);
      return matches.length === 1 ? matches[0].path : key;
    }))];
    for (const workspace of workspaceTabs) {
      if (!workspaceTabsOrder.includes(workspace.path)) workspaceTabsOrder.push(workspace.path);
    }
    workspaceTabs.sort((a, b) => workspaceTabsOrder.indexOf(a.path) - workspaceTabsOrder.indexOf(b.path));
    if (JSON.stringify(workspaceTabsOrder) !== previousOrder) workspaceTabsSaveOrder();

    let html = `
      <div class="workspace-tab self-tab${selfActive || vaultActive ? ' active' : ''}" data-kind="productivity" data-key="${SELF_WORKSPACE_ID}" role="tab" title="Home">
        <span class="label">&#x1F3E0; Home</span>
      </div>`;
    if (LAB_IS_ADMIN) html += `
      <div class="workspace-tab assistant-tab${assistantActive ? ' active' : ''}" data-kind="assistant" data-key="${ASSISTANT_WORKSPACE_ID}" role="tab" title="Global Assistant tasks">
        <span class="label">&#x2726; Assistant</span>
      </div>`;
    html += workspaceTabs.map(workspace => {
      const vault = _vaultForWorkspace(workspace);
      const active = activeWorkspacePath === workspace.path ? ' active' : '';
      const color = workspaceTabsEsc((vault && vault.color) || '#8b949e');
      const blocked = tabBlocked.pid === workspace.name ? ' blocked' : '';
      return `
        <div class="workspace-tab vault-owned${active}${blocked}" draggable="true" style="--vault-color:${color}" data-kind="workspace" data-key="${workspaceTabsEsc(workspace.path)}" data-workspace-id="${workspaceTabsEsc(workspace.name)}" data-vault="${workspaceTabsEsc(workspace.vault || '')}" role="tab" title="${workspaceTabsEsc((vault && (vault.name || vault.id)) || '')} · ${workspaceTabsEsc(workspace.path)}">
          <span class="vault-mark"></span>
          <span class="label">${workspaceTabsEsc(_workspaceDisplayName(workspace))}</span>
          <button class="x" title="Close workspace tab (resources keep running)" data-x="${workspaceTabsEsc(workspace.path)}">&times;</button>
        </div>`;
    }).join('');
    // Polling should preserve the existing nodes, listeners, and focus when
    // the visible tabs have not changed. Compare source markup, not innerHTML
    // (the browser normalizes entities and attribute serialization).
    if (el._labTabsHtml === html) return;
    el._labTabsHtml = html;
    el.innerHTML = html;

    workspaceTabsWireDnD(el);
    el.querySelectorAll('.workspace-tab').forEach(node => {
      node.addEventListener('click', (e) => {
        if (e.target.closest('.x')) return;  // X handled separately
        const kind = node.getAttribute('data-kind');
        const key = node.getAttribute('data-key');
        if (kind === 'productivity') { goToProductivity(); return; }
        if (kind === 'assistant') { goToAssistant(); return; }
        if (kind === 'workspace' && key) goToWorkspace(key);
      });
    });
    el.querySelectorAll('.workspace-tab .x').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const tab = btn.closest('.workspace-tab');
        workspaceTabsClose({
          key: btn.getAttribute('data-x'),
          kind: tab && tab.getAttribute('data-kind'),
          workspaceId: tab && tab.getAttribute('data-workspace-id'),
          vault: tab && tab.getAttribute('data-vault'),
        });
      });
    });
  }

  function workspaceTabsWireDnD(container) {
    container.querySelectorAll('.workspace-tab[data-kind="workspace"]').forEach(tab => {
      tab.addEventListener('dragstart', (e) => {
        workspaceTabsDragId = tab.getAttribute('data-key');
        tab.classList.add('dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', workspaceTabsDragId);
        }
      });
      tab.addEventListener('dragend', () => {
        tab.classList.remove('dragging');
        container.querySelectorAll('.workspace-tab.drop-before, .workspace-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        workspaceTabsDragId = null;
        workspaceTabsRender();
      });
      tab.addEventListener('dragover', (e) => {
        if (!workspaceTabsDragId) return;
        e.preventDefault();  // allow drop
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        container.querySelectorAll('.workspace-tab.drop-before, .workspace-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        const rect = tab.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        tab.classList.add(before ? 'drop-before' : 'drop-after');
      });
      tab.addEventListener('drop', async (e) => {
        e.preventDefault();
        const src = workspaceTabsDragId;
        const dst = tab.getAttribute('data-key');
        workspaceTabsDragId = null;
        container.querySelectorAll('.workspace-tab.drop-before, .workspace-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        if (!src || !dst || src === dst) return;
        const rect = tab.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        await workspaceTabsReorder(src, dst, before);
      });
    });
  }

  async function workspaceTabsReorder(srcPath, dstPath, placeBefore) {
    const current = [...workspaceTabsOrder];
    const srcIdx = current.indexOf(srcPath);
    if (srcPath === dstPath || srcIdx === -1 || !current.includes(dstPath)) return;
    current.splice(srcIdx, 1);
    let dstIdx = current.indexOf(dstPath);
    if (!placeBefore) dstIdx += 1;
    current.splice(dstIdx, 0, srcPath);

    workspaceTabsOrder = current;
    workspaceTabsRender();
    await workspaceTabsSaveOrder();
  }

  function workspaceTabsEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  async function workspaceTabsClose({key, kind, workspaceId, vault}) {
    if (!key || kind === 'productivity') return;
    if (kind !== 'workspace' || !workspaceId) return;
    const wasActive = currentWorkspace && currentWorkspace.path === key;
    await workspaceTabsSetOpen(key, false);
    if (wasActive && currentWorkspace?.path === key) goToVault(vault);
    await workspaceTabsRefresh();
  }

  function workspaceTabsClosePicker(restoreFocus = false) {
    document.getElementById('workspaceTabsPicker')?.classList.remove('open');
    const button = document.getElementById('workspaceTabsPlusBtn');
    button?.setAttribute('aria-expanded', 'false');
    if (restoreFocus) button?.focus();
  }

  function workspaceTabsTogglePicker(ev) {
    if (ev) ev.stopPropagation();
    const picker = document.getElementById('workspaceTabsPicker');
    const button = document.getElementById('workspaceTabsPlusBtn');
    if (!picker || !button) return;
    if (picker.classList.contains('open')) {
      workspaceTabsClosePicker();
      return;
    }
    workspaceTabsRenderPicker();
    picker.classList.add('open');
    button.setAttribute('aria-expanded', 'true');
    const bounds = button.getBoundingClientRect();
    picker.style.left = Math.max(8, Math.min(bounds.left, window.innerWidth - picker.offsetWidth - 8)) + 'px';
    picker.style.top = (bounds.bottom + 10) + 'px';
    picker.querySelector('select, button')?.focus();
  }

  document.addEventListener('click', event => {
    const picker = document.getElementById('workspaceTabsPicker');
    if (picker && !picker.contains(event.target) && !event.target.closest('#workspaceTabsPlusBtn')) {
      workspaceTabsClosePicker();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && document.getElementById('workspaceTabsPicker')?.classList.contains('open')) {
      event.preventDefault();
      event.stopPropagation();
      workspaceTabsClosePicker(true);
    }
  });
  document.addEventListener('focusin', event => {
    if (!event.target.closest('.workspace-tabs-plus-wrap')) workspaceTabsClosePicker();
  });
  window.addEventListener('resize', () => workspaceTabsClosePicker());

  function workspaceTabsRenderPicker(vaultId = '', creating = false) {
    const picker = document.getElementById('workspaceTabsPicker');
    if (!picker) return;
    const vaults = (vaultCatalog || []).filter(vault => !vault.unavailable);
    if (!vaults.length) {
      picker.innerHTML = '<div class="empty">No vaults available. Add a vault in Home.</div>';
      return;
    }
    if (creating) {
      picker.innerHTML = `
        <button type="button" class="row" data-action="back">← Back</button>
        <div class="picker-heading">New workspace · Choose a vault</div>
        ${vaults.map(vault => `
          <button type="button" class="row" data-create-vault="${workspaceTabsEsc(vault.id)}">
            <span class="vault-mark" style="--vault-color:${workspaceTabsEsc(vault.color || '#8b949e')}"></span>
            <span class="label">${workspaceTabsEsc(vault.name || vault.id)}</span>
          </button>`).join('')}`;
      picker.querySelector('[data-action="back"]').addEventListener('click', () => {
        workspaceTabsRenderPicker(vaultId);
        picker.querySelector('[data-action="create"]')?.focus();
      });
      picker.querySelectorAll('[data-create-vault]').forEach(row => {
        row.addEventListener('click', () => {
          const vault = vaults.find(vault => vault.id === row.getAttribute('data-create-vault'));
          workspaceTabsClosePicker();
          openVaultWorkspaceModal(vault);
        });
      });
      return;
    }
    const openWorkspaces = new Set(workspaceTabsOpenIds());
    const selectedVault = vaults.find(vault => vault.id === vaultId);
    const shownVaults = selectedVault ? [selectedVault] : vaults;
    picker.innerHTML = `
      ${LAB_IS_ADMIN ? '<button type="button" class="row" data-action="create"><span aria-hidden="true">+</span><span>New workspace</span></button>' : ''}
      <div class="picker-heading">Open existing workspace</div>
      <label class="picker-vault">From<select aria-label="Workspace vault">
        <option value="">All vaults</option>
        ${vaults.map(vault => `<option value="${workspaceTabsEsc(vault.id)}"${vault.id === selectedVault?.id ? ' selected' : ''}>${workspaceTabsEsc(vault.name || vault.id)}</option>`).join('')}
      </select></label>
      ${shownVaults.map(vault => {
        const candidates = (vault.workspace_rows || []).filter(workspace => workspace.is_workspace);
        return `<section class="picker-vault-group" style="--vault-color:${workspaceTabsEsc(vault.color || '#8b949e')}" aria-label="${workspaceTabsEsc(vault.name || vault.id)}">
          <div class="picker-vault-name"><span class="vault-mark"></span>${workspaceTabsEsc(vault.name || vault.id)}</div>
          ${candidates.length ? candidates.map(workspace => `
            <button type="button" class="row" data-path="${workspaceTabsEsc(workspace.path)}">
              <span class="label">${workspaceTabsEsc(_workspaceDisplayName(workspace))}</span>
              ${openWorkspaces.has(workspace.path) ? '<span class="meta">Open</span>' : ''}
            </button>`).join('') : '<div class="empty">No workspaces in this vault yet.</div>'}
        </section>`;
      }).join('')}`;
    picker.querySelector('select').addEventListener('change', event => {
      workspaceTabsRenderPicker(event.target.value);
      picker.querySelector('select')?.focus();
    });
    picker.querySelector('[data-action="create"]')?.addEventListener('click', () => {
      if (selectedVault) {
        workspaceTabsClosePicker();
        openVaultWorkspaceModal(selectedVault);
      } else {
        workspaceTabsRenderPicker(vaultId, true);
        picker.querySelector('[data-create-vault]')?.focus();
      }
    });
    picker.querySelectorAll('[data-path]').forEach(row => {
      row.addEventListener('click', () => {
        workspaceTabsClosePicker();
        goToWorkspace(row.getAttribute('data-path'));
      });
    });
  }

  function workspaceTabsStartPolling() {
    if (workspaceTabsRefreshTimer) return;
    workspaceTabsRefreshTimer = setInterval(workspaceTabsRefresh, 5000);
  }

  async function termOpenForWorkspace(workspaceId) {
    // Show the panel and restore every session this workspace had.
    //
    // "Restore every session" means: compare live tmux sessions against the
    // saved list in workspace.json, and respawn any saved entry whose logical
    // name isn't currently live. For claude entries this POST path re-uses
    // the saved claude_session_id via --resume. This is the key to
    // ``claude-2`` (and friends) coming back after a tab-close → reopen.
    //
    // Per-user opt-out of both auto-respawn and first-time auto-spawn via
    // ``localStorage.labTermAutoSpawn = "0"``. Explicitly closing the last
    // terminal also disables only the first-time auto-spawn for this workspace
    // so a reload does not recreate a terminal the user just removed.
    if (!workspaceId) { termClose(); return; }
    if (!_termIsScopeActive(workspaceId)) return;
    document.body.classList.add('term-open');
    // Restore the user's last-known collapse state for this view
    // (default = visible for workspaces).
    _termApplyRememberedVisibility();

    // Warm switch: this workspace has been opened earlier in the browser
    // session, so we have its pill list in memory. Paint it instantly
    // and attach the cached session — no network wait, no respawn
    // detour. Background-refresh reconciles via termRefreshSessions
    // and the periodic poller; if a Claude died meanwhile its pill
    // shows up `dead` (click to retry). Avoids the multi-second
    // "resuming N session(s)…" wait that fired on every tab click.
    const sessionCacheKey = typeof _termSessionsKey === 'function'
      ? _termSessionsKey(workspaceId) : workspaceId;
    const isWarmSwitch = _termSessionsCache.has(sessionCacheKey);
    if (isWarmSwitch) {
      termSessions = _termSessionsCache.get(sessionCacheKey) || [];
      termRenderSessionList();
      if (termSessions.length > 0) {
        const pick = _termPickRestoreName(workspaceId);
        if (pick && _termHasOpenCachedPane(workspaceId, pick)) {
          termAttach(pick, workspaceId);
          termRefreshSessions(workspaceId);  // background reconcile, no await
        } else {
          console.info('[term] warm cache stale; reconciling before attach', workspaceId, pick);
          _termClientLog('info', 'terminal warm cache stale; reconciling before attach', {
            event_type: 'term.restore.stale_cache',
            target: workspaceId,
          });
          await _termRestoreSessionsForWorkspace(workspaceId);
        }
      } else {
        termDetach();
        termShowEmpty();
        termSetStatus('idle', 'no session — click + New');
        termRefreshSessions(workspaceId);  // background reconcile, no await
      }
      termStartPeriodicRefresh();
      return;
    }

    // Cold open (first visit to this workspace this browser session). Full
    // restore path: pull saved sessions out of workspace.json and respawn
    // any that aren't live in tmux. This is the path that surfaces saved
    // Claude conversations after a browser reload.
    await _termRestoreSessionsForWorkspace(workspaceId);
    // Keep the dropdown + current attachment honest when sessions change out
    // from under us (manual `tmux kill-session`, server restart, etc.).
    termStartPeriodicRefresh();
  }

  function _termHasOpenCachedPane(workspaceId, name) {
    if (typeof _termCache === 'undefined' || typeof _termCacheKey !== 'function') return false;
    const cached = _termCache.get(_termCacheKey(workspaceId, name));
    return _termCachedPaneIsFresh(cached);
  }

  async function _termTryWarmOpen(workspaceId) {
    const sessionCacheKey = typeof _termSessionsKey === 'function'
      ? _termSessionsKey(workspaceId) : workspaceId;
    if (!_termSessionsCache.has(sessionCacheKey)) return false;
    termSessions = _termSessionsCache.get(sessionCacheKey) || [];
    termRenderSessionList();
    if (termSessions.length > 0) {
      const pick = _termPickRestoreName(workspaceId);
      if (pick && _termHasOpenCachedPane(workspaceId, pick)) {
        termAttach(pick, workspaceId);
        _termRefreshSessionsForWorkspaceId(workspaceId);  // background reconcile
      } else {
        console.info('[term] warm cache stale; reconciling before attach', workspaceId, pick);
        _termClientLog('info', 'terminal warm cache stale; reconciling before attach', {
          event_type: 'term.restore.stale_cache',
          target: workspaceId,
        });
        await _termRestoreSessionsForWorkspace(workspaceId);
      }
    } else {
      termDetach();
      termShowEmpty();
      termSetStatus('idle', 'no session — click + New');
      _termRefreshSessionsForWorkspaceId(workspaceId);  // background reconcile
    }
    return true;
  }

  async function _termRefreshSessionsForWorkspaceId(workspaceId) {
    // Returns true when the sessions fetch succeeded (server reachable);
    // callers use this to tell "session confirmed gone" apart from
    // "couldn't ask".
    if (workspaceId === '__cerebro__' || workspaceId === '__self__' || workspaceId === '__logs__') {
      return await termRefreshSessionsByWorkspaceId(workspaceId);
    }
    return await termRefreshSessions(workspaceId);
  }

  function _termClientLog(level, msg, extra = {}) {
    try {
      const event = {
        level,
        msg,
        path: location.pathname + location.search + location.hash,
        ...extra,
      };
      fetch('/api/log/client', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({events: [event]}),
        keepalive: true,
      }).catch(() => {});
    } catch {}
  }

  async function _termRestoreSessionsForWorkspace(workspaceId) {
    const vaultId = typeof _termVaultId === 'function' ? _termVaultId() : null;
    const vaultQuery = typeof _vaultQuery === 'function' ? _vaultQuery(vaultId) : '';
    await _termRefreshSessionsForWorkspaceId(workspaceId);
    if (!_termIsScopeActive(workspaceId)) return;

    let saved = [];
    try {
      const r = await fetch('/api/term/sessions/saved?workspace_id=' + encodeURIComponent(workspaceId) + vaultQuery);
      if (r.ok) saved = await r.json();
    } catch (e) {
      _termClientLog('warning', 'terminal saved-session fetch failed', {
        event_type: 'term.restore.saved_fetch_failed',
        target: workspaceId,
      });
    }
    if (!_termIsScopeActive(workspaceId)) return;

    const liveLogicalNames = new Set(termSessions.map(s => s.logical_name).filter(Boolean));
    // Attached tmux aliases deliberately do not respawn as ordinary shell
    // sessions if the source/alias later disappears. The user can paste the
    // source name again from + New when they want to reattach it.
    const toRestore = saved.filter(s =>
      s && s.name && s.kind !== 'attached' && !liveLogicalNames.has(s.name)
    );
    const globalAutoSpawn = localStorage.getItem('labTermAutoSpawn') !== '0';
    const workspaceAutoSpawn = globalAutoSpawn && await termAutoSpawnEnabled(workspaceId, vaultId);
    if (!_termIsScopeActive(workspaceId)) return;
    if (_termKillAllPending.has(_termSessionsKey(workspaceId, vaultId))
        || _termCloseTabsPending.has(_termSessionsKey(workspaceId, vaultId))) return;

    if (toRestore.length > 0 && globalAutoSpawn) {
      termSetStatus('idle', `resuming ${toRestore.length} session(s)…`);
      _termClientLog('info', 'terminal restoring saved sessions', {
        event_type: 'term.restore.saved',
        target: workspaceId,
      });
      await Promise.all(toRestore.map(s => fetch('/api/term/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace_id: workspaceId,
          vault: vaultId,
          kind: s.kind || 'claude',
          agent: s.agent,
          name: s.name,
          // No explicit `auto`: the vault's per-agent autopilot
          // setting decides (an explicit value here would override it).
        }),
      }).catch(() => null)));
      await _termRefreshSessionsForWorkspaceId(workspaceId);
      if (!_termIsScopeActive(workspaceId)) return;
    }

    if (termSessions.length > 0) {
      const pick = _termPickRestoreName(workspaceId);
      if (pick) termAttach(pick, workspaceId);
      return;
    }

    termDetach();
    termShowEmpty();
    if (workspaceAutoSpawn) {
      termSetStatus('idle', 'auto-spawning claude…');
      await termSpawnSession('claude', { startFresh: false });
    } else {
      termSetStatus('idle', 'no session — click + New');
    }
  }

  function termStartPeriodicRefresh() {
    if (termRefreshTimer) return;
    termRefreshTimer = setInterval(async () => {
      if (!document.body.classList.contains('term-open')) {
        termStopPeriodicRefresh();
        return;
      }
      // Skip a tick if a reorder is still writing — otherwise the GET can
      // beat the POST and stomp the user's fresh drop.
      if (_termReorderPending) return;
      // Framework views win over a stale currentWorkspace from the previous
      // tab. Otherwise, use the loaded workspace or vault id.
      const pid = _termActiveWorkspaceId();
      if (!pid) return;
      const prev = termCurrentSession;
      const prevPid = termCurrentWorkspaceId;
      const ok = await _termRefreshSessionsForWorkspaceId(pid);
      // Attached session disappeared from tmux (confirmed by a successful
      // fetch, not a blip) → restore it automatically.
      if (prev && ok && prevPid === pid && !termSessions.some(s => s.name === prev)) {
        _termSessionGone(prev, pid);
      }
    }, 8000);
  }

  function termStopPeriodicRefresh() {
    if (termRefreshTimer) { clearInterval(termRefreshTimer); termRefreshTimer = null; }
  }

  function termClose() {
    document.body.classList.remove('term-open');
    document.body.classList.remove('term-collapsed');
    termStopPeriodicRefresh();
    // Soft-park the active session (preserves WS+xterm in cache) so that
    // toggling the panel back open doesn't trigger a fresh reconnect.
    termDetach(true);
  }

  function termShowRecovery() {
    // Overlay when the session vanished; click to spawn a fresh one.
    const body = document.getElementById('termBody');
    if (!body) return;
    // Hide all per-session containers; show the recovery overlay.
    _termHidePanesExcept(null);
    let el = document.getElementById('termEmpty');
    if (!el) {
      el = document.createElement('div');
      el.id = 'termEmpty';
      el.className = 'term-empty';
      body.appendChild(el);
    }
    // Rarely shown: disconnects auto-reconnect and confirmed-gone sessions
    // auto-restore (_termSessionGone). This overlay is the crash-loop
    // fallback, so "retry" is the primary action — creating a NEW session
    // is deliberately the quiet secondary one (accidental clicks used to
    // spawn unwanted fresh sessions).
    el.innerHTML = `
      <p style="margin-bottom:12px">This session ended and couldn't be restored automatically.</p>
      <button onclick="termReconnectOrRefresh()" style="background:var(--accent);color:#fff;border:none;border-radius:4px;padding:6px 12px;font-size:12px;cursor:pointer;margin-right:8px">Try restoring again</button>
      <button onclick="termCreateNew('claude')" style="background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:6px 12px;font-size:12px;cursor:pointer;margin-right:8px">Start fresh Claude</button>
      <button onclick="termCreateNew('terminal')" style="background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:6px 12px;font-size:12px;cursor:pointer">New terminal</button>`;
    el.style.display = '';
    termXterm = null;
    termFitAddon = null;
  }

  async function termReconnectOrRefresh() {
    const pid = _termActiveWorkspaceId();
    if (!pid) return;
    // User asked to retry — clear any dead/backoff state so termAttach
    // will make a fresh attempt instead of bouncing off _termMarkDead.
    termDeadSessions.clear();
    for (const k of Object.keys(termReconnectAttempts)) delete termReconnectAttempts[k];
    for (const k of Object.keys(_termAutoRestoreAt)) delete _termAutoRestoreAt[k];
    await _termRefreshSessionsForWorkspaceId(pid);
    if (!_termIsScopeActive(pid)) return;
    if (termSessions.length > 0) termAttach(termSessions[0].name, pid);
    else await _termRestoreSessionsForWorkspace(pid);
  }

  function termToggleCollapse() {
    document.body.classList.toggle('term-collapsed');
    const shown = !document.body.classList.contains('term-collapsed');
    _termRememberVisibility(_termVisibilityKey(), shown);
    if (shown && termXterm && termFitAddon) {
      setTimeout(() => { try { termFitAddon.fit(); termSendResize(); } catch {} }, 60);
    }
  }

  // Per-view persistence of "is the terminal panel collapsed?" so the
  // user's last toggle sticks across tab switches and reloads. The key
  // is namespaced by the active workspace, vault, or framework view.
  // (`_TERM_VIS_KEY_PREFIX` is declared higher up to avoid a TDZ when
  // these helpers run during the initial `?view=…` URL dispatch.)
  function _termVisibilityKey() {
    if (document.body.classList.contains('cerebro-active')) return _TERM_VIS_KEY_PREFIX + 'cerebro';
    if (_termHomeViewActive()) return _TERM_VIS_KEY_PREFIX + 'self';
    if (document.body.classList.contains('assistant-active')) return _TERM_VIS_KEY_PREFIX + 'assistant';
    if (currentWorkspace && currentWorkspace.is_workspace) return _TERM_VIS_KEY_PREFIX + 'workspace:' + currentWorkspace.name;
    return _TERM_VIS_KEY_PREFIX + 'unknown';
  }
  function _termRememberVisibility(key, shown) {
    try { localStorage.setItem(key, shown ? '1' : '0'); } catch {}
  }
  function _termRecallVisibility(key, defaultShown) {
    try {
      const v = localStorage.getItem(key);
      if (v === '1') return true;
      if (v === '0') return false;
    } catch {}
    return defaultShown;
  }
  // Apply the remembered (or default) visibility for the current view.
  function _termApplyRememberedVisibility() {
    const key = _termVisibilityKey();
    const shown = _termRecallVisibility(key, true);
    document.body.classList.toggle('term-collapsed', !shown);
    // The files sidebar piggy-backs on the same per-view entry point: every
    // view init (workspace / self / cerebro) lands here, so this is the one
    // place that restores the sidebar's per-view collapse state + width.
    _sidebarApplyForView();
  }

  // ─── Files-sidebar collapse + per-view width ───
  // Same UX as the terminal toggle, mirrored on the left edge. Both the
  // collapsed flag and the dragged width are namespaced by view (workspace
  // id / self / cerebro), so hiding or resizing the sidebar in one workspace
  // never leaks into another. The un-suffixed legacy key `labSidebarPct`
  // remains as the boot-time default for views without their own entry.
  // (The two key-prefix consts are hoisted next to _TERM_VIS_KEY_PREFIX —
  // same initial-dispatch TDZ rule.)
  function _sidebarViewSuffix() {
    if (document.body.classList.contains('cerebro-active')) return 'cerebro';
    if (document.body.classList.contains('self-active')) return 'self';
    if (document.body.classList.contains('assistant-active')) return 'assistant';
    if (document.body.classList.contains('vault-active')) return 'vault';
    if (currentWorkspace && currentWorkspace.is_workspace) {
      // Server (proxy) views get their own namespace so they can default
      // to a collapsed sidebar — the embedded app wants the full left +
      // center width — without touching the workspace's normal preference.
      if (typeof _workspaceDocPath === 'string' && _workspaceDocPath.startsWith('__proxy__/')) {
        return 'proxy:' + currentWorkspace.name + ':' + _workspaceDocPath.slice('__proxy__/'.length);
      }
      return 'workspace:' + currentWorkspace.name;
    }
    return 'unknown';
  }
  function sidebarToggleCollapse() {
    document.body.classList.toggle('sidebar-collapsed');
    const shown = !document.body.classList.contains('sidebar-collapsed');
    try { localStorage.setItem(_SIDEBAR_VIS_KEY_PREFIX + _sidebarViewSuffix(), shown ? '1' : '0'); } catch {}
  }
  function _sidebarApplyForView() {
    const sfx = _sidebarViewSuffix();
    // Server views start collapsed by default; everything else starts
    // shown. An explicit user toggle (stored '0'/'1') always wins.
    let shown = !sfx.startsWith('proxy:');
    try {
      const v = localStorage.getItem(_SIDEBAR_VIS_KEY_PREFIX + sfx);
      if (v === '0') shown = false; else if (v === '1') shown = true;
    } catch {}
    document.body.classList.toggle('sidebar-collapsed', !shown);
    let pct = NaN;
    try { pct = parseFloat(localStorage.getItem(_SIDEBAR_PCT_KEY_PREFIX + sfx)); } catch {}
    if (!Number.isFinite(pct) || pct <= 0) {
      try { pct = parseFloat(localStorage.getItem('labSidebarPct')); } catch {}
    }
    if (Number.isFinite(pct) && pct > 0) {
      document.documentElement.style.setProperty('--sidebar-width', pct + '%');
    } else {
      // No width saved for this view (nor a legacy global): clear any
      // inline value left over from the previous view so this one falls
      // back to the stylesheet default instead of inheriting a neighbor's
      // drag.
      document.documentElement.style.removeProperty('--sidebar-width');
    }
  }

  // Percentage-based resize of the two vertical dividers between the
  // three columns [sidebar | main (doc + comments) | terminal]. Both
  // --sidebar-width and --term-width are stored as CSS percentages so
  // the layout fills 100% of the viewport by default and each column
  // scales proportionally on window resize. Pixel mins enforced during
  // drag protect readability.
  (function initColumnResize() {
    const SIDEBAR_KEY = 'labSidebarPct';
    const TERM_KEY = 'labTermPct';
    const MIN_SIDEBAR_PX = 150;
    const MIN_MAIN_PX = 320;
    const MIN_TERM_PX = 280;
    const root = document.documentElement;
    const vw = () => window.innerWidth || 1;
    const pxToPct = (px) => (px / vw()) * 100;
    const setSidebarPct = (pct) => root.style.setProperty('--sidebar-width', pct + '%');
    const setTermPct = (pct) => root.style.setProperty('--term-width', pct + '%');
    const readPct = (varName, fallback) => {
      const raw = getComputedStyle(root).getPropertyValue(varName).trim();
      if (raw.endsWith('%')) return parseFloat(raw);
      if (raw.endsWith('px')) return pxToPct(parseFloat(raw));
      return fallback;
    };
    const currentSidebarPct = () => readPct('--sidebar-width', 10);
    const currentTermPct = () => readPct('--term-width', 40);
    const refit = () => { if (termXterm && termFitAddon) { try { termFitAddon.fit(); } catch {} } };

    // Restore saved percentages (ignore stale px-keyed values from before
    // this refactor — they'd produce wildly wrong widths).
    const savedSidebar = parseFloat(localStorage.getItem(SIDEBAR_KEY));
    if (Number.isFinite(savedSidebar) && savedSidebar > 0) setSidebarPct(savedSidebar);
    const savedTerm = parseFloat(localStorage.getItem(TERM_KEY));
    if (Number.isFinite(savedTerm) && savedTerm > 0) setTermPct(savedTerm);

    const wire = (resizerId, dragClass, onDrag, onDrop) => {
      const resizer = document.getElementById(resizerId);
      if (!resizer) return;
      let dragging = false;
      let startX = 0;
      let startSidebar = 0;
      let startTerm = 0;
      resizer.addEventListener('mousedown', (e) => {
        dragging = true;
        startX = e.clientX;
        startSidebar = currentSidebarPct();
        startTerm = currentTermPct();
        document.body.classList.add(dragClass);
        resizer.classList.add('dragging');
        e.preventDefault();
      });
      document.addEventListener('mousemove', (e) => {
        if (!dragging) return;
        onDrag(e.clientX - startX, startSidebar, startTerm);
        refit();
      });
      document.addEventListener('mouseup', () => {
        if (!dragging) return;
        dragging = false;
        document.body.classList.remove(dragClass);
        resizer.classList.remove('dragging');
        onDrop();
        refit();
        if (typeof termSendResize === 'function') termSendResize();
      });
    };

    // Sidebar/main divider: dragging right grows the sidebar. The width is
    // saved under the active view's key ONLY (per-workspace by request) —
    // the legacy global key is read as a fallback default but never
    // written anymore, so resizing workspace A can't restyle workspace B.
    wire('sidebarResizer', 'sidebar-resizing', (dx, startSidebar /*, startTerm*/) => {
      const nextPx = Math.max(MIN_SIDEBAR_PX, (startSidebar * vw() / 100) + dx);
      const termPx = currentTermPct() * vw() / 100;
      const maxPx = vw() - termPx - MIN_MAIN_PX;
      const clamped = Math.min(nextPx, Math.max(MIN_SIDEBAR_PX, maxPx));
      setSidebarPct(pxToPct(clamped));
    }, () => {
      try {
        localStorage.setItem(_SIDEBAR_PCT_KEY_PREFIX + _sidebarViewSuffix(),
                             String(currentSidebarPct()));
      } catch {}
    });

    // Main/terminal divider: dragging left grows the terminal.
    wire('termResizer', 'term-resizing', (dx, _startSidebar, startTerm) => {
      const nextPx = Math.max(MIN_TERM_PX, (startTerm * vw() / 100) - dx);
      const sidebarPx = currentSidebarPct() * vw() / 100;
      const maxPx = vw() - sidebarPx - MIN_MAIN_PX;
      const clamped = Math.min(nextPx, Math.max(MIN_TERM_PX, maxPx));
      setTermPct(pxToPct(clamped));
    }, () => localStorage.setItem(TERM_KEY, String(currentTermPct())));

    // Window resize: percentages already re-resolve against the viewport,
    // but if the user shrinks past the pixel minimums we rebalance so no
    // column collapses below its readability threshold.
    window.addEventListener('resize', () => {
      const sbPx = currentSidebarPct() * vw() / 100;
      const trPx = currentTermPct() * vw() / 100;
      if (sbPx < MIN_SIDEBAR_PX) setSidebarPct(pxToPct(MIN_SIDEBAR_PX));
      if (trPx < MIN_TERM_PX) setTermPct(pxToPct(MIN_TERM_PX));
      refit();
      if (typeof termSendResize === 'function') termSendResize();
    });
  })();

  async function termRefreshSessions(workspaceId) {
    workspaceId = workspaceId || _termActiveWorkspaceId();
    if (!workspaceId) return;
    const vaultId = _termVaultId();
    const sessionCacheKey = _termSessionsKey(workspaceId, vaultId);
    let fresh = [];
    let ok = false;
    try {
      const r = await fetch('/api/term/sessions?workspace_id=' + encodeURIComponent(workspaceId) + _vaultQuery(vaultId));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(sessionCacheKey, fresh);
    // Stale-response guard. termOpenForWorkspace's warm-switch path fires
    // this refresh without awaiting, so by the time the response lands
    // the user may already be on a different tab. Cache the result but
    // don't touch globals or repaint — the active view's own refresh
    // will handle its own pills.
    if (workspaceId !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return ok;
    // On a failed fetch (server restarting, network blip) fall back to the
    // last successful list for this workspace instead of wiping the pills —
    // the tmux sessions are almost certainly still alive, and the reconnect
    // loop needs their names to keep retrying.
    termSessions = ok ? fresh : (_termSessionsCache.get(sessionCacheKey) || []);
    if (ok) {
      // Any name that's no longer in the live list is genuinely gone —
      // don't keep its dead/backoff bookkeeping around. If tmux later
      // spawns a new session with the same name, we'll treat it fresh.
      const live = new Set(termSessions.map(s => s.name));
      for (const n of Array.from(termDeadSessions)) {
        if (!live.has(n)) termDeadSessions.delete(n);
      }
      for (const n of Object.keys(termReconnectAttempts)) {
        if (!live.has(n)) delete termReconnectAttempts[n];
      }
    }
    termRenderSessionList();
    return ok;
  }

  let _termDragState = null;
  let _termDragLogical = null;    // logical_name of pill being dragged
  let _termReorderPending = false; // suspends periodic refresh right after a reorder
  let _termGroupMenuOutside = null;

  function _termGroupScopeKey() {
    return _termSessionsKey(_termActiveWorkspaceId(), _termVaultId());
  }

  let _termTabSelectionScope = null;
  const _termSelectedTabs = new Set();

  function _termTabSelection() {
    const scope = _termGroupScopeKey();
    if (_termTabSelectionScope !== scope) {
      _termSelectedTabs.clear();
      _termTabSelectionScope = scope;
    }
    const live = new Set((termSessions || []).map(session => session.name));
    for (const name of _termSelectedTabs) {
      if (!live.has(name)) _termSelectedTabs.delete(name);
    }
    return _termSelectedTabs;
  }

  function _termSyncTabSelection() {
    const selected = _termTabSelection();
    document.getElementById('termSessionList')?.querySelectorAll('.sess').forEach(node => {
      const isSelected = selected.has(node.getAttribute('data-name'));
      node.classList.toggle('bulk-selected', isSelected);
      const description = isSelected
        ? 'Selected for bulk actions. Cmd-click or Ctrl-click to deselect.'
        : 'Cmd-click or Ctrl-click to select multiple terminals.';
      if (node.getAttribute('aria-description') !== description) node.setAttribute('aria-description', description);
    });
  }

  function _termSelectTab(name, toggle = false, contextMenu = false) {
    const selected = _termTabSelection();
    if (toggle) {
      // The mounted tab is the starting selection, just as in a file list.
      if (!selected.size && termCurrentWorkspaceId === _termActiveWorkspaceId()
          && termSessions.some(session => session.name === termCurrentSession)) {
        selected.add(termCurrentSession);
      }
      if (selected.has(name)) selected.delete(name);
      else selected.add(name);
    } else if (!contextMenu || !selected.has(name)) {
      selected.clear();
      if (name) selected.add(name);
    }
    _termSyncTabSelection();
  }

  function _termNormalizeGroupState(raw) {
    const groups = [];
    const seen = new Set();
    for (const candidate of (raw && Array.isArray(raw.groups) ? raw.groups : [])) {
      const id = String(candidate && candidate.id || '').slice(0, 80);
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const color = /^#[0-9a-f]{6}$/i.test(String(candidate.color || ''))
        ? String(candidate.color) : _TERM_GROUP_COLORS[groups.length % _TERM_GROUP_COLORS.length];
      groups.push({id, color});
    }
    const order = [];
    const seenTokens = new Set();
    for (const candidate of (raw && Array.isArray(raw.order) ? raw.order : [])) {
      const token = String(candidate || '').slice(0, 160);
      if (!/^[sg]:.+/.test(token) || seenTokens.has(token)) continue;
      seenTokens.add(token);
      order.push(token);
    }
    // Keep the old membership map only long enough to migrate the previous
    // container model into divider order on the next render.
    const membership = {};
    const validIds = new Set(groups.map(group => group.id));
    if (raw && raw.membership && typeof raw.membership === 'object') {
      Object.entries(raw.membership).forEach(([logical, groupId]) => {
        if (logical && validIds.has(groupId)) membership[String(logical)] = groupId;
      });
    }
    const tabGroups = [];
    for (const candidate of (Array.isArray(raw?.tabGroups) ? raw.tabGroups : [])) {
      const id = String(candidate?.id || '').slice(0, 80);
      if (!id || tabGroups.some(group => group.id === id)) continue;
      tabGroups.push({id, name: String(candidate.name || 'Group').slice(0, 80),
        color: /^#[0-9a-f]{6}$/i.test(candidate.color || '') ? candidate.color : _TERM_GROUP_COLORS[0],
        collapsed: candidate.collapsed === true});
    }
    const tabMembership = Object.fromEntries(Object.entries(raw?.tabMembership || {})
      .filter(([logical, id]) => logical && tabGroups.some(group => group.id === id)));
    return {groups, order, membership, tabGroups, tabMembership};
  }

  function _termReadGroupState() {
    try {
      const all = JSON.parse(localStorage.getItem(_TERM_GROUPS_KEY) || '{}');
      return _termNormalizeGroupState(all && all[_termGroupScopeKey()]);
    } catch { return _termNormalizeGroupState(null); }
  }

  function _termWriteGroupState(state) {
    try {
      let all = {};
      try { all = JSON.parse(localStorage.getItem(_TERM_GROUPS_KEY) || '{}') || {}; } catch {}
      all[_termGroupScopeKey()] = _termNormalizeGroupState(state);
      localStorage.setItem(_TERM_GROUPS_KEY, JSON.stringify(all));
    } catch {}
  }

  function _termSessionLogical(name) {
    const session = _termSessionMeta(name);
    return session && session.logical_name || '';
  }

  function _termReconcileGroupOrder(state) {
    const sessions = (termSessions || []).filter(session => session.logical_name);
    const validSessions = new Set(sessions.map(session => session.logical_name));
    const validGroups = new Set(state.groups.map(group => group.id));
    const order = [];
    const seen = new Set();
    const add = (token) => {
      if (seen.has(token)) return;
      const kind = token.slice(0, 2);
      const id = token.slice(2);
      if ((kind === 's:' && validSessions.has(id)) || (kind === 'g:' && validGroups.has(id))) {
        seen.add(token);
        order.push(token);
      }
    };

    if (state.order.length) {
      state.order.forEach(add);
    } else if (Object.keys(state.membership || {}).length) {
      // One-time migration: preserve the visible grouping from the old
      // explicit-membership UI, then let divider position own membership.
      const emittedGroups = new Set();
      sessions.forEach(session => {
        const logical = session.logical_name;
        const groupId = state.membership[logical];
        if (!groupId || !validGroups.has(groupId)) {
          add(`s:${logical}`);
          return;
        }
        if (emittedGroups.has(groupId)) return;
        emittedGroups.add(groupId);
        add(`g:${groupId}`);
        sessions
          .filter(item => state.membership[item.logical_name] === groupId)
          .forEach(item => add(`s:${item.logical_name}`));
      });
    }

    sessions.forEach(session => add(`s:${session.logical_name}`));
    state.groups.forEach(group => add(`g:${group.id}`));
    return order;
  }

  function termCreateDivider(sessionName = termCurrentSession, position = 'before') {
    const logical = _termSessionLogical(sessionName);
    const state = _termReadGroupState();
    const id = `g-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    state.groups.push({
      id,
      color: _TERM_GROUP_COLORS[state.groups.length % _TERM_GROUP_COLORS.length],
    });
    const order = _termReconcileGroupOrder(state).filter(token => token !== `g:${id}`);
    const activeToken = logical ? `s:${logical}` : '';
    const activeIndex = activeToken ? order.indexOf(activeToken) : -1;
    order.splice(activeIndex >= 0 ? activeIndex + (position === 'after' ? 1 : 0) : order.length, 0, `g:${id}`);
    state.order = order;
    state.membership = {};
    _termWriteGroupState(state);
    termCloseGroupMenu();
    termRenderSessionList();
  }

  function termSetDividerColor(groupId, color) {
    if (!/^#[0-9a-f]{6}$/i.test(String(color || ''))) return;
    const state = _termReadGroupState();
    const group = state.groups.find(item => item.id === groupId);
    if (!group) return;
    group.color = color;
    _termWriteGroupState(state);
    termCloseGroupMenu();
    termRenderSessionList();
  }

  function termDeleteDivider(groupId) {
    const state = _termReadGroupState();
    state.groups = state.groups.filter(group => group.id !== groupId);
    state.order = _termReconcileGroupOrder(state).filter(token => token !== `g:${groupId}`);
    state.membership = {};
    _termWriteGroupState(state);
    termCloseGroupMenu();
    termRenderSessionList();
  }

  function termCloseGroupMenu() {
    const menu = document.getElementById('termGroupMenu');
    if (menu) menu.hidden = true;
    if (_termGroupMenuOutside) {
      document.removeEventListener('pointerdown', _termGroupMenuOutside);
      _termGroupMenuOutside = null;
    }
  }

  function _termShowGroupMenu(anchor, html, onAction) {
    const menu = document.getElementById('termGroupMenu');
    if (!menu || !anchor) return;
    termCloseGroupMenu();
    const scope = _termGroupScopeKey();
    menu.innerHTML = html;
    menu.hidden = false;
    menu.onkeydown = event => {
      if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...menu.querySelectorAll('[data-action]')];
      const index = buttons.indexOf(document.activeElement);
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (index + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length;
      buttons[next]?.focus();
    };
    menu.querySelectorAll('[data-action]').forEach(button => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (scope !== _termGroupScopeKey()) { termCloseGroupMenu(); return; }
        onAction(button.getAttribute('data-action'), button);
      });
    });
    menu.querySelector('[data-action]')?.focus();
    const rect = anchor.getBoundingClientRect();
    const bounds = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - bounds.width - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(rect.bottom + 5, window.innerHeight - bounds.height - 8))}px`;
    _termGroupMenuOutside = (event) => {
      if (!menu.contains(event.target) && !event.target.closest('[data-term-group-trigger]')) {
        termCloseGroupMenu();
      }
    };
    setTimeout(() => {
      if (_termGroupMenuOutside) document.addEventListener('pointerdown', _termGroupMenuOutside);
    }, 0);
  }

  function termOpenDividerOptions(groupId, anchor) {
    const state = _termReadGroupState();
    const group = state.groups.find(item => item.id === groupId);
    if (!group) return;
    const colors = _TERM_GROUP_COLORS.map(color => `
      <button type="button" class="term-group-color${color === group.color ? ' selected' : ''}" style="--term-group-color:${color}" data-action="color:${color}" aria-label="Use ${color}"></button>`).join('');
    _termShowGroupMenu(anchor, `
      <div class="term-group-menu-title">Divider color</div>
      <div class="term-group-colors">${colors}</div>
      <button type="button" class="term-group-menu-row danger" data-action="delete">Delete divider</button>`, (action) => {
        if (action === 'delete') termDeleteDivider(groupId);
        else if (action.startsWith('color:')) termSetDividerColor(groupId, action.slice(6));
      });
  }

  const _TERM_NEW_OPTIONS = ['claude', 'codex', 'copilot', 'terminal', 'attach'];
  const _TERM_NEW_OPTIONS_KEY = 'labTermNewOptions-v1:';

  function _termReadNewOptions(scope = _termGroupScopeKey()) {
    try {
      const saved = JSON.parse(localStorage.getItem(_TERM_NEW_OPTIONS_KEY + scope));
      if (Array.isArray(saved)) return _TERM_NEW_OPTIONS.filter(option => saved.includes(option));
    } catch {}
    return [..._TERM_NEW_OPTIONS];
  }

  function _termRenderNewOptionsSettings() {
    const container = document.getElementById('termNewOptions');
    if (!container) return;
    container.dataset.scope = _termGroupScopeKey();
    const enabled = new Set(_termReadNewOptions(container.dataset.scope));
    container.querySelectorAll('input').forEach(input => { input.checked = enabled.has(input.value); });
  }

  function termSetNewOption(option, enabled) {
    if (!_TERM_NEW_OPTIONS.includes(option)) return;
    const scope = document.getElementById('termNewOptions')?.dataset.scope || _termGroupScopeKey();
    const selected = new Set(_termReadNewOptions(scope));
    if (enabled) selected.add(option);
    else selected.delete(option);
    try { localStorage.setItem(_TERM_NEW_OPTIONS_KEY + scope, JSON.stringify([...selected])); } catch {}
    if (scope === _termGroupScopeKey()) _termApplyNewOptions(document.getElementById('termNewPicker'), scope);
  }

  function _termApplyNewOptions(picker, scope = _termGroupScopeKey()) {
    if (!picker) return;
    const enabled = new Set(_termReadNewOptions(scope));
    let visible = 0;
    picker.querySelectorAll('[data-term-option]').forEach(button => {
      button.hidden = !enabled.has(button.dataset.termOption) || button.dataset.vaultHidden === 'true';
      if (!button.hidden) visible += 1;
    });
    const empty = document.getElementById('termNewOptionsEmpty');
    if (empty) empty.hidden = visible > 0;
  }

  function _termNewButtonHtml() {
    return '<button id="termNewBtn" class="term-new-tab" onclick="termToggleNewPicker(event)" title="New terminal tab" aria-label="New terminal tab"><span aria-hidden="true">＋</span><span class="term-new-label"> New</span></button>';
  }

  function termAssignTabGroup(sessionName, groupId) {
    const names = Array.isArray(sessionName) ? sessionName : [sessionName];
    const logicals = new Set(names.map(_termSessionLogical).filter(Boolean));
    if (!logicals.size) return;
    const state = _termReadGroupState();
    if (groupId === 'new') {
      const name = prompt('Group name', 'New group');
      if (!name?.trim()) return;
      groupId = `tabs-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
      state.tabGroups.push({id: groupId, name: name.trim().slice(0, 80),
        color: _TERM_GROUP_COLORS[state.tabGroups.length % _TERM_GROUP_COLORS.length], collapsed: false});
    }
    if (groupId && !state.tabGroups.some(group => group.id === groupId)) return;
    for (const logical of logicals) {
      if (groupId) state.tabMembership[logical] = groupId;
      else delete state.tabMembership[logical];
    }
    // Keep members adjacent in the underlying drag order too.
    const current = _termReconcileGroupOrder(state);
    const moving = current.filter(token => token.startsWith('s:') && logicals.has(token.slice(2)));
    const originalIndex = current.indexOf(moving[0]);
    const order = current.filter(token => !moving.includes(token));
    const peers = order.filter(token => token.startsWith('s:') && state.tabMembership[token.slice(2)] === groupId);
    const index = groupId ? (peers.length ? order.indexOf(peers[peers.length - 1]) + 1 : Math.max(0, originalIndex)) : order.length;
    order.splice(index, 0, ...moving);
    state.order = order;
    _termWriteGroupState(state);
    termCloseGroupMenu();
    termRenderSessionList();
  }

  function termUpdateTabGroup(groupId, action) {
    const state = _termReadGroupState();
    const group = state.tabGroups.find(item => item.id === groupId);
    if (!group) return;
    if (action === 'toggle') group.collapsed = !group.collapsed;
    else if (action === 'rename') {
      const name = prompt('Group name', group.name);
      if (!name?.trim()) return;
      group.name = name.trim().slice(0, 80);
    } else if (action.startsWith('color:')) {
      const color = action.slice(6);
      if (!/^#[0-9a-f]{6}$/i.test(color)) return;
      group.color = color;
    } else if (action === 'ungroup') {
      state.tabGroups = state.tabGroups.filter(item => item.id !== groupId);
      state.tabMembership = Object.fromEntries(Object.entries(state.tabMembership).filter(([, id]) => id !== groupId));
    }
    _termWriteGroupState(state);
    termCloseGroupMenu();
    termRenderSessionList();
  }

  function termOpenTabMenu(sessionName, anchor) {
    _termSelectTab(sessionName, false, true);
    const names = [..._termTabSelection()];
    if (names.length > 1) {
      termOpenSelectedTabsMenu(names, anchor);
      return;
    }
    const state = _termReadGroupState();
    const logical = _termSessionLogical(sessionName);
    const membership = state.tabMembership[logical];
    const horizontal = termSessionOrientation === 'horizontal';
    const session = (termSessions || []).find(item => item.name === sessionName);
    const row = (action, label, danger = false) => `<button role="menuitem" class="term-group-menu-row${danger ? ' danger' : ''}" data-action="${termSessEsc(action)}">${termSessEsc(label)}</button>`;
    _termShowGroupMenu(anchor,
      row('rename', 'Rename tab…') +
      (_termActiveWorkspaceId() === '__self__' ? '<hr><div class="term-group-menu-title">Associate with</div>' +
        _termHomeAssociationOptions().map(item => row('associate:' + item.id,
          (_termHomeAssociation(session) === item.id ? '✓ ' : '') + item.name)).join('') + '<hr>' : '') +
      (session?.linked_file ? row('unlink-file', 'Unlink from file') : '') +
      (session?.linked_scope ? row('unlink-scope', 'Unlink from folder/worktree') : '') +
      row('new', 'Add to new group…') +
      state.tabGroups.filter(group => group.id !== membership).map(group => row(`group:${group.id}`, `Move to ${group.name}`)).join('') +
      (membership ? row('ungroup', 'Remove from group') : '') + '<hr>' +
      row('before', `Add divider ${horizontal ? 'before' : 'above'}`) + row('after', `Add divider ${horizontal ? 'after' : 'below'}`) + '<hr>' +
      row('close', 'Close tab', true) + (membership ? row('close-group', 'Close group…', true) : ''), action => {
        termCloseGroupMenu();
        if (action === 'rename') termRenameSession(sessionName);
        else if (action.startsWith('associate:')) {
          _termSaveHomeAssociation(logical, action.slice(10));
          termRenderSessionList();
        }
        else if (action === 'unlink-file') void termUnlinkTarget(sessionName, 'file');
        else if (action === 'unlink-scope') void termUnlinkTarget(sessionName, 'scope');
        else if (action === 'new') termAssignTabGroup(sessionName, 'new');
        else if (action.startsWith('group:')) termAssignTabGroup(sessionName, action.slice(6));
        else if (action === 'ungroup') termAssignTabGroup(sessionName, null);
        else if (action === 'before' || action === 'after') termCreateDivider(sessionName, action);
        else if (action === 'close') void termCloseTabs([sessionName]);
        else if (action === 'close-group') void termCloseTabGroup(membership);
      });
  }

  function termOpenSelectedTabsMenu(names, anchor) {
    const sessions = (termSessions || []).filter(session => names.includes(session.name));
    const state = _termReadGroupState();
    const row = (action, label, danger = false) => `<button role="menuitem" class="term-group-menu-row${danger ? ' danger' : ''}" data-action="${termSessEsc(action)}">${termSessEsc(label)}</button>`;
    _termShowGroupMenu(anchor,
      `<div class="term-group-menu-title">${sessions.length} terminals selected</div>` +
      (_termActiveWorkspaceId() === '__self__' ? '<div class="term-group-menu-title">Associate with</div>' +
        _termHomeAssociationOptions().map(item => row('associate:' + item.id,
          (sessions.every(session => _termHomeAssociation(session) === item.id) ? '✓ ' : '') + item.name)).join('') + '<hr>' : '') +
      (sessions.some(session => session.linked_file) ? row('unlink-file', 'Unlink from files') : '') +
      (sessions.some(session => session.linked_scope) ? row('unlink-scope', 'Unlink from folders/worktrees') : '') +
      row('new', 'Add to new group…') +
      state.tabGroups.filter(group => !sessions.every(session => state.tabMembership[session.logical_name] === group.id))
        .map(group => row(`group:${group.id}`, `Move to ${group.name}`)).join('') +
      (sessions.some(session => state.tabMembership[session.logical_name]) ? row('ungroup', 'Remove from groups') : '') +
      '<hr>' + row('clear', 'Clear selection') + row('close', `Close ${sessions.length} tabs…`, true), action => {
        termCloseGroupMenu();
        if (action.startsWith('associate:')) {
          for (const session of sessions) _termSaveHomeAssociation(session.logical_name, action.slice(10));
          termRenderSessionList();
        } else if (action === 'new') termAssignTabGroup(names, 'new');
        else if (action.startsWith('group:')) termAssignTabGroup(names, action.slice(6));
        else if (action === 'ungroup') termAssignTabGroup(names, null);
        else if (action === 'unlink-file') void termUnlinkTabs(sessions, 'file');
        else if (action === 'unlink-scope') void termUnlinkTabs(sessions, 'scope');
        else if (action === 'clear') _termSelectTab(null);
        else if (action === 'close') void termCloseTabs(names);
      });
  }

  async function termUnlinkTabs(sessions, kind) {
    const context = _termLinkContext();
    const failures = [];
    for (const session of sessions) {
      if (!(kind === 'file' ? session.linked_file : session.linked_scope)) continue;
      const patch = kind === 'file' ? {linked_file: null} : {linked_scope: null};
      if (kind === 'file' && session.label === _termLinkedFileName(session.linked_file?.path)) patch.label = null;
      try { await _termPatchLinks(session, patch, context); }
      catch (error) { failures.push(`${_termSessionDisplay(session)}: ${error.message}`); }
    }
    if (failures.length) explorerToast('Could not remove all links: ' + failures.join('; '), true);
    else explorerToast('Terminal links removed.');
  }

  function termOpenTabGroupMenu(groupId, anchor) {
    const group = _termReadGroupState().tabGroups.find(item => item.id === groupId);
    if (!group) return;
    const colors = _TERM_GROUP_COLORS.map(color => `<button type="button" class="term-group-color${color === group.color ? ' selected' : ''}" style="--term-group-color:${color}" data-action="color:${color}" aria-label="Use ${color}"></button>`).join('');
    _termShowGroupMenu(anchor, `<div class="term-group-menu-title">${termSessEsc(group.name)}</div>
      <div class="term-group-colors">${colors}</div>
      <button role="menuitem" class="term-group-menu-row" data-action="rename">Rename group…</button>
      <button role="menuitem" class="term-group-menu-row" data-action="toggle">${group.collapsed ? 'Expand' : 'Collapse'} group</button>
      <button role="menuitem" class="term-group-menu-row" data-action="ungroup">Ungroup tabs</button>
      <hr><button role="menuitem" class="term-group-menu-row danger" data-action="close">Close group…</button>`, action => {
        if (action === 'close') { termCloseGroupMenu(); void termCloseTabGroup(groupId); }
        else termUpdateTabGroup(groupId, action);
      });
  }

  async function termCloseTabGroup(groupId) {
    const state = _termReadGroupState();
    const group = state.tabGroups.find(item => item.id === groupId);
    if (!group) return;
    const names = termSessions.filter(session => state.tabMembership[session.logical_name] === groupId).map(session => session.name);
    const scope = _termGroupScopeKey();
    if (await termCloseTabs(names, group.name) && scope === _termGroupScopeKey()) termUpdateTabGroup(groupId, 'ungroup');
  }

  const _termCloseTabsPending = new Set();
  async function termCloseTabs(names, groupName = '') {
    const workspaceId = _termActiveWorkspaceId(), vaultId = _termVaultId();
    const scope = _termSessionsKey(workspaceId, vaultId);
    if (!workspaceId || !names.length || _termCloseTabsPending.has(scope)) return false;
    names = [...new Set(names)];
    const label = groupName ? `group "${groupName}" (${names.length} tabs)`
      : names.length > 1 ? `${names.length} selected terminal tabs` : 'this terminal tab';
    if (!confirm(`Close ${label}? Running work will stop and closed tabs will stay closed after reload. External sessions will only be detached from Lab.`)) return false;
    const isActive = () => workspaceId === _termActiveWorkspaceId() && vaultId === _termVaultId();
    _termCloseTabsPending.add(scope);
    const failures = [];
    try {
      const setting = await fetch('/api/ui/term-autospawn', {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace_id: workspaceId, vault: vaultId, enabled: false})});
      if (!setting.ok) throw new Error('Could not disable automatic session spawning.');
      for (const name of names) {
        try {
          const response = await fetch('/api/term/sessions/' + encodeURIComponent(name) + '?purge=true' + _vaultQuery(vaultId), {method: 'DELETE'});
          if (!response.ok) {
            const result = await response.json().catch(() => ({}));
            throw new Error(result.detail || response.statusText || 'Request failed');
          }
          if (isActive() && termCurrentSession === name) termDetach();
          _termEvictCache(name, workspaceId);
        } catch (error) { failures.push(`${name}: ${error.message}`); }
      }
      _termSessionsCache.delete(scope);
      if (failures.length) throw new Error(failures.join('\n'));
      return true;
    } catch (error) {
      alert('Could not close all selected tabs: ' + error.message);
      return false;
    } finally {
      _termCloseTabsPending.delete(scope);
      if (isActive()) {
        await _termRefreshSessionsForWorkspaceId(workspaceId);
        if (isActive() && !termCurrentSession) {
          if (termSessions.length) termAttach(termSessions[0].name, workspaceId);
          else { termShowEmpty(); termSetStatus('idle', 'no session — click + New'); }
        }
      }
      if (typeof workspaceTabsRefresh === 'function') workspaceTabsRefresh();
    }
  }

  function _termSessionDisplay(s) {
    if (!s) return '';
    const manual = String(s.label || '').trim();
    const scope = s.linked_scope;
    const fileName = String(s.linked_file?.path || '').split('/').pop();
    // File linking previously saved the basename as the display label.
    // Keep explicit renames, while letting those automatic labels use the project.
    if (manual && !(scope && manual === fileName)) return manual;
    if (scope) {
      const project = String(scope.label || '').split(' · ')[0].trim();
      const folder = String(scope.project_root || scope.root || '').replace(/\/+$/, '').split('/').pop();
      if (project && project !== 'Root') return project;
      if (folder) return folder;
    }
    const requestCount = Array.isArray(s.agent_session_requests)
      ? s.agent_session_requests.filter(Boolean).length
      : 0;
    const agentSession = requestCount <= 1
      ? String(s.agent_session_name || '').trim()
      : '';
    return agentSession || s.logical_name || s.name || '';
  }

  function _termSessionRequests(s) {
    const saved = s && s.agent_session_requests;
    const requests = Array.isArray(saved)
      ? saved.map(value => String(value || '').trim()).filter(Boolean)
      : [];
    if (requests.length) return requests;
    if (_termSessionObjective(s)) return [];
    const fallback = String(s && (s.agent_session_summary || s.summary) || '').trim();
    return fallback ? [fallback] : [];
  }

  function _termSessionObjective(s) {
    return String(s && s.agent_session_objective || '').trim();
  }

  function _termSessionContext(s) {
    const objective = _termSessionObjective(s);
    if (objective) {
      return {label: 'Objective', items: [objective], isObjective: true};
    }
    return {label: 'Requests', items: _termSessionRequests(s), isObjective: false};
  }

  function _termContextRowsHtml(context) {
    return context.items.map(item => `
      <span class="term-context-row${context.isObjective ? ' objective' : ''}">
        ${context.isObjective ? '' : '<span class="term-context-bullet" aria-hidden="true">•</span>'}
        <span class="term-context-preview">${termSessEsc(item)}</span>
      </span>`).join('');
  }

  function _termPreviewRequests(requests) {
    const preview = [];
    let characters = 0;
    for (let i = requests.length - 1; i >= 0 && characters < 50; i--) {
      const text = String(requests[i] || '').trim();
      if (!text) continue;
      characters += Array.from(text).length + (preview.length ? 1 : 0);
      preview.unshift(text);
    }
    return preview;
  }

  function _termSessionIdentity(s) {
    const scope = s?.linked_scope;
    const basename = path => String(path || '').replace(/\/+$/, '').split('/').pop();
    const root = scope?.project_root || scope?.root || s?.cwd || '';
    const projectLabel = String(scope?.label || '').split(' · ')[0];
    const project = projectLabel && projectLabel !== 'Root' ? projectLabel : basename(root);
    const identity = [];
    if (project) identity.push({kind: 'project', text: project, title: `Project: ${root || project}`,
      color: scope ? _termScopeColor({...scope, worktree: null}) : 'var(--accent)'});
    if (scope) identity.push({kind: 'worktree',
      text: scope.worktree ? String(scope.label || '').split(' · ').slice(1).join(' · ') || basename(scope.worktree) : 'main',
      title: `Worktree: ${scope.worktree || scope.root || 'main'}`, color: _termScopeColor(scope)});
    const linked = String(s?.linked_file?.path || '').trim();
    if (linked) identity.push({kind: 'file', text: linked, title: `Linked file: ${linked}`, color: 'var(--accent)'});
    return identity;
  }

  function _termSessionIdentityHtml(identity) {
    return identity.map(part => {
      const color = /^#[0-9a-f]{6}$/i.test(part.color) ? part.color : 'var(--accent)';
      return `<span class="term-context-identity-part" style="color:${color}" title="${termSessEsc(part.title)}">${termSessEsc(part.text)}</span>`;
    }).join('<span class="term-context-identity-arrow" aria-hidden="true">→</span>');
  }

  function _termShowNewestContextItems(container, visibleCount) {
    if (!container) return;
    if (container.style) container.style.maxHeight = '';
    const rows = container.querySelectorAll
      ? Array.from(container.querySelectorAll('.term-context-row'))
      : [];
    if (rows.length > visibleCount && container.style) {
      const first = rows[rows.length - visibleCount];
      const last = rows[rows.length - 1];
      const height = (last.offsetTop + last.offsetHeight) - first.offsetTop;
      if (height > 0) container.style.maxHeight = `${Math.ceil(height)}px`;
    }
    container.scrollTop = container.scrollHeight;
  }

  function _termSessionSummary(s) {
    const context = _termSessionContext(s);
    return context.items.length ? context.items[context.items.length - 1] : '';
  }

  function _termSessionVisual(s) {
    const kind = (s && s.kind || '').toLowerCase();
    const agent = (s && s.agent || (kind === 'claude' ? 'claude' : '')).toLowerCase();
    return {
      kind,
      agent,
      badge: kind === 'claude' ? (agent || 'claude') : kind,
      icon: kind !== 'claude' ? '💻'
        : agent === 'codex' ? '🧠'
        : agent === 'copilot' ? '🐙'
        : '🤖',
      isClaude: agent === 'claude',
    };
  }

  function _termSessionTooltipPayload(s) {
    const identity = _termSessionIdentity(s);
    return JSON.stringify({items: _termPreviewRequests(_termSessionRequests(s)),
      ...(identity.length ? {identity} : {})});
  }

  async function termRenameSession(name) {
    const session = _termSessionMeta(name);
    if (!session) return;
    const workspaceId = _termActiveWorkspaceId();
    const vaultId = _termVaultId();
    const logical = session.logical_name || '';
    if (!workspaceId || !logical) return;
    const current = session.label || logical;
    const nextRaw = prompt('Rename terminal tab', current);
    if (nextRaw === null) return;
    const next = nextRaw.trim();
    try {
      const r = await fetch('/api/term/sessions/metadata', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace_id: workspaceId,
          vault: vaultId,
          name: logical,
          label: next || null,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || r.statusText || 'rename failed');
      if (workspaceId !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return;
      const updated = body.session || {};
      termSessions = (termSessions || []).map(s =>
        s.name === name ? {...s, label: updated.label || null, summary: updated.summary || s.summary} : s
      );
      _termSessionsCache.set(_termSessionsKey(workspaceId, vaultId), termSessions);
      termRenderSessionList();
      _termClientLog('info', 'terminal tab renamed', {
        event_type: 'term.session.rename',
        target: workspaceId,
      });
    } catch (e) {
      console.warn('[term] rename failed', e);
      termSetStatus('err', 'rename failed');
      _termClientLog('warning', 'terminal tab rename failed: ' + (e && e.message || e), {
        event_type: 'term.session.rename_failed',
        target: workspaceId,
      });
    }
  }

  function termRenameCurrent() {
    if (termCurrentSession) termRenameSession(termCurrentSession);
  }

  function _termRenderActiveSessionHeader() {
    const el = document.getElementById('termActiveSession');
    const statusSummary = document.getElementById('termStatusSummary');
    const statusSummaryLabel = document.getElementById('termStatusSummaryLabel');
    const statusSummaryText = document.getElementById('termStatusSummaryText');
    const statusIdentity = document.getElementById('termStatusIdentity');
    if (!el && !statusSummary) return;
    const session = (termSessions || []).find(s =>
      s.name === termCurrentSession && _termActiveWorkspaceId() === termCurrentWorkspaceId
    );
    if (!session) {
      if (el) {
        el.innerHTML = '';
        delete el._labHeaderHtml;
        el.removeAttribute('title');
        el.removeAttribute('data-tooltip');
        el.className = 'term-active-session';
      }
      if (statusSummary) {
        statusSummary.removeAttribute('title');
        statusSummary.hidden = true;
      }
      if (statusSummaryText) {
        statusSummaryText.textContent = '';
        if (statusSummaryText.dataset) delete statusSummaryText.dataset.contextKey;
      }
      if (statusIdentity) { statusIdentity.innerHTML = ''; statusIdentity.hidden = true; }
      if (statusSummaryLabel) statusSummaryLabel.textContent = 'Requests';
      return;
    }
    const display = _termSessionDisplay(session);
    const context = _termSessionContext(session);
    const summary = _termSessionSummary(session);
    const visual = _termSessionVisual(session);
    const linked = String(session.linked_file && session.linked_file.path || '').trim();
    if (el) {
      el.className = `term-active-session on ${visual.kind}`;
      el.setAttribute?.('data-tooltip', _termSessionTooltipPayload(session, ''));
      el.removeAttribute('title');
      const subline = summary
        ? `${context.label} · ${summary}`
        : (linked && !session.linked_scope ? `Linked · ${linked}` : '');
      const html = `<span aria-hidden="true">${visual.icon}</span><span class="term-active-session-copy"><span class="name">${termSessEsc(display)}</span>${subline ? `<span class="summary">${termSessEsc(subline)}</span>` : ''}</span>${_termHomeAssociationHtml(session)}<span class="agent">${termSessEsc(visual.badge)}</span>`;
      if (el._labHeaderHtml !== html) {
        el._labHeaderHtml = html;
        el.innerHTML = html;
      }
    }
    const identityHtml = _termSessionIdentityHtml(_termSessionIdentity(session));
    if (statusIdentity) {
      if (statusIdentity.innerHTML !== identityHtml) statusIdentity.innerHTML = identityHtml;
      statusIdentity.hidden = !identityHtml;
    }
    if (statusSummary) {
      statusSummary.removeAttribute('title');
      statusSummary.hidden = !context.items.length && !identityHtml;
    }
    if (statusSummaryLabel) statusSummaryLabel.textContent = context.label;
    if (statusSummaryText) {
      const contextKey = JSON.stringify([
        session.name, context.label, context.items,
      ]);
      if (
        !statusSummaryText.dataset
        || statusSummaryText.dataset.contextKey !== contextKey
      ) {
        statusSummaryText.innerHTML = _termContextRowsHtml(context);
        _termShowNewestContextItems(statusSummaryText, 3);
        if (statusSummaryText.dataset) {
          statusSummaryText.dataset.contextKey = contextKey;
        }
      }
    }
  }

  let _termSessionTooltipHideTimer = null;

  function _termCancelSessionTooltipHide() {
    if (_termSessionTooltipHideTimer !== null) {
      clearTimeout(_termSessionTooltipHideTimer);
      _termSessionTooltipHideTimer = null;
    }
  }

  function _termHideSessionTooltip() {
    _termCancelSessionTooltipHide();
    const tooltip = document.getElementById('termSessionTooltip');
    if (!tooltip) return;
    tooltip.hidden = true;
    tooltip.innerHTML = '';
  }

  function _termScheduleSessionTooltipHide() {
    _termCancelSessionTooltipHide();
    _termSessionTooltipHideTimer = setTimeout(_termHideSessionTooltip, 120);
  }

  function _termShowSessionTooltip(anchor) {
    if (_termDragState) { _termHideSessionTooltip(); return; }
    const tooltip = document.getElementById('termSessionTooltip');
    const raw = anchor && anchor.getAttribute('data-tooltip');
    if (!tooltip || !raw) {
      _termHideSessionTooltip();
      return;
    }
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch (_error) {
      payload = {label: 'Requests', items: [raw], isObjective: false, meta: []};
    }
    const items = Array.isArray(payload.items)
      ? payload.items.map(value => String(value || '').trim()).filter(Boolean)
      : [];
    const latest = _termPreviewRequests(items);
    const identityHtml = _termSessionIdentityHtml(Array.isArray(payload.identity) ? payload.identity : []);
    const anchorRect = anchor.getBoundingClientRect();
    const panel = anchor.closest?.('.term-panel');
    const boundary = panel ? panel.getBoundingClientRect().left : anchorRect.left;
    const gap = 8;
    const availableWidth = boundary - gap * 2;
    // Never flip above/below or into the terminal. A full-width terminal may
    // leave no usable space on the left; its selected header still has history.
    if ((!latest.length && !identityHtml) || availableWidth < 120) {
      _termHideSessionTooltip();
      return;
    }
    _termCancelSessionTooltipHide();
    if (!tooltip._termInteractive && tooltip.addEventListener) {
      tooltip.addEventListener('pointerenter', _termCancelSessionTooltipHide);
      tooltip.addEventListener('pointerleave', _termScheduleSessionTooltipHide);
      tooltip._termInteractive = true;
    }
    tooltip.innerHTML = `
      ${identityHtml ? `<div class="term-context-identity">${identityHtml}</div>` : ''}
      ${latest.length ? `<div class="term-session-tooltip-context">
        <div class="term-session-tooltip-label">${latest.length > 1 ? 'Latest requests' : 'Latest request'}</div>
        <div class="term-session-tooltip-items">${_termContextRowsHtml({items: latest, isObjective: true})}</div>
      </div>` : ''}`;
    tooltip.style.width = `${Math.min(420, availableWidth)}px`;
    tooltip.style.left = '0px';
    tooltip.style.top = '0px';
    tooltip.hidden = false;
    const tipRect = tooltip.getBoundingClientRect();
    tooltip.style.left = `${boundary - gap - tipRect.width}px`;
    tooltip.style.top = `${Math.max(gap, Math.min(
      anchorRect.top + (anchorRect.height - tipRect.height) / 2,
      window.innerHeight - tipRect.height - gap,
    ))}px`;
  }

  function _termSessionAssociationHtml(session) {
    if (_termActiveWorkspaceId() === '__self__') return _termHomeAssociationHtml(session);
    const scope = session.linked_scope;
    const config = scope ? (scope.config_scope === _sidebarFileConfigScope
      ? _sidebarFileConfig : _loadSidebarFileConfig(scope.config_scope)) : null;
    const folder = config?.folderScopes?.find(row => row.path === scope.project_root);
    const savedAlias = String(scope?.label || '').split(' · ')[0].trim();
    const alias = folder?.label || (savedAlias && savedAlias !== 'Root' ? savedAlias : 'main');
    const worktree = String(scope?.worktree || '').replace(/\/+$/, '').split('/').pop();
    const label = worktree && alias === 'main' ? worktree : alias;
    const checkout = worktree ? 'worktree' : 'main';
    const color = scope ? _termScopeColor(scope) : '#8b949e';
    const title = `${alias} · ${worktree ? `Git worktree ${worktree}` : 'Main folder'}${scope?.root ? `: ${scope.root}` : ''}`;
    return `<span class="term-home-association term-folder-association" data-checkout="${checkout}" style="--term-association-color:${color}" title="${termSessEsc(title)}"><span>${termSessEsc(label)}</span>${worktree || alias !== 'main' ? `<small>${checkout}</small>` : ''}</span>`;
  }

  function _termSessionPillHtml(s, index) {
    const display = _termSessionDisplay(s);
    // Compact/full visibility is CSS-controlled so switching detail never
    // rebuilds or reconnects a terminal. The active header always carries
    // the complete identity, even in compact mode.
    const visual = _termSessionVisual(s);
    const active = (s.name === termCurrentSession && _termActiveWorkspaceId() === termCurrentWorkspaceId) ? ' active' : '';
    const recentMeta = _termSessionRecentMeta(s);
    const recent = recentMeta ? ' recent' : '';
    const logical = s.logical_name || '';
    const dead = termDeadSessions.has(s.name) ? ' dead' : '';
    const statusTitle = dead ? 'Session unreachable — click to retry' : '';
    const recentTitle = recentMeta ? `Recently active — ${recentMeta.label} · window ${_termRecentWindowLabel()}` : '';
    const context = _termSessionContext(s);
    const summary = _termSessionSummary(s);
    const ariaSummary = summary.length > 160 ? `${summary.slice(0, 157).trim()}...` : summary;
    const ariaLabel = `${display} · ${visual.badge}${ariaSummary ? ` · ${context.label}: ${ariaSummary}` : ''}`;
    const tooltip = _termSessionTooltipPayload(s, [statusTitle, recentTitle].filter(Boolean).join(' · '));
    const linked = String(s.linked_file && s.linked_file.path || '').trim();
    const scope = s.linked_scope;
    const scopeAttrs = scope ? ` style="--term-scope-color:${termSessEsc(_termScopeColor(scope))}" data-linked-scope="${termSessEsc(scope.root)}"` : '';
    return `<span${scopeAttrs} class="sess ${visual.kind}${active}${recent}${dead}" role="tab" aria-label="${termSessEsc(ariaLabel)}" aria-selected="${active ? 'true' : 'false'}" tabindex="${active ? '0' : '-1'}" draggable="true" data-order-token="${termSessEsc(`s:${logical}`)}" data-name="${termSessEsc(s.name)}" data-logical="${termSessEsc(logical)}" data-tooltip="${termSessEsc(tooltip)}">
      <span class="sess-icon" aria-hidden="true">${visual.icon}</span>
      <span class="sess-order" aria-hidden="true">${index + 1}</span>
      <span class="sess-label${s.label ? ' custom' : ''}">${termSessEsc(display)}</span>
      ${_termSessionAssociationHtml(s)}
      ${linked ? `<span class="sess-link" aria-hidden="true">&#x21C4;</span>` : ''}
    </span>`;
  }

  function termRenderSessionList() {
    if (_termDragState) {
      if (_termDragState.scope === _termGroupScopeKey()) return;
      _termFinishDrag(false);
    }
    const el = document.getElementById('termSessionList');
    if (!el) return;
    _termSyncTabSelection();
    _termRenderActiveSessionHeader();
    if (!termSessions || termSessions.length === 0) {
      const html = _termNewButtonHtml();
      if (el._labTabsHtml === html) return;
      el._labTabsHtml = html;
      _termHideSessionTooltip();
      el.innerHTML = html;
      return;
    }
    const groupState = _termReadGroupState();
    const order = _termReconcileGroupOrder(groupState);
    if (JSON.stringify(order) !== JSON.stringify(groupState.order)) {
      groupState.order = order;
      groupState.membership = {};
      _termWriteGroupState(groupState);
    }
    const sessionsByLogical = new Map(
      termSessions.map((session, index) => [session.logical_name, {session, index}])
    );
    const groupsById = new Map(groupState.groups.map(group => [group.id, group]));
    const dividerOwners = new Map();
    order.forEach((token, index) => {
      if (!token.startsWith('g:')) return;
      const before = order.slice(0, index).reverse().find(item => item.startsWith('s:'));
      const after = order.slice(index + 1).find(item => item.startsWith('s:'));
      const owner = before && groupState.tabMembership[before.slice(2)];
      if (owner && after && groupState.tabMembership[after.slice(2)] === owner) dividerOwners.set(token, owner);
    });
    const dividerHtml = divider => `<div class="term-divider" draggable="true" data-order-token="${termSessEsc(`g:${divider.id}`)}" data-term-group-trigger data-divider-options="${termSessEsc(divider.id)}" role="button" tabindex="0" aria-label="Colored terminal tab divider" title="Click to change color · Drag to move divider" style="--term-divider-color:${termSessEsc(divider.color)}"></div>`;
    const renderedGroups = new Set();
    const renderRow = row => {
      const groupId = groupState.tabMembership[row.session.logical_name];
      const group = groupState.tabGroups.find(item => item.id === groupId);
      if (!group) return _termSessionPillHtml(row.session, row.index);
      if (renderedGroups.has(groupId)) return '';
      renderedGroups.add(groupId);
      const members = order.filter(token => token.startsWith('s:') && groupState.tabMembership[token.slice(2)] === groupId)
        .map(token => sessionsByLogical.get(token.slice(2))).filter(Boolean);
      const active = members.some(item => item.session.name === termCurrentSession);
      const contents = order.map(token => {
        if (dividerOwners.get(token) === groupId) return dividerHtml(groupsById.get(token.slice(2)));
        if (!token.startsWith('s:') || groupState.tabMembership[token.slice(2)] !== groupId) return '';
        const member = sessionsByLogical.get(token.slice(2));
        return member ? _termSessionPillHtml(member.session, member.index) : '';
      }).join('');
      return `<div class="term-tab-group" style="--term-group-color:${termSessEsc(group.color)}">
        <button class="term-tab-group-label${active ? ' has-active' : ''}" data-tab-group="${termSessEsc(group.id)}" aria-expanded="${!group.collapsed}" title="${termSessEsc(group.name)} · Right-click for group options">${group.collapsed ? '▸' : '▾'} <span>${termSessEsc(group.name)}</span><small>${members.length}</small></button>
        <div class="term-tab-group-tabs" ${group.collapsed ? 'hidden' : ''}>${contents}</div>
      </div>`;
    };
    let html = '';
    let currentDivider = null;
    let currentRows = [];
    const flushDivider = () => {
      if (!currentDivider) return;
      const divider = currentDivider;
      const rows = currentRows;
      html += `<div class="term-divider-section" data-divider-id="${termSessEsc(divider.id)}">
        <div class="term-divider" draggable="true" data-order-token="${termSessEsc(`g:${divider.id}`)}" data-term-group-trigger data-divider-options="${termSessEsc(divider.id)}" role="button" tabindex="0" aria-label="Colored terminal tab divider" title="Click to change color · Drag to move divider" style="--term-divider-color:${termSessEsc(divider.color)}">
        </div>
        <div class="term-divider-tabs">${rows.map(renderRow).join('')}</div>
      </div>`;
      currentDivider = null;
      currentRows = [];
    };
    order.forEach(token => {
      if (token.startsWith('g:')) {
        if (dividerOwners.has(token)) return;
        flushDivider();
        currentDivider = groupsById.get(token.slice(2)) || null;
        return;
      }
      const row = sessionsByLogical.get(token.slice(2));
      if (!row) return;
      if (currentDivider) currentRows.push(row);
      else html += renderRow(row);
    });
    flushDivider();
    html += _termNewButtonHtml();
    // Unchanged polls must not recreate every tab or dismiss its tooltip.
    if (el._labTabsHtml === html) return;
    el._labTabsHtml = html;
    _termHideSessionTooltip();
    el.innerHTML = html;
    _termSyncTabSelection();
    el.querySelectorAll('[data-tab-group]').forEach(node => {
      node.addEventListener('click', () => termUpdateTabGroup(node.dataset.tabGroup, 'toggle'));
      node.addEventListener('contextmenu', event => {
        event.preventDefault();
        termOpenTabGroupMenu(node.dataset.tabGroup, node);
      });
    });
    el.querySelectorAll('.sess').forEach(node => {
      node.addEventListener('pointerenter', () => _termShowSessionTooltip(node));
      node.addEventListener('pointerleave', _termScheduleSessionTooltipHide);
      node.addEventListener('focus', () => _termShowSessionTooltip(node));
      node.addEventListener('blur', _termScheduleSessionTooltipHide);
      node.addEventListener('contextmenu', event => {
        event.preventDefault();
        _termHideSessionTooltip();
        termOpenTabMenu(node.getAttribute('data-name'), node);
      });
      node.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.metaKey || e.ctrlKey || _termTabSelection().size > 1) return;
        termRenameSession(node.getAttribute('data-name'));
      });
      node.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        if (e.metaKey || e.ctrlKey) {
          _termSelectTab(node.getAttribute('data-name'), true);
          return;
        }
        node.click();
      });
      node.addEventListener('click', (event) => {
        _termHideSessionTooltip();
        const name = node.getAttribute('data-name');
        if (!name) return;
        termCloseGroupMenu();
        if (event.metaKey || event.ctrlKey) {
          event.preventDefault();
          _termSelectTab(name, true);
          return;
        }
        _termSelectTab(null);
        void _termActivateTab(name);
      });
    });
    el.querySelectorAll('[data-divider-options]').forEach(divider => {
      const openOptions = (e) => {
        e.preventDefault();
        e.stopPropagation();
        termOpenDividerOptions(divider.getAttribute('data-divider-options'), divider);
      };
      divider.addEventListener('click', openOptions);
      divider.addEventListener('contextmenu', openOptions);
      divider.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        openOptions(e);
      });
    });
    termWireSessionDnD(el);
  }

  // One move plan is used by the preview and by the committed drop.
  function _termPlanItemMove(state, srcToken, dstToken, placeBefore, groupId) {
    const next = _termNormalizeGroupState(state);
    const order = _termReconcileGroupOrder(next);
    if (!order.includes(srcToken) || srcToken === dstToken) return null;
    if (dstToken && !order.includes(dstToken)) return null;
    order.splice(order.indexOf(srcToken), 1);
    const index = dstToken ? order.indexOf(dstToken) + (placeBefore ? 0 : 1) : order.length;
    order.splice(index, 0, srcToken);
    next.order = order;
    next.membership = {};
    if (srcToken.startsWith('s:')) {
      const destinationGroup = groupId === undefined
        ? (dstToken?.startsWith('s:') ? next.tabMembership[dstToken.slice(2)] : '') : groupId;
      if (destinationGroup && next.tabGroups.some(group => group.id === destinationGroup)) {
        next.tabMembership[srcToken.slice(2)] = destinationGroup;
      } else delete next.tabMembership[srcToken.slice(2)];
    }
    return next;
  }

  function _termClearDropPreview() {
    const drag = _termDragState;
    if (!drag) return;
    drag.preview?.remove();
    drag.hint?.remove();
    drag.source.classList.remove('term-drag-source');
    drag.container.querySelectorAll('.term-drop-group').forEach(node => node.classList.remove('term-drop-group'));
    drag.expanded?.setAttribute('hidden', '');
    drag.expanded = null;
    drag.target = null;
  }

  function _termFinishDrag(render = true) {
    _termClearDropPreview();
    _termClearLinkDropTarget();
    _termDragState?.source.classList.remove('dragging');
    _termDragState = null;
    _termDragLogical = null;
    if (render) termRenderSessionList();
  }

  function _termPreviewDrop(target, event) {
    const drag = _termDragState;
    if (!drag || drag.scope !== _termGroupScopeKey()) return;
    const plan = _termPlanItemMove(drag.state, _termDragLogical, target.token, target.before, target.groupId);
    if (!plan) { _termClearDropPreview(); return; }
    // Leaving the placeholder under the pointer in place avoids jitter as the
    // surrounding tabs make room. No storage or server writes happen here.
    const signature = JSON.stringify([target.token, target.before, target.groupId]);
    if (drag.target?.signature === signature) return;
    _termClearDropPreview();
    drag.target = {...target, signature};
    const group = drag.state.tabGroups.find(item => item.id === target.groupId);
    const groupNode = target.parent.closest('.term-tab-group');
    if (groupNode) {
      groupNode.classList.add('term-drop-group');
      const children = groupNode.querySelector('.term-tab-group-tabs');
      if (children.hidden) { children.hidden = false; drag.expanded = children; }
    }
    const preview = drag.source.cloneNode(true);
    preview.removeAttribute('id');
    for (const attribute of [...preview.attributes]) {
      if (attribute.name.startsWith('data-')) preview.removeAttribute(attribute.name);
    }
    preview.classList.remove('dragging', 'active', 'recent', 'dead');
    preview.classList.add('term-drop-preview');
    preview.setAttribute('draggable', 'false');
    preview.setAttribute('aria-hidden', 'true');
    preview.setAttribute('tabindex', '-1');
    preview.style.setProperty('--term-drop-color', group?.color || 'var(--accent)');
    target.parent.insertBefore(preview, target.beforeNode);
    drag.preview = preview;
    drag.source.classList.add('term-drag-source');
    const hint = document.createElement('div');
    hint.className = 'term-drag-hint';
    hint.setAttribute('role', 'status');
    const session = termSessions.find(item => `s:${item.logical_name}` === _termDragLogical);
    const label = session ? _termSessionDisplay(session) : 'Divider';
    hint.textContent = `${label} → ${group ? group.name : 'Ungrouped tabs'}`;
    document.body.appendChild(hint);
    hint.style.left = `${Math.max(8, Math.min(event.clientX + 16, window.innerWidth - hint.offsetWidth - 8))}px`;
    hint.style.top = `${Math.max(8, Math.min(event.clientY + 18, window.innerHeight - hint.offsetHeight - 8))}px`;
    drag.hint = hint;
  }

  function termWireSessionDnD(container) {
    container.querySelectorAll('[data-order-token]').forEach(item => {
      item.addEventListener('dragstart', (event) => {
        _termFinishDrag(false);
        _termHideSessionTooltip();
        termCloseGroupMenu();
        _termDragLogical = item.getAttribute('data-order-token');
        _termDragState = {source: item, container, scope: _termGroupScopeKey(), state: _termReadGroupState()};
        item.classList.add('dragging');
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = 'all';
          event.dataTransfer.setData('text/plain', _termDragLogical || '');
          if (_termDragLogical?.startsWith('s:')) event.dataTransfer.setData('application/x-lab-terminal', _termDragLogical.slice(2));
        }
      });
      item.addEventListener('dragend', () => _termFinishDrag());
    });
    container.ondragover = event => {
      const drag = _termDragState;
      if (!drag || drag.scope !== _termGroupScopeKey()) return;
      event.preventDefault();
      if (event.dataTransfer) event.dataTransfer.dropEffect = 'move';
      if (event.target.closest('.term-drop-preview')) return;
      const item = event.target.closest('[data-order-token]');
      const groupNode = event.target.closest('.term-tab-group');
      const groupId = groupNode?.querySelector('[data-tab-group]')?.dataset.tabGroup || '';
      let target;
      if (item && item !== drag.source) {
        const rect = item.getBoundingClientRect();
        const e = event;
        const before = termSessionOrientation === 'horizontal'
          ? (e.clientX - rect.left) < rect.width / 2
          : (e.clientY - rect.top) < rect.height / 2;
        target = {token: item.dataset.orderToken, before, groupId,
          parent: item.parentElement, beforeNode: before ? item : item.nextSibling};
      } else if (groupNode && _termDragLogical.startsWith('s:')) {
        // Group labels are drop targets too, including collapsed groups.
        const children = groupNode.querySelector('.term-tab-group-tabs');
        const tokens = [...children.querySelectorAll('[data-order-token]')].filter(node => node !== drag.source);
        const last = tokens[tokens.length - 1];
        if (!last) { _termClearDropPreview(); return; }
        target = {token: last.dataset.orderToken, before: false, groupId, parent: children, beforeNode: null};
      } else if (!item) {
        target = {token: null, before: false, groupId: '', parent: container,
          beforeNode: document.getElementById('termNewBtn')};
      }
      if (target) _termPreviewDrop(target, event);
      // Keep the rail usable when the intended position starts offscreen.
      const rect = container.getBoundingClientRect();
      if (termSessionOrientation === 'horizontal') {
        if (event.clientX < rect.left + 24) container.scrollLeft -= 12;
        else if (event.clientX > rect.right - 24) container.scrollLeft += 12;
      } else {
        if (event.clientY < rect.top + 24) container.scrollTop -= 12;
        else if (event.clientY > rect.bottom - 24) container.scrollTop += 12;
      }
    };
    container.ondragleave = event => {
      const rect = container.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX >= rect.right
          || event.clientY < rect.top || event.clientY >= rect.bottom) _termClearDropPreview();
    };
    container.ondrop = async event => {
      const drag = _termDragState;
      if (!drag) return;
      event.preventDefault();
      const target = drag.target;
      const src = _termDragLogical;
      const sameScope = drag.scope === _termGroupScopeKey();
      _termFinishDrag(false);
      if (sameScope && target) await termReorderItems(src, target.token, target.before, target.groupId);
      else termRenderSessionList();
    };
  }

  async function termReorderItems(srcToken, dstToken, placeBefore, groupId) {
    const groupState = _termPlanItemMove(_termReadGroupState(), srcToken, dstToken, placeBefore, groupId);
    if (!groupState) { termRenderSessionList(); return; }
    const current = groupState.order;
    _termWriteGroupState(groupState);

    // Reorder termSessions to match so the next render picks it up.
    const byLogical = Object.fromEntries(
      (termSessions || []).map(s => [s.logical_name, s])
    );
    const sessionOrder = current
      .filter(token => token.startsWith('s:'))
      .map(token => token.slice(2));
    termSessions = sessionOrder.map(logical => byLogical[logical]).filter(Boolean);
    termRenderSessionList();

    // Divider moves are browser-local and do not need a server write.
    if (srcToken.startsWith('g:')) return;

    // Persist server-side. Same workspace-id resolution used elsewhere.
    const workspaceId = _termActiveWorkspaceId();
    if (!workspaceId) return;
    // Suspend the periodic refresh while the POST is in flight: otherwise a
    // 5s-tick GET can race the POST and re-paint the old order, making the
    // reorder appear to "snap back".
    _termReorderPending = true;
    try {
      await fetch('/api/term/sessions/order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace_id: workspaceId, vault: _termVaultId(), order: sessionOrder}),
      });
    } catch (e) { /* best-effort; local order already reflects */ }
    // Small grace so filesystem writes + watcher ignore-list settle.
    setTimeout(() => { _termReorderPending = false; }, 250);
  }

  function termReorderSessions(srcLogical, dstLogical, placeBefore) {
    return termReorderItems(`s:${srcLogical}`, `s:${dstLogical}`, placeBefore);
  }

  function termSessEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  async function termToggleNewPicker(ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('termNewPicker');
    if (!el) return;
    const opening = !el.classList.contains('open');
    if (!opening) {
      el.classList.remove('open');
      return;
    }
    termCloseRecentSettings();
    // Resolve vault policy before revealing the menu so a disabled agent
    // never flashes as a clickable choice during the network round-trip.
    const scope = _termGroupScopeKey();
    await termRefreshAgentAvail(el);
    if (scope !== _termGroupScopeKey()) return;
    _termApplyNewOptions(el, scope);
    el.classList.add('open');
    const rect = document.getElementById('termNewBtn').getBoundingClientRect();
    el.style.left = `${Math.max(8, Math.min(rect.left, window.innerWidth - el.offsetWidth - 8))}px`;
    el.style.top = `${Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - el.offsetHeight - 8))}px`;
    // One-shot outside-click listener to dismiss.
    const off = (e) => {
      if (!el.contains(e.target) && e.target.id !== 'termNewBtn') {
        el.classList.remove('open');
        document.removeEventListener('click', off);
      }
    };
    setTimeout(() => document.addEventListener('click', off), 0);
  }

  // Vault policy removes disabled agents from every + New menu. Enabled
  // agents whose CLI is missing stay visible but disabled so the reason is
  // clear. Both checks are enforced again by the create-session endpoint.
  let _agentAvail = null;
  async function termRefreshAgentAvail(picker) {
    let policy;
    try {
      const [avail, loadedPolicy] = await Promise.all([
        _agentAvail
          ? Promise.resolve(_agentAvail)
          : fetch('/api/agents/available').then(r => r.json()),
        loadVaultAgentPolicy(),
      ]);
      _agentAvail = avail;
      policy = loadedPolicy;
    } catch { return; }
    const supported = new Set(policy.supported || []);
    picker.querySelectorAll('button[data-agent]').forEach(btn => {
      const a = btn.dataset.agent;
      btn.hidden = !supported.has(a);
      btn.dataset.vaultHidden = String(btn.hidden);
      const ok = _agentAvail[a] !== false;
      btn.disabled = !ok;
      btn.style.opacity = ok ? '' : '0.45';
      const base = btn.textContent.replace(/ — not installed$/, '');
      btn.textContent = ok ? base : base + ' — not installed';
    });
  }

  // ─── File ↔ terminal links ───────────────────────────────────────────
  // The link is durable session metadata. Automatic navigation is a
  // separate browser-local preference so a user can keep useful links
  // without every file or terminal selection moving the other pane.
  let _termLinkModalState = null;
  let _termLinkPending = false;
  let _termLinkEscHandler = null;
  let _termLinkedNavigationSeq = 0;

  function _termLinkContext() {
    return {workspaceId: _termActiveWorkspaceId(), vaultId: _termVaultId()};
  }

  async function _termPatchLinks(session, patch, context = _termLinkContext()) {
    if (!session?.logical_name || !context.workspaceId) throw new Error('Select a saved terminal to link.');
    const response = await fetch('/api/term/sessions/metadata', {
      method: 'PATCH', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({workspace_id: context.workspaceId, vault: context.vaultId,
        name: session.logical_name, ...patch}),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || 'Could not update terminal link.');
    // Displaced file owners may belong to a different open workspace.
    _termSessionsCache.clear();
    if (context.workspaceId !== _termActiveWorkspaceId() || context.vaultId !== _termVaultId()) return body.session;
    const updates = new Map((body.displaced || [])
      .filter(row => row.current_workspace)
      .map(row => [row.session.name, row.session]));
    updates.set(session.logical_name, body.session);
    termSessions = (termSessions || []).map(row => {
      const updated = updates.get(row.logical_name);
      return updated ? {...row, label: updated.label || null, linked_file: updated.linked_file || null,
        linked_scope: updated.linked_scope || null} : row;
    });
    _termSessionsCache.set(_termSessionsKey(context.workspaceId, context.vaultId), termSessions);
    termRenderSessionList();
    _termRenderActiveSessionHeader();
    return body.session;
  }

  function _termSessionsLinkedToContext(ctx) {
    const absolute = _termLinkedAbsolutePath(ctx.root, ctx.path);
    return (termSessions || []).filter(session => ctx.kind === 'file'
      ? _termLinkedFileMatches(session.linked_file, ctx.root, ctx.path)
      : _termNormalizeLinkedRoot(session.linked_scope?.root) === _termNormalizeLinkedRoot(absolute));
  }

  async function termLinkTarget(ctx, sessionName) {
    const session = (termSessions || []).find(row => row.name === sessionName);
    const context = _termLinkContext();
    if (!session?.logical_name || !context.workspaceId) {
      explorerToast('Select a terminal to link.', true);
      return;
    }
    const clipboard = ctx.kind === 'file' ? _copyToClipboard(_termLinkedAbsolutePath(ctx.root, ctx.path)) : null;
    try {
      let scope = ctx.scope || await _termScopeForFile(ctx);
      if (ctx.kind !== 'file' && !ctx.scope) {
        const absolute = _termLinkedAbsolutePath(ctx.root, ctx.path);
        if (_termNormalizeLinkedRoot(scope.root) !== _termNormalizeLinkedRoot(absolute)) {
          scope = {...scope, root: absolute, project_root: absolute, worktree: null,
            label: _termLinkedFileName(absolute)};
        }
      }
      if (context.workspaceId !== _termActiveWorkspaceId() || context.vaultId !== _termVaultId()) return;
      const patch = {linked_scope: scope};
      if (ctx.kind === 'file') Object.assign(patch,
        {linked_file: {root: ctx.root, path: ctx.path}, label: _termLinkedFileName(ctx.path)});
      await _termPatchLinks(session, patch, context);
      const copied = clipboard && await clipboard;
      explorerToast(`Terminal linked to ${ctx.kind === 'file' ? _termLinkedFileName(ctx.path) : scope.label}${copied ? ' · Absolute path copied' : ''}`);
    } catch (error) { explorerToast(error.message || String(error), true); }
  }

  async function termUnlinkTarget(sessionName, kind) {
    const session = (termSessions || []).find(row => row.name === sessionName);
    if (!session) return;
    const patch = kind === 'file' ? {linked_file: null} : {linked_scope: null};
    if (kind === 'file' && session.label === _termLinkedFileName(session.linked_file?.path)) patch.label = null;
    try {
      await _termPatchLinks(session, patch);
      explorerToast('Terminal link removed.');
    } catch (error) { explorerToast(error.message || String(error), true); }
  }

  function _termLinkDropContext(target) {
    const row = target?.closest?.('[data-entry-kind][data-entry-path], .sidebar-file-scope-button, .sidebar-worktree-picker');
    if (!row) return null;
    if (row.matches('[data-entry-kind]')) return _explorerContextFromRow(row);
    const baseRoot = row.getAttribute('data-base-root');
    if (row.classList.contains('sidebar-file-scope-button')) {
      const root = row.getAttribute('data-folder-path') || baseRoot;
      const folder = _sidebarFolderScope(root);
      return {kind: 'folder', root, path: '', row, scope: {base_root: baseRoot,
        project_root: root, root, worktree: null, label: folder?.label || 'Root',
        color: _sidebarValidColor(folder?.color || _sidebarFileConfig.rootScopeColors?.[baseRoot]),
        config_scope: _sidebarFileConfigScope}};
    }
    const scope = _termSelectedScope(baseRoot);
    return scope ? {kind: 'folder', root: scope.root, path: '', row, scope} : null;
  }

  let _termLinkDropElement = null;
  function _termClearLinkDropTarget() {
    _termLinkDropElement?.classList.remove('term-link-drop-target');
    _termLinkDropElement = null;
  }

  function _termDraggedLinkSession() {
    if (!_termDragState || _termDragState.scope !== _termGroupScopeKey()
        || !_termDragLogical?.startsWith('s:')) return null;
    return (termSessions || []).find(row => row.logical_name === _termDragLogical.slice(2)) || null;
  }

  document.addEventListener('dragover', event => {
    if (!_termDraggedLinkSession()) return;
    const ctx = _termLinkDropContext(event.target);
    _termClearLinkDropTarget();
    if (!ctx) return;
    event.preventDefault();
    _termClearDropPreview();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'link';
    ctx.row.classList.add('term-link-drop-target');
    _termLinkDropElement = ctx.row;
  });
  document.addEventListener('dragleave', event => {
    if (_termLinkDropElement && !_termLinkDropElement.contains(event.relatedTarget)) _termClearLinkDropTarget();
  });
  document.addEventListener('drop', event => {
    const session = _termDraggedLinkSession();
    const ctx = session && _termLinkDropContext(event.target);
    if (!ctx) return;
    event.preventDefault();
    event.stopPropagation();
    _termFinishDrag(false);
    void termLinkTarget(ctx, session.name);
  });
  document.addEventListener('contextmenu', event => {
    const ctx = _termLinkDropContext(event.target);
    if (!ctx?.scope) return; // File/folder tree rows use the explorer menu.
    event.preventDefault();
    const linked = _termSessionsLinkedToContext(ctx);
    const row = (action, label) => `<button role="menuitem" class="term-group-menu-row" data-action="${termSessEsc(action)}">${termSessEsc(label)}</button>`;
    _termShowGroupMenu(ctx.row, row('link', 'Link to active terminal') + linked.map((session, i) =>
      row(`unlink:${i}`, linked.length === 1 ? 'Unlink from terminal' : `Unlink from ${_termSessionDisplay(session)}`)).join(''), action => {
      termCloseGroupMenu();
      if (action === 'link') void termLinkTarget(ctx, termCurrentSession);
      else void termUnlinkTarget(linked[Number(action.slice(7))]?.name, 'scope');
    });
  });

  function _termSelectedScope(baseRoot = _sidebarWorktreeBaseRoot()) {
    if (!baseRoot) return null;
    const worktree = _sidebarSelectedWorktree(baseRoot);
    return {
      base_root: baseRoot,
      project_root: _sidebarWorkspaceRoot(baseRoot),
      root: _sidebarScopedRoot(baseRoot),
      worktree: worktree?.path || null,
      label: _sidebarWorkspaceLabel(baseRoot) + (worktree ? ` · ${worktree.name}` : ''),
      color: worktree ? _sidebarWorktreeColor(worktree.path) : _sidebarWorkspaceColor(baseRoot),
      config_scope: _sidebarFileConfigScope,
    };
  }

  function _termPathWithin(path, root) {
    return path === root || path.startsWith(root.replace(/\/+$/, '') + '/');
  }

  async function _termScopeForFile(ctx) {
    const selected = _termSelectedScope();
    const absolute = _termLinkedAbsolutePath(ctx.root, ctx.path);
    if (selected && _termPathWithin(absolute, selected.root)
        && !(_sidebarFileConfig.folderScopes || []).some(row =>
          row.path.length > selected.root.length && _termPathWithin(absolute, row.path))) return selected;
    const baseRoot = selected?.base_root || ctx.root;
    const config = _sidebarFileConfig;
    const configScope = _sidebarFileConfigScope;
    const projects = [{path: baseRoot, label: 'Root', color: config.rootScopeColors?.[baseRoot],
      worktreeFolder: config.rootWorktreeFolders?.[baseRoot] || config.worktreeFolder},
      ...(config.folderScopes || [])];
    const candidates = [];
    for (const project of projects) {
      candidates.push({project, root: project.path, worktree: null, label: project.label, color: project.color});
      if (!project.worktreeFolder) continue;
      const query = new URLSearchParams({path: project.worktreeFolder,
        repo: _sidebarWorktreeRepositoryRoot(project.path), scope: project.path});
      const response = await fetch(`/api/sidebar-worktrees?${query}`);
      if (!response.ok) throw new Error('Could not resolve the file’s worktree.');
      const data = await response.json();
      for (const row of data.folders || []) {
        candidates.push({project, root: row.path, worktree: row.path,
          label: `${project.label} · ${row.name}`, color: config.worktreeColors?.[row.path]});
      }
    }
    const match = candidates.filter(row => _termPathWithin(absolute, row.root))
      .sort((a, b) => b.root.length - a.root.length)[0];
    return {base_root: baseRoot, project_root: match?.project.path || ctx.root,
      root: match?.root || ctx.root, worktree: match?.worktree || null,
      label: match?.label || ctx.root.split('/').pop() || 'Root',
      color: _sidebarValidColor(match?.color), config_scope: configScope};
  }

  function _termScopeColor(scope) {
    const config = scope.config_scope === _sidebarFileConfigScope
      ? _sidebarFileConfig : _loadSidebarFileConfig(scope.config_scope);
    const color = scope.worktree ? config.worktreeColors?.[scope.worktree]
      : scope.project_root === scope.base_root ? config.rootScopeColors?.[scope.base_root]
      : config.folderScopes?.find(row => row.path === scope.project_root)?.color;
    return _sidebarValidColor(color || scope.color);
  }

  async function termLinkCurrentScope(button) {
    const session = (termSessions || []).find(row => row.name === termCurrentSession);
    if (!session?.logical_name || termCurrentWorkspaceId !== _termActiveWorkspaceId()) {
      explorerToast('Select a terminal to link.', true);
      return;
    }
    const scope = _termSelectedScope(button.getAttribute('data-base-root'));
    if (!scope) return;
    button.disabled = true;
    try { await termLinkTarget({kind: 'folder', root: scope.root, path: '', scope}, session.name); }
    finally { button.disabled = false; }
  }

  window.termLinkCurrentScope = termLinkCurrentScope;

  async function _termSyncLinkedScope(scope, request) {
    if (!scope || !_linkedTerminalSyncOn || request !== _termLinkedNavigationSeq) return;
    const baseRoot = _sidebarWorktreeBaseRoot();
    if (scope.base_root !== baseRoot) return;
    if (_sidebarScopedRoot(baseRoot) === scope.root) return;
    // Preserve the saved identity even when this browser has not configured the folder yet.
    if (scope.project_root !== baseRoot && !_sidebarFolderScope(scope.project_root)) {
      _sidebarFileConfig.folderScopes.push({path: scope.project_root,
        label: scope.label.split(' · ')[0], color: scope.color, worktreeFolder: ''});
    }
    _sidebarFileConfig.selectedFolders = {..._sidebarFileConfig.selectedFolders,
      [baseRoot]: scope.project_root === baseRoot ? '' : scope.project_root};
    _sidebarFileConfig.selectedWorktrees = {..._sidebarFileConfig.selectedWorktrees,
      [scope.project_root]: scope.worktree || ''};
    if (scope.worktree && !_sidebarActiveWorktreeFolder(baseRoot)) {
      const parent = scope.worktree.slice(0, scope.worktree.lastIndexOf('/')) || '/';
      const folder = _sidebarFolderScope(scope.project_root);
      if (folder) folder.worktreeFolder = parent;
      else _sidebarFileConfig.rootWorktreeFolders = {..._sidebarFileConfig.rootWorktreeFolders,
        [baseRoot]: parent};
    }
    _storeSidebarFileConfig();
    _sidebarClearWorktreeDiscovery();
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    workspaceOpenFile = null;
    diffCache = {uncommitted: null, branch: null};
    _lastWorkspaceMtime = 0;
    _workspaceSidebarCache.delete(baseRoot);
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
    await _refreshSidebarAfterFileConfig();
  }

  function _termCancelPendingLinkedFileOpen() {
    _termLinkedNavigationSeq += 1;
  }

  function _termNormalizeLinkedRoot(value) {
    const root = String(value || '').trim();
    return root.length > 1 ? root.replace(/\/+$/, '') : root;
  }

  function _termLinkedFile(linkedFile) {
    if (!linkedFile || typeof linkedFile !== 'object') return null;
    const root = _termNormalizeLinkedRoot(linkedFile.root);
    const path = String(linkedFile.path || '').trim();
    return root && path ? {root, path} : null;
  }

  function _termLinkedFileMatches(linkedFile, root, path) {
    const linked = _termLinkedFile(linkedFile);
    return !!linked && _termLinkedAbsolutePath(linked.root, linked.path)
      === _termLinkedAbsolutePath(root, path);
  }

  function _termLinkedFileLabel(linkedFile) {
    const linked = _termLinkedFile(linkedFile);
    if (!linked) return '';
    return linked.path;
  }

  function _termLinkedFileName(path) {
    return String(path || '').split('/').filter(Boolean).pop() || 'file';
  }

  function _termLinkedAbsolutePath(root, path) {
    const normalizedRoot = _termNormalizeLinkedRoot(root);
    const normalizedPath = String(path || '').trim();
    if (!normalizedPath) return normalizedRoot;
    if (normalizedPath.startsWith('/')) return normalizedPath;
    const relativePath = normalizedPath.replace(/^\.\/+/, '').replace(/^\/+/, '');
    if (!normalizedRoot || normalizedRoot === '/') return `/${relativePath}`;
    return `${normalizedRoot}/${relativePath}`;
  }

  function _termCopyLinkedAbsolutePath(state) {
    const absolutePath = state
      ? _termLinkedAbsolutePath(state.ctx.root, state.ctx.path)
      : '';
    return absolutePath ? _copyToClipboard(absolutePath) : Promise.resolve(false);
  }

  function _termSetLinkStatus(message, error = false) {
    const status = document.getElementById('termLinkStatus');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('error', !!error);
  }

  function _termRenderLinkModal() {
    const state = _termLinkModalState;
    const list = document.getElementById('termLinkList');
    if (!state || !list) return;
    const rows = Array.isArray(termSessions) ? termSessions : [];
    if (!rows.length) {
      list.innerHTML = '<div class="term-link-empty">No existing terminals yet. Create one above.</div>';
      return;
    }
    list.innerHTML = rows.map(session => {
      const linked = _termLinkedFile(session.linked_file);
      const sameFile = _termLinkedFileMatches(session.linked_file, state.ctx.root, state.ctx.path);
      const visual = _termSessionVisual(session);
      const name = _termSessionDisplay(session);
      const detail = linked
        ? (sameFile ? `Linked to ${linked.path}` : `Currently linked to ${linked.path}`)
        : 'Not linked';
      const badge = sameFile ? 'linked' : visual.badge;
      return `<div class="term-link-row">
        <button type="button" class="term-link-choice" data-term-link-session="${termSessEsc(session.name)}" ${_termLinkPending ? 'disabled' : ''}>
          <span class="term-link-choice-copy"><span class="term-link-choice-name">${termSessEsc(name)}</span><span class="term-link-choice-file">${termSessEsc(detail)}</span></span>
          <span class="term-link-choice-badge${sameFile ? ' linked' : ''}">${termSessEsc(badge)}</span>
        </button>
        ${sameFile ? `<button type="button" class="term-link-unlink" data-term-unlink-session="${termSessEsc(session.name)}" ${_termLinkPending ? 'disabled' : ''}>Unlink</button>` : ''}
      </div>`;
    }).join('');
  }

  async function termOpenLinkModal(ctx) {
    const workspaceId = _termActiveWorkspaceId();
    if (!ctx || ctx.kind !== 'file' || !workspaceId) {
      explorerToast('Open the file from a workspace, vault, or Framework tab to link a terminal.', true);
      return;
    }
    const vaultId = _termVaultId();
    const linkedScope = await _termScopeForFile(ctx).catch(error => {
      explorerToast(error.message, true); return null;
    });
    if (!linkedScope || workspaceId !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return;
    _termLinkModalState = {
      linkedScope,
      ctx: {root: ctx.root, path: ctx.path, surface: ctx.surface || 'workspace'},
      workspaceId,
      vaultId,
      fileName: _termLinkedFileName(ctx.path),
    };
    _termLinkPending = false;
    const modal = document.getElementById('termLinkModal');
    const target = document.getElementById('termLinkTarget');
    if (target) target.textContent = `${ctx.path} · ${ctx.root}`;
    if (modal) modal.classList.add('active');
    _termSetLinkStatus('Choose a new or existing terminal.');
    _termRenderLinkModal();
    if (!_termLinkEscHandler) {
      _termLinkEscHandler = event => {
        if (event.key === 'Escape') termCloseLinkModal();
      };
      document.addEventListener('keydown', _termLinkEscHandler);
    }
    await termRefreshAgentAvail(modal);
    try { await _termRefreshSessionsForWorkspaceId(workspaceId); } catch {}
    if (!_termLinkModalState
        || _termLinkModalState.workspaceId !== workspaceId
        || _termLinkModalState.vaultId !== vaultId) return;
    _termRenderLinkModal();
  }
  window.termOpenLinkModal = termOpenLinkModal;

  function termCloseLinkModal() {
    _termLinkModalState = null;
    _termLinkPending = false;
    document.getElementById('termLinkModal')?.classList.remove('active');
    if (_termLinkEscHandler) {
      document.removeEventListener('keydown', _termLinkEscHandler);
      _termLinkEscHandler = null;
    }
  }
  window.termCloseLinkModal = termCloseLinkModal;

  async function _termSaveLinkedFile(session, linkedFile) {
    const state = _termLinkModalState;
    const logical = session && session.logical_name;
    if (!state || !logical) throw new Error('This terminal has no saved session identity.');
    const label = linkedFile ? state.fileName : null;
    return _termPatchLinks(session, {label, linked_file: linkedFile,
      ...(linkedFile ? {linked_scope: state.linkedScope} : {})}, state);
  }

  async function termLinkExistingSession(sessionName) {
    const state = _termLinkModalState;
    const session = (termSessions || []).find(row => row.name === sessionName);
    if (!state || !session || _termLinkPending) return;
    // Start the clipboard write while the secondary-click choice still owns
    // browser user activation; session persistence may take long enough for
    // that permission window to expire.
    const clipboardCopy = _termCopyLinkedAbsolutePath(state);
    _termLinkPending = true;
    _termRenderLinkModal();
    _termSetLinkStatus(`Linking ${state.fileName}…`);
    try {
      await _termSaveLinkedFile(session, {root: state.ctx.root, path: state.ctx.path});
      const workspaceId = state.workspaceId;
      const name = session.name;
      termCloseLinkModal();
      document.body.classList.add('term-open');
      document.body.classList.remove('term-collapsed');
      _termRememberVisibility(_termVisibilityKey(), true);
      termAttach(name, workspaceId);
      const copied = await clipboardCopy;
      explorerToast(`Linked ${state.fileName} to ${_termSessionDisplay(session)} · ${copied ? 'Absolute path copied' : 'Clipboard unavailable'}`);
    } catch (error) {
      _termLinkPending = false;
      _termRenderLinkModal();
      _termSetLinkStatus(error && error.message || 'Could not link terminal.', true);
    }
  }
  window.termLinkExistingSession = termLinkExistingSession;

  async function termUnlinkSession(sessionName) {
    const session = (termSessions || []).find(row => row.name === sessionName);
    if (!_termLinkModalState || !session || _termLinkPending) return;
    _termLinkPending = true;
    _termRenderLinkModal();
    _termSetLinkStatus('Removing link…');
    try {
      await _termSaveLinkedFile(session, null);
      _termLinkPending = false;
      _termRenderLinkModal();
      _termSetLinkStatus('Link removed.');
    } catch (error) {
      _termLinkPending = false;
      _termRenderLinkModal();
      _termSetLinkStatus(error && error.message || 'Could not remove link.', true);
    }
  }
  window.termUnlinkSession = termUnlinkSession;

  async function termCreateLinkedSession(kind, agent) {
    const state = _termLinkModalState;
    if (!state || _termLinkPending) return;
    const clipboardCopy = _termCopyLinkedAbsolutePath(state);
    _termLinkPending = true;
    _termRenderLinkModal();
    _termSetLinkStatus(`Creating ${state.fileName}…`);
    const modal = document.getElementById('termLinkModal');
    if (modal) modal.querySelectorAll('.term-link-new button').forEach(button => { button.disabled = true; });
    const created = await termSpawnSession(kind, {
      startFresh: true,
      agent,
      name: state.fileName,
      linkedScope: state.linkedScope,
    });
    if (!created || _termLinkModalState !== state) {
      if (_termLinkModalState === state) {
        _termLinkPending = false;
        _termRenderLinkModal();
        if (modal) void termRefreshAgentAvail(modal);
      }
      return;
    }
    const session = (termSessions || []).find(row => row.name === created.name) || created;
    try {
      await _termSaveLinkedFile(session, {root: state.ctx.root, path: state.ctx.path});
      termCloseLinkModal();
      const copied = await clipboardCopy;
      explorerToast(`Created ${state.fileName} and linked it · ${copied ? 'Absolute path copied' : 'Clipboard unavailable'}`);
    } catch (error) {
      _termLinkPending = false;
      _termRenderLinkModal();
      if (modal) void termRefreshAgentAvail(modal);
      _termSetLinkStatus(`Terminal created, but linking failed: ${error && error.message || error}`, true);
    }
  }
  window.termCreateLinkedSession = termCreateLinkedSession;

  document.getElementById('termLinkList')?.addEventListener('click', event => {
    const unlink = event.target.closest('[data-term-unlink-session]');
    if (unlink) {
      event.preventDefault();
      void termUnlinkSession(unlink.getAttribute('data-term-unlink-session'));
      return;
    }
    const link = event.target.closest('[data-term-link-session]');
    if (link) {
      event.preventDefault();
      void termLinkExistingSession(link.getAttribute('data-term-link-session'));
    }
  });

  function _termSyncFromFileClick(root, path) {
    if (!_linkedTerminalSyncOn) return;
    const matches = (termSessions || []).filter(session =>
      _termLinkedFileMatches(session.linked_file, root, path));
    if (!matches.length) return;
    const current = matches.find(session =>
      session.name === termCurrentSession && termCurrentWorkspaceId === _termActiveWorkspaceId());
    const target = current || matches[0];
    if (!target) return;
    const workspaceId = _termActiveWorkspaceId();
    if (!workspaceId) return;
    document.body.classList.add('term-open');
    document.body.classList.remove('term-collapsed');
    _termRememberVisibility(_termVisibilityKey(), true);
    if (current) return;
    termAttach(target.name, workspaceId);
  }

  function _termPreferredLinkedSidebarRow(linked) {
    const rows = Array.from(document.querySelectorAll(
      '[data-entry-kind="file"][data-entry-path][data-entry-root]',
    ));
    const matches = rows.filter(row => _termLinkedFileMatches(
      linked,
      row.getAttribute('data-entry-root'),
      row.getAttribute('data-entry-path'),
    ));
    return matches.find(row => row.classList.contains('sidebar-file-recent'))
      || matches.find(row => row.classList.contains('tree-file'))
      || matches.find(row => row.classList.contains('sidebar-file'))
      || null;
  }

  function _termRevealLinkedSidebarRow(row) {
    if (!row) return;
    let parent = row.parentElement;
    while (parent && parent.id !== 'sidebar') {
      const trigger = parent.previousElementSibling;
      if (parent.classList.contains('sidebar-folder-children')) {
        parent.classList.add('open');
        if (trigger && trigger.classList.contains('sidebar-folder')) {
          trigger.querySelector('.folder-arrow')?.classList.add('open');
          _treeSetOpen(
            trigger.getAttribute('data-tree-scope'),
            trigger.getAttribute('data-tree-path'),
            true,
          );
        }
      } else if (parent.classList.contains('tree-dir-children')) {
        parent.classList.remove('collapsed');
        if (trigger && trigger.classList.contains('tree-dir')) {
          trigger.querySelector('.arrow')?.classList.remove('collapsed');
        }
      }
      parent = parent.parentElement;
    }
  }

  function _termSelectLinkedSidebarRow(linked) {
    const row = _termPreferredLinkedSidebarRow(linked);
    if (!row) return false;
    _termRevealLinkedSidebarRow(row);
    document.querySelectorAll('.sidebar-file.active, .tree-file.active')
      .forEach(candidate => candidate.classList.remove('active'));
    row.classList.add('active');
    try { row.scrollIntoView({block: 'nearest'}); } catch {}
    return true;
  }

  async function _termOpenLinkedFile(session) {
    const request = ++_termLinkedNavigationSeq;
    if (!_linkedTerminalSyncOn) return;
    await _termSyncLinkedScope(session && session.linked_scope, request);
    if (!_linkedTerminalSyncOn || request !== _termLinkedNavigationSeq) return;
    const linked = _termLinkedFile(session && session.linked_file);
    if (!linked || !currentWorkspace) return;
    const repoRoot = typeof _activeRepoFileRoot === 'function'
      ? _termNormalizeLinkedRoot(_activeRepoFileRoot()) : '';
    if (currentRepo && repoRoot === linked.root) {
      await openWorkspaceFile(linked.path);
    } else {
      await openWorkspaceDoc(linked.path, {root: linked.root});
    }
    if (request !== _termLinkedNavigationSeq) return;
    _termSelectLinkedSidebarRow(linked);
  }

  let _termAttachModalScope = null;
  let _termAttachModalRows = [];
  let _termAttachModalRequestSeq = 0;
  let _termAttachModalGeneration = 0;
  let _termAttachPendingName = null;
  let _termAttachEscHandler = null;

  function _termAttachWorkspaceLabel(row) {
    const workspaceId = String(row && row.workspace_id || '');
    if (!workspaceId) return 'Unassigned';
    if (workspaceId === SELF_WORKSPACE_ID) return 'Framework';
    // Keep pseudo-workspace matching self-contained: terminal helper tests run
    // this function without evaluating the full application constant block.
    if (workspaceId === '__assistant__') return 'Assistant';
    if (workspaceId === CEREBRO_WORKSPACE_ID) return 'Cerebro';
    if (workspaceId === VAULT_WORKSPACE_ID) return 'Vault';
    return String(row.workspace_name || workspaceId);
  }

  function _termAttachGroupKey(row) {
    return `${String(row && row.vault || '')}\u0000${String(row && row.workspace_id || '')}`;
  }

  function _termAttachOrderedGroups(rows, scope, filter = '') {
    const needle = String(filter || '').trim().toLowerCase();
    const filtered = (Array.isArray(rows) ? rows : []).filter(row => {
      if (!needle) return true;
      return [
        row && row.name,
        row && row.logical_name,
        row && row.workspace_id,
        row && row.workspace_name,
        row && row.vault,
        row && row.agent,
        row && row.kind,
      ].some(value => String(value || '').toLowerCase().includes(needle));
    });
    const byWorkspace = new Map();
    filtered.forEach(row => {
      const key = _termAttachGroupKey(row);
      if (!byWorkspace.has(key)) {
        byWorkspace.set(key, {
          key,
          workspaceId: String(row.workspace_id || ''),
          workspaceName: _termAttachWorkspaceLabel(row),
          vault: String(row.vault || ''),
          current: !!row.current_workspace || (
            String(row.workspace_id || '') === String(scope && scope.workspaceId || '')
            && String(row.vault || '') === String(scope && scope.vaultId || '')
          ),
          rows: [],
        });
      }
      byWorkspace.get(key).rows.push(row);
    });
    const groups = Array.from(byWorkspace.values());
    groups.forEach(group => group.rows.sort((a, b) =>
      Number(!!a.has_ui_tab) - Number(!!b.has_ui_tab)
      || Number(b.created || b.created_at || 0) - Number(a.created || a.created_at || 0)
      || String(a.logical_name || a.name).localeCompare(String(b.logical_name || b.name))
    ));
    groups.sort((a, b) =>
      Number(b.current) - Number(a.current)
      || Number(!a.workspaceId) - Number(!b.workspaceId)
      || a.workspaceName.localeCompare(b.workspaceName)
      || a.vault.localeCompare(b.vault)
    );
    return groups;
  }

  function _termAttachAge(row) {
    const timestamp = Number(row && (row.created || row.created_at) || 0);
    if (!timestamp) return '';
    const seconds = Math.max(0, Math.floor(Date.now() / 1000) - timestamp);
    if (seconds < 60) return `${seconds}s`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
  }

  function _termSetAttachStatus(message, error = false) {
    const status = document.getElementById('termAttachStatus');
    if (!status) return;
    status.textContent = message;
    status.classList.toggle('error', !!error);
  }

  function termRenderAttachModal() {
    const list = document.getElementById('termAttachList');
    if (!list) return;
    const filter = document.getElementById('termAttachFilter');
    const groups = _termAttachOrderedGroups(
      _termAttachModalRows,
      _termAttachModalScope,
      filter && filter.value,
    );
    const visibleCount = groups.reduce((total, group) => total + group.rows.length, 0);
    if (!visibleCount) {
      list.innerHTML = `<div class="term-attach-empty">${_termAttachModalRows.length ? 'No sessions match this filter.' : 'No live tmux sessions found.'}</div>`;
      _termSetAttachStatus(_termAttachModalRows.length ? 'Try a different filter.' : 'There are no sessions available to attach.');
      return;
    }

    list.innerHTML = groups.map(group => {
      const workspaceId = group.workspaceId && group.workspaceId !== group.workspaceName
        ? `<span class="term-attach-workspace-id">${termSessEsc(group.workspaceId)}</span>` : '';
      const vault = group.vault
        ? `<span class="term-attach-vault">${termSessEsc(group.vault)}</span>` : '';
      const current = group.current
        ? '<span class="term-attach-current-badge">Current workspace</span>' : '';
      const sections = [false, true].map(hasUiTab => {
        const sessions = group.rows.filter(row => !!row.has_ui_tab === hasUiTab);
        if (!sessions.length) return '';
        const heading = hasUiTab ? 'Attached in Lab' : 'Available to attach';
        const sessionRows = sessions.map(row => {
          const label = String(row.logical_name || row.name || 'tmux');
          const fullName = String(row.name || '');
          const meta = [];
          if (row.windows != null) meta.push(`${row.windows} ${Number(row.windows) === 1 ? 'window' : 'windows'}`);
          const age = _termAttachAge(row);
          if (age) meta.push(age);
          const kind = row.agent || row.kind;
          const kindBadge = kind ? `<span class="term-attach-badge">${termSessEsc(kind)}</span>` : '';
          const attachedBadge = hasUiTab ? '<span class="term-attach-badge live">attached</span>' : '';
          const tabLocation = [row.tab_workspace_name || row.tab_workspace_id, row.tab_vault]
            .filter(Boolean).join(' · ');
          const title = hasUiTab
            ? `Already has a Lab terminal tab${tabLocation ? ` in ${tabLocation}` : ''}`
            : (row.summary
              ? `${fullName} — ${String(row.summary)}`
              : `Attach ${fullName} without stopping the original session`);
          const disabled = hasUiTab || _termAttachPendingName;
          return `<button type="button" class="term-attach-row${hasUiTab ? ' has-tab' : ''}" data-term-attach-name="${termSessEsc(fullName)}" title="${termSessEsc(title)}" ${disabled ? 'disabled' : ''}>
            <span class="term-attach-main"><span class="term-attach-label">${termSessEsc(label)}</span>${label !== fullName ? `<span class="term-attach-name">${termSessEsc(fullName)}</span>` : ''}</span>
            <span class="term-attach-meta">${termSessEsc(meta.join(' · '))}</span>
            <span class="term-attach-badges">${kindBadge}${attachedBadge}</span>
          </button>`;
        }).join('');
        return `<div class="term-attach-state-title">${heading} · ${sessions.length}</div>${sessionRows}`;
      }).join('');
      return `<section class="term-attach-workspace${group.current ? ' current' : ''}">
        <div class="term-attach-workspace-head"><span class="term-attach-workspace-name">${termSessEsc(group.workspaceName)}</span>${workspaceId}${current}${vault}<span class="term-attach-workspace-count">${group.rows.length}</span></div>
        ${sections}
      </section>`;
    }).join('');
    const availableCount = groups.reduce(
      (total, group) => total + group.rows.filter(row => !row.has_ui_tab).length,
      0,
    );
    const attachedCount = visibleCount - availableCount;
    _termSetAttachStatus(`${availableCount} available to attach · ${attachedCount} already ${attachedCount === 1 ? 'has a tab' : 'have tabs'}`);
  }

  async function termReloadAttachModal() {
    const scope = _termAttachModalScope;
    const list = document.getElementById('termAttachList');
    if (!scope || !list) return;
    const seq = ++_termAttachModalRequestSeq;
    list.innerHTML = '<div class="term-attach-empty">Loading live sessions…</div>';
    _termSetAttachStatus('Reading tmux sessions…');
    const query = new URLSearchParams({workspace_id: scope.workspaceId});
    if (scope.vaultId) query.set('vault', scope.vaultId);
    try {
      const response = await fetch(`/api/term/sessions/attachable?${query}`);
      const rows = await response.json().catch(() => []);
      if (!response.ok) throw new Error(rows.detail || response.statusText || 'session list failed');
      if (seq !== _termAttachModalRequestSeq || scope !== _termAttachModalScope) return;
      _termAttachModalRows = Array.isArray(rows) ? rows : [];
      termRenderAttachModal();
    } catch (listError) {
      if (seq !== _termAttachModalRequestSeq || scope !== _termAttachModalScope) return;
      _termAttachModalRows = [];
      list.innerHTML = '<div class="term-attach-empty">Could not load tmux sessions.</div>';
      _termSetAttachStatus(listError && listError.message || 'Could not load tmux sessions.', true);
    }
  }

  async function termOpenAttachModal(ev) {
    if (ev) {
      ev.preventDefault();
      ev.stopPropagation();
    }
    const workspaceId = _termActiveWorkspaceId();
    if (!workspaceId) {
      termSetStatus('err', 'open a workspace before attaching a session');
      return;
    }
    const vaultId = _termVaultId();
    const workspaceLabel = workspaceId === SELF_WORKSPACE_ID ? 'Home'
      : (currentWorkspace && currentWorkspace.is_workspace ? _workspaceDisplayName(currentWorkspace) : workspaceId);
    _termAttachModalGeneration += 1;
    _termAttachModalScope = {workspaceId, vaultId, workspaceLabel, homeSection: _termHomeSection()};
    _termAttachModalRows = [];
    _termAttachPendingName = null;
    document.getElementById('termNewPicker')?.classList.remove('open');
    const modal = document.getElementById('termAttachModal');
    const target = document.getElementById('termAttachTarget');
    const filter = document.getElementById('termAttachFilter');
    if (target) target.textContent = `Add to ${workspaceLabel}${vaultId ? ` · ${vaultId}` : ''}`;
    if (filter) filter.value = '';
    if (modal) modal.classList.add('active');
    if (!_termAttachEscHandler) {
      _termAttachEscHandler = event => {
        if (event.key === 'Escape') termCloseAttachModal();
      };
      document.addEventListener('keydown', _termAttachEscHandler);
    }
    await termReloadAttachModal();
    if (_termAttachModalScope && filter) filter.focus();
  }

  function termCloseAttachModal() {
    _termAttachModalRequestSeq += 1;
    _termAttachModalGeneration += 1;
    _termAttachModalScope = null;
    _termAttachModalRows = [];
    _termAttachPendingName = null;
    document.getElementById('termAttachModal')?.classList.remove('active');
    if (_termAttachEscHandler) {
      document.removeEventListener('keydown', _termAttachEscHandler);
      _termAttachEscHandler = null;
    }
  }

  function termChooseAttachCandidate(ev) {
    const button = ev && ev.target && ev.target.closest
      ? ev.target.closest('[data-term-attach-name]') : null;
    if (!button || _termAttachPendingName) return;
    void termAttachExisting(button.dataset.termAttachName);
  }

  async function termAttachExisting(rawSessionName) {
    const sessionName = String(rawSessionName || '').trim();
    const scope = _termAttachModalScope;
    if (!sessionName || !scope) return;
    const {workspaceId, vaultId} = scope;
    const generation = _termAttachModalGeneration;
    _termAttachPendingName = sessionName;
    termRenderAttachModal();
    _termSetAttachStatus(`Attaching ${sessionName}…`);
    termSetStatus('idle', `attaching ${sessionName}…`);
    let failureMessage = null;
    try {
      const response = await fetch('/api/term/sessions/attach', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace_id: workspaceId,
          vault: vaultId,
          name: sessionName,
        }),
      });
      const attached = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(attached.detail || response.statusText || 'attach failed');
      if (scope.homeSection) _termSaveHomeAssociation(attached.logical_name, scope.homeSection);
      if (generation === _termAttachModalGeneration) termCloseAttachModal();
      if (workspaceId !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return;
      if (scope.homeSection && scope.homeSection !== _termHomeSection()) return;
      _termClearDead(attached.name);
      await _termRefreshSessionsForWorkspaceId(workspaceId);
      if (!_termIsScopeActive(workspaceId)) return;
      if (scope.homeSection && scope.homeSection !== _termHomeSection()) return;
      if (!termSessions.some(s => s && s.name === attached.name)) {
        termSessions = [{...attached, workspace_id: attached.workspace_id || workspaceId}, ...termSessions];
        _termSessionsCache.set(_termSessionsKey(workspaceId, vaultId), termSessions);
        termRenderSessionList();
      }
      termAttach(attached.name, workspaceId);
    } catch (attachError) {
      failureMessage = attachError && attachError.message || 'Attach failed.';
      termSetStatus('err', 'attach failed');
    } finally {
      if (generation === _termAttachModalGeneration) {
        _termAttachPendingName = null;
        termRenderAttachModal();
        if (failureMessage) _termSetAttachStatus(failureMessage, true);
      }
    }
  }

  function termCreateNew(kind, agent) {
    document.getElementById('termNewPicker')?.classList.remove('open');
    // Explicit + New: always spawn a fresh session (new name + new UUID).
    termSpawnSession(kind, { startFresh: true, agent });
  }

  async function termSpawnSession(kind, { startFresh = false, agent = null, name = null, linkedScope = null } = {}) {
    const workspaceId = _termActiveWorkspaceId();
    if (!workspaceId) return;
    const vaultId = _termVaultId();
    const homeSection = _termHomeSection();

    const scope = linkedScope || _termSelectedScope();
    termSetStatus('idle', kind === 'claude' ? `creating ${agent || 'claude'}…` : 'creating terminal…');
    try {
      const r = await fetch('/api/term/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace_id: workspaceId,
          vault: vaultId,
          kind,
          agent,  // null → server resolves workspace override / global default
          name,
          start_fresh: startFresh,
          linked_scope: scope,
          cwd: scope?.root || null,
          // No explicit `auto`: the vault's per-agent autopilot
          // setting decides (an explicit value here would override it).
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        alert('Failed to create session: ' + (body.detail || r.statusText));
        termSetStatus('err', 'create failed');
        return;
      }
      const created = await r.json();
      if (homeSection) _termSaveHomeAssociation(created.logical_name, homeSection);
      await termSetAutoSpawnEnabled(workspaceId, true, vaultId);
      if (workspaceId !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return;
      if (homeSection && homeSection !== _termHomeSection()) return;
      // Brand-new session — clear any stale dead/backoff state for this
      // tmux name (possible if the user just recycled the same logical
      // name after the previous session died).
      _termClearDead(created.name);
      // Framework pseudo-workspaces use the workspace-id-aware helper.
      if (workspaceId === CEREBRO_WORKSPACE_ID || workspaceId === SELF_WORKSPACE_ID || workspaceId === ASSISTANT_WORKSPACE_ID) {
        await termRefreshSessionsByWorkspaceId(workspaceId);
      } else {
        await termRefreshSessions(workspaceId);
      }
      if (!_termIsScopeActive(workspaceId)) return;
      if (!termSessions.some(s => s && s.name === created.name)) {
        termSessions = [{...created, workspace_id: created.workspace_id || workspaceId}, ...termSessions];
        _termSessionsCache.set(_termSessionsKey(workspaceId, vaultId), termSessions);
        termRenderSessionList();
      }
      if (homeSection && homeSection !== _termHomeSection()) return created;
      termAttach(created.name, workspaceId);
      return created;
    } catch (e) {
      alert('Failed to create session: ' + e.message);
      termSetStatus('err', 'create failed');
      return null;
    }
  }

  async function termKillCurrent() {
    if (!termCurrentSession) return;
    const workspaceId = _termActiveWorkspaceId();
    const vaultId = typeof _termVaultId === 'function' ? _termVaultId() : null;
    const session = (termSessions || []).find(s => s && s.name === termCurrentSession);
    const isAttached = session && session.kind === 'attached';
    const question = isAttached
      ? 'Detach ' + (session.logical_name || termCurrentSession) + ' from Lab? The original tmux session will keep running.'
      : 'Close terminal session ' + termCurrentSession + '? It will stay closed after reload.';
    if (!confirm(question)) return;
    const name = termCurrentSession;
    termDetach();  // full close (soft=false) — evicts cache entry
    try { await fetch('/api/term/sessions/' + encodeURIComponent(name) + '?purge=true', {method: 'DELETE'}); } catch {}
    await termSetAutoSpawnEnabled(workspaceId, false, vaultId);
    if (workspaceId !== _termActiveWorkspaceId()
        || (typeof _termVaultId === 'function' && vaultId !== _termVaultId())) return;
    if (workspaceId === CEREBRO_WORKSPACE_ID || workspaceId === SELF_WORKSPACE_ID || workspaceId === '__assistant__') await termRefreshSessionsByWorkspaceId(workspaceId);
    else if (workspaceId) await termRefreshSessions(workspaceId);
    if (!_termIsScopeActive(workspaceId)) return;
    if (termSessions.length > 0) termAttach(termSessions[0].name, workspaceId);
    else { termShowEmpty(); termSetStatus('idle', 'no session — click + New'); }
  }

  const _termKillAllPending = new Set();
  async function termKillAll() {
    const workspaceId = _termActiveWorkspaceId();
    const vaultId = _termVaultId();
    const scopeKey = _termSessionsKey(workspaceId, vaultId);
    if (!workspaceId || _termKillAllPending.has(scopeKey)) return;
    const label = currentWorkspace && currentWorkspace.name === workspaceId
      ? _workspaceDisplayName(currentWorkspace) : dashTermGroupLabel(workspaceId);
    if (!confirm(`Kill all terminal sessions for "${label}"? Running work will stop and sessions will stay closed after reload. Attached external sessions will only be detached from Lab.`)) return;
    const isActive = () => workspaceId === _termActiveWorkspaceId() && vaultId === _termVaultId();
    const names = new Set((termSessions || []).map(s => s.name));
    _termKillAllPending.add(scopeKey);
    const button = document.getElementById('termKillAllBtn');
    if (button) button.disabled = true;
    try {
      // Disable automatic spawning before terminating anything, including
      // recovery triggered by another open view when the sessions disappear.
      const setting = await fetch('/api/ui/term-autospawn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace_id: workspaceId, enabled: false, vault: vaultId}),
      });
      if (!setting.ok) throw new Error('Could not disable automatic session spawning.');
      if (isActive()) termDetach();
      for (const name of names) _termEvictCache(name, workspaceId);
      const response = await fetch('/api/term/sessions/workspace/' + encodeURIComponent(workspaceId)
        + '?purge=true' + _vaultQuery(vaultId), {method: 'DELETE'});
      const result = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(result.detail || response.statusText || 'Request failed');
      for (const name of result.killed || []) _termEvictCache(name, workspaceId);
      _termSessionsCache.delete(scopeKey);
      if (!isActive()) return;
      termSessions = [];
      termRenderSessionList();
      termShowEmpty();
      termSetStatus('idle', 'all sessions closed — click + New');
      await _termRefreshSessionsForWorkspaceId(workspaceId);
    } catch (error) {
      alert('Failed to kill all sessions: ' + error.message);
      if (isActive()) {
        await _termRefreshSessionsForWorkspaceId(workspaceId);
        if (isActive()) termSetStatus('err', 'could not close all sessions');
      }
    } finally {
      _termKillAllPending.delete(scopeKey);
      if (button) button.disabled = false;
      if (typeof workspaceTabsRefresh === 'function') workspaceTabsRefresh();
    }
  }

  async function termCopyAttachCmd() {
    // Prefer the currently-attached session; fall back to the first
    // session in the pill list so the button still works while disconnected.
    const name = termCurrentSession || (termSessions && termSessions[0] && termSessions[0].name) || null;
    if (!name) { termFlashCopy('no session'); return; }
    // `-r` = read-only client: sees every keystroke + output, can't inject
    // input. Good for riding along a running Claude session from iTerm
    // without risk of accidentally typing into it.
    const session = (termSessions || []).find(s => s && s.name === name);
    const cmd = `${session && session.attach_command || `tmux attach -t '${name}'`} -r`;
    try {
      await navigator.clipboard.writeText(cmd);
      termFlashCopy('copied');
    } catch (e) {
      // Clipboard API may be blocked on non-HTTPS / permissions. Fall back
      // to the legacy execCommand path so the feature still works locally.
      try {
        const ta = document.createElement('textarea');
        ta.value = cmd; ta.style.position = 'fixed'; ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        termFlashCopy('copied');
      } catch {
        termFlashCopy('copy failed');
      }
    }
  }

  function termFlashCopy(text) {
    const btn = document.getElementById('termCopyAttachBtn');
    if (!btn) return;
    const prev = btn.textContent;
    btn.textContent = text;
    btn.disabled = true;
    setTimeout(() => { btn.textContent = prev; btn.disabled = false; }, 1200);
  }

  // Strip tmux's mouse-tracking ENABLE sequences before passing PTY data to
  // xterm.js so xterm stays in normal (non-tracking) mode. In tracking mode
  // xterm.js forwards click/drag events to the app instead of its own
  // selection service, making text selection impossible for the user.
  // Wheel scrolling (which also needs mouse tracking to reach tmux's
  // WheelUpPane binding) is handled separately in termEnsureXterm via a
  // manual wheel listener that sends SGR mouse events directly. tmux then
  // routes them: pass-through to programs that enabled mouse reporting
  // (claude scrolls its own transcript), copy-mode line scrolling for
  // everything else (codex, shells). See _configure_tmux_wheel_scrolling
  // in term.py.
  function _termStripModes(s) {
    // Remove all ?<mode>h (enable) variants for the common mouse-tracking
    // modes tmux sends on attach. Disable variants (?<mode>l) can pass
    // through — they're no-ops when tracking was never enabled.
    return s.replace(/\x1b\[\?(?:1000|1002|1003|1005|1006|1015|1016)h/g, '');
  }

  function _termMakeContainer() {
    // Each session gets its own absolutely-positioned div inside #termBody.
    // Switching sessions = display:none / display:block. No DOM destruction.
    const body = document.getElementById('termBody');
    const container = document.createElement('div');
    container.style.cssText = 'position:absolute;inset:0;display:none';
    body.appendChild(container);
    return container;
  }

  function _termClipboardImageFile(ev) {
    const data = ev && ev.clipboardData;
    if (!data) return null;
    const items = Array.from(data.items || []);
    for (const item of items) {
      if (item && item.kind === 'file' && /^image\//i.test(item.type || '')) {
        try { return item.getAsFile(); } catch { return null; }
      }
    }
    const files = Array.from(data.files || []);
    return files.find(f => f && /^image\//i.test(f.type || '')) || null;
  }

  function _termReadFileAsDataUrl(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(reader.error || new Error('read failed'));
      reader.readAsDataURL(file);
    });
  }

  async function _termHandlePaste(ev) {
    const file = _termClipboardImageFile(ev);
    if (!file) return;  // Let xterm handle normal text paste.
    if (!termWS || termWS.readyState !== WebSocket.OPEN || !termCurrentSession) return;
    const workspaceId = _termActiveWorkspaceId();
    if (!workspaceId) return;
    ev.preventDefault();
    ev.stopPropagation();
    termSetStatus('idle', 'saving pasted image...');
    try {
      const dataUrl = await _termReadFileAsDataUrl(file);
      const r = await fetch('/api/term/paste-image', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace_id: workspaceId,
          vault: _termVaultId(),
          session_name: termCurrentSession,
          name: file.name || 'clipboard-image',
          mime: file.type || 'image/png',
          data: dataUrl,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || r.statusText || 'paste failed');
      // Terminals may now start in a project/worktree outside the workspace root.
      const path = body.absolute_path || body.path;
      if (!path) throw new Error('paste response missing path');
      if (termWS && termWS.readyState === WebSocket.OPEN) {
        termWS.send(JSON.stringify({ type: 'input', data: path }));
      }
      termSetStatus('live', 'pasted image · ' + path);
      _termClientLog('info', 'terminal image paste saved', {
        event_type: 'term.paste_image',
        target: workspaceId,
      });
    } catch (e) {
      console.warn('[term] image paste failed', e);
      termSetStatus('err', 'image paste failed');
      _termClientLog('warning', 'terminal image paste failed: ' + (e && e.message || e), {
        event_type: 'term.paste_image_failed',
        target: workspaceId,
      });
    }
  }

  function _termGuardViewportDisposal(xt) {
    const dispose = xt.dispose.bind(xt);
    xt.dispose = () => {
      // xterm 5.3 leaves viewport timers/animation frames queued on disposal.
      // Their callbacks otherwise read dimensions from the disposed renderer.
      // Keep this version-specific workaround here, not in the immutable vendor asset.
      const viewport = xt._core?.viewport;
      if (viewport) {
        viewport.syncScrollArea = () => {};
        viewport._innerRefresh = () => {};
      }
      dispose();
    };
  }

  function termEnsureXterm() {
    // Kept for the cache-miss fresh-connect path in termAttach; creates the
    // xterm+fitAddon and assigns to module-level termXterm/termFitAddon.
    // The caller is responsible for providing a container via _termMakeContainer().
    const _body = document.getElementById('termBody');
    console.log('[term] termEnsureXterm — body has', _body ? _body.children.length : '?', 'children, termXterm already=', !!termXterm);
    if (termXterm) return;
    if (typeof Terminal === 'undefined' || typeof FitAddon === 'undefined') {
      termSetStatus('err', 'xterm.js not loaded');
      return;
    }
    termXterm = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, monospace',
      theme: { background: '#0a0e13', foreground: '#e6edf3', cursor: '#58a6ff' },
      // Scrollback here is only used for non-tmux panes (none today).
      // Inside tmux, scrolling is tmux's job — wheel events are forwarded
      // as SGR mouse input and tmux either passes them to the app (claude)
      // or enters copy-mode (codex, shells).
      scrollback: 20000,
      convertEol: false,
    });
    _termGuardViewportDisposal(termXterm);
    termFitAddon = new FitAddon.FitAddon();
    termXterm.loadAddon(termFitAddon);
    // Wheel handler on the shared #termBody — routes to whatever session is
    // currently active via termXterm/termWS. Added once; all per-session
    // containers are children of #termBody so events bubble up to it.
    if (!_termWheelListenerAdded) {
      _termWheelListenerAdded = true;
      const body = document.getElementById('termBody');
      body.addEventListener('wheel', (ev) => {
        if (!termXterm || !termWS || termWS.readyState !== WebSocket.OPEN) return;
        ev.preventDefault();
        ev.stopPropagation();
        if ((ev.deltaY < 0 && _termWheelAccum > 0) || (ev.deltaY > 0 && _termWheelAccum < 0)) {
          _termWheelAccum = 0;
        }
        _termWheelAccum += ev.deltaY;
        const threshold = 100;
        const ticks = Math.trunc(_termWheelAccum / threshold);
        if (ticks === 0) return;
        _termWheelAccum -= ticks * threshold;
        const button = ticks < 0 ? 64 : 65;
        const rect = body.getBoundingClientRect();
        const col = Math.max(1, Math.floor((ev.clientX - rect.left) / (rect.width / termXterm.cols)) + 1);
        const row = Math.max(1, Math.floor((ev.clientY - rect.top) / (rect.height / termXterm.rows)) + 1);
        const count = Math.abs(ticks);
        for (let i = 0; i < count; i++) {
          termWS.send(JSON.stringify({ type: 'input', data: `\x1b[<${button};${col};${row}M` }));
        }
      }, { passive: false, capture: true });
    }
    if (!_termPasteListenerAdded) {
      const body = document.getElementById('termBody');
      if (body) {
        _termPasteListenerAdded = true;
        body.addEventListener('paste', _termHandlePaste, { capture: true });
      }
    }
  }

  // ─── GPU rendering (xterm-addon-webgl) ───
  // The DOM renderer re-lays-out hundreds of spans per repaint — visibly
  // sluggish under Claude Code's TUI, which redraws its whole status area
  // several times a second. The WebGL renderer draws glyphs on the GPU and
  // is the single biggest client-side latency win for typing echo.
  //
  // Browsers cap live WebGL contexts (~8-16 per page) and we keep parked
  // terminals alive in _termCache, so the context is attached to the
  // ACTIVE session only: enabled on attach, disposed on park/detach.
  // Any failure (no WebGL, context-limit hit, context loss) falls back to
  // the DOM renderer silently — rendering correctness is unaffected.
  let _termWebglFailed = false;  // hard failure → stop retrying this page-load
  function _termEnableWebgl() {
    if (_termWebglFailed || !termXterm || typeof WebglAddon === 'undefined') return;
    if (termXterm._webglAddon) return;  // already on
    try {
      const addon = new WebglAddon.WebglAddon();
      addon.onContextLoss(() => {
        // GPU context evicted (too many contexts / driver reset). Drop to
        // the DOM renderer for this terminal; next attach retries WebGL.
        try { addon.dispose(); } catch {}
        if (termXterm && termXterm._webglAddon === addon) termXterm._webglAddon = null;
      });
      termXterm.loadAddon(addon);
      termXterm._webglAddon = addon;
    } catch (e) {
      console.warn('[term] WebGL renderer unavailable, using DOM renderer', e);
      _termWebglFailed = true;
    }
  }
  function _termDisableWebgl(xt) {
    if (xt && xt._webglAddon) {
      try { xt._webglAddon.dispose(); } catch {}
      xt._webglAddon = null;
    }
  }
  // The vendored 0.16 addon can throw from inside xterm's render loop when
  // a queued frame races a resize that shrank the buffer (upstream xterm.js
  // "Cannot read properties of undefined (reading 'loadCell')"). That
  // exception escapes to window.onerror — no try/catch here sees it — so
  // recover the same way onContextLoss does: drop to the DOM renderer for
  // this terminal; the next attach retries WebGL.
  window.addEventListener('error', (ev) => {
    if (!termXterm || !termXterm._webglAddon) return;
    const fromAddon = (ev.filename || '').includes('xterm-addon-webgl');
    if (!fromAddon && !(ev.message || '').includes('loadCell')) return;
    console.warn('[term] WebGL renderer crashed, using DOM renderer', ev.message);
    _termDisableWebgl(termXterm);
  });

  function termShowEmpty() {
    const body = document.getElementById('termBody');
    if (!body) return;
    // Hide all per-session containers; show the empty state overlay.
    _termHidePanesExcept(null);
    let el = document.getElementById('termEmpty');
    if (!el) {
      el = document.createElement('div');
      el.id = 'termEmpty';
      el.className = 'term-empty';
      body.appendChild(el);
    }
    el.innerHTML = `Click <b>+ New</b> to spawn a <code>tmux</code> session running <code>claude</code> in this workspace's folder. You can also attach from iTerm anytime with <code>tmux attach -t &lt;name&gt;</code>.`;
    el.style.display = '';
    termXterm = null;
    termFitAddon = null;
  }

  function termSendResize() {
    if (!termXterm || !termWS || termWS.readyState !== WebSocket.OPEN) return;
    termWS.send(JSON.stringify({ type: 'resize', rows: termXterm.rows, cols: termXterm.cols }));
  }

  // soft=true: tab-switch — keep WS+xterm alive in cache, just un-mount DOM.
  // soft=false (default): full close — evict cache entry, close WS.
  function termDetach(soft = false) {
    console.log('[term] termDetach soft=', soft, 'prev=', termCurrentSession, 'cacheSize=', _termCache.size);
    const prev = termCurrentSession;
    const prevWorkspaceId = termCurrentWorkspaceId;
    // Record activity at the moment a tab is left. This matters when a tab
    // stayed selected longer than the recent window: its attach timestamp may
    // be old, but the user was actively looking at it until right now.
    if (typeof _termMarkRecent === 'function') _termMarkRecent(prevWorkspaceId, prev);
    termAttachRequestSeq += 1;  // cancel any attach still waiting on assets/layout
    termUserDetached = true;  // mark so onclose doesn't try to recover
    if (termReconnectTimer) { clearTimeout(termReconnectTimer); termReconnectTimer = null; }
    if (soft) {
      // Park: hide the session's container div, stash refs in cache. Never evict.
      // We deliberately leave the WS listeners attached so server output
      // continues to land in the cached xterm — that's what keeps the
      // pane warm so a switch back doesn't have to replay scrollback
      // through tmux. The exit-frame handler in onmessage already
      // checks whether this WS is still the active one before marking
      // dead, so a tmux-side death while parked won't pop the recovery
      // overlay over an unrelated workspace. (We did try nulling all
      // listeners here — that turned out to break input echo on the
      // cache-hit re-attach because the WS was reused without rebinding.)
      const prevContainer = termContainer;
      _termSetPaneActive(prevContainer, false);
      if (prev && prevWorkspaceId && termWS && termXterm && prevContainer) {
        // Release the GPU context while parked — hidden panes render fine
        // (and cheaply) on the DOM renderer, and this keeps us well under
        // the browser's WebGL context cap no matter how many sessions are
        // cached. Re-enabled on the next attach.
        _termDisableWebgl(termXterm);
        if (prevWorkspaceId) {
          _termCache.set(_termCacheKey(prevWorkspaceId, prev), {
            workspaceId: prevWorkspaceId,
            name: prev,
            xterm: termXterm,
            fitAddon: termFitAddon,
            ws: termWS,
            container: prevContainer,
            parkedAt: Date.now(),
          });
        }
        console.log('[term] parked', prev, 'workspace=', prevWorkspaceId, 'ws.readyState=', termWS.readyState, 'cache size=', _termCache.size);
      } else {
        // If a pane was still connecting, it may not have a WebSocket yet.
        // Do not leave that orphaned container visible behind the next
        // terminal; there is no live stream to preserve.
        if (termWS) {
          try { termWS.send(JSON.stringify({ type: 'detach' })); } catch {}
          try { termWS.close(); } catch {}
        }
        if (termXterm) { try { termXterm.dispose(); } catch {} }
        if (prevContainer) { try { prevContainer.remove(); } catch {} }
      }
    } else {
      if (termWS) {
        try { termWS.send(JSON.stringify({ type: 'detach' })); } catch {}
        try { termWS.close(); } catch {}
        termWS = null;
      }
      if (prev) _termEvictCache(prev, prevWorkspaceId);
    }
    termXterm = null;
    termFitAddon = null;
    termWS = null;
    termContainer = null;
    termCurrentSession = null;
    termCurrentWorkspaceId = null;
    const badge = document.getElementById('termAutoBadge');
    if (badge) badge.style.display = 'none';
  }

  // Compute the next reconnect delay using exponential backoff. Caps at
  // TERM_RECONNECT_CAP_MS so a long-dead server doesn't produce a tight
  // reconnect loop that spams the log and burns CPU.
  function _termBackoffMs(attempts) {
    const n = Math.max(1, attempts);
    const ms = TERM_RECONNECT_BASE_MS * Math.pow(2, n - 1);
    return Math.min(TERM_RECONNECT_CAP_MS, ms);
  }

  // A *successful* sessions fetch confirmed tmux no longer has this
  // session. Instead of parking on the manual recovery overlay, run the
  // same restore flow a cold panel-open uses: respawn saved sessions
  // (claude comes back via --resume) and reattach — no buttons to click.
  // The overlay remains only as a crash-loop fallback: if the same
  // session dies again right after an auto-restore, respawning forever
  // would fight the user (or a broken binary), so we stop and ask.
  const _termAutoRestoreAt = {};   // name -> ts of last auto-restore
  const TERM_AUTO_RESTORE_MIN_GAP_MS = 20000;
  async function _termSessionGone(name, workspaceId) {
    if (!_termIsScopeActive(workspaceId)) return;
    if (_termKillAllPending.has(_termSessionsKey(workspaceId))
        || _termCloseTabsPending.has(_termSessionsKey(workspaceId))) return;
    const now = Date.now();
    if (now - (_termAutoRestoreAt[name] || 0) < TERM_AUTO_RESTORE_MIN_GAP_MS) {
      _termMarkDead(name, 'session keeps ending: ' + name, workspaceId);
      return;
    }
    _termAutoRestoreAt[name] = now;
    _termClientLog('info', 'terminal session gone — auto-restoring', {
      event_type: 'term.restore.auto',
      target: String(workspaceId) + '::' + String(name),
    });
    // Drop the dead pane's client state so restore attaches fresh.
    if (name === termCurrentSession && workspaceId === termCurrentWorkspaceId) {
      if (termWS) { try { termWS.close(); } catch {} termWS = null; }
      termCurrentSession = null;
      termCurrentWorkspaceId = null;
    }
    _termEvictCache(name, workspaceId);
    delete termReconnectAttempts[name];
    termSetStatus('idle', 'session ended — restoring…');
    await _termRestoreSessionsForWorkspace(workspaceId);
  }

  // Endless capped-backoff reconnect after a WS drop. Waits the backoff,
  // refreshes the session list, then either re-attaches (session still
  // listed — including the "server unreachable, keep the last-known list"
  // case) or hands off to _termSessionGone once a successful refresh
  // confirms tmux no longer has the session. Deliberately no attempt cap:
  // transient outages (lab server restart, laptop sleep) heal on their
  // own, and the only terminal state is "confirmed gone".
  function _termScheduleReconnect(name, workspaceId, myWS) {
    const attempts = (termReconnectAttempts[name] || 0) + 1;
    termReconnectAttempts[name] = attempts;
    const delay = _termBackoffMs(attempts);
    termSetStatus('err', 'disconnected — reconnecting in ' + Math.max(1, Math.round(delay / 1000)) + 's…');
    if (termReconnectTimer) clearTimeout(termReconnectTimer);
    termReconnectTimer = setTimeout(async () => {
      termReconnectTimer = null;
      if (termWS !== null && termWS !== myWS) return;
      if (!_termIsScopeActive(workspaceId)) return;
      if (termDeadSessions.has(name)) return;
      let refreshOk = false;
      try { refreshOk = !!(await _termRefreshSessionsForWorkspaceId(workspaceId)); } catch {}
      if (termDeadSessions.has(name)) return;
      if (_termCanAttach(workspaceId, name)) {
        termWS = null;
        termCurrentSession = null;
        termCurrentWorkspaceId = null;
        termAttach(name, workspaceId);
      } else if (!_termIsScopeActive(workspaceId)) {
        return;
      } else if (refreshOk) {
        _termSessionGone(name, workspaceId);
      } else {
        // Server unreachable and the name isn't even in the last-known
        // list — keep the loop alive until the server answers.
        _termScheduleReconnect(name, workspaceId, myWS);
      }
    }, delay);
  }

  // Mark a session dead: stop reconnecting, clear timers, render the
  // recovery overlay. Used as the crash-loop fallback (see
  // _termSessionGone) and from termAttach on an already-dead name.
  function _termMarkDead(name, statusText, workspaceId = termCurrentWorkspaceId || _termActiveWorkspaceId()) {
    console.log('[term] MARK DEAD', name, 'workspace=', workspaceId, statusText);
    termDeadSessions.add(name);
    delete termReconnectAttempts[name];
    if (termReconnectTimer) { clearTimeout(termReconnectTimer); termReconnectTimer = null; }
    if (name === termCurrentSession && workspaceId === termCurrentWorkspaceId) {
      termCurrentSession = null;
      termCurrentWorkspaceId = null;
    }
    _termEvictCache(name, workspaceId);  // drop xterm+WS for this dead session
    if (_termIsScopeActive(workspaceId)) {
      if (statusText) termSetStatus('err', statusText);
      termShowRecovery();
      // Refresh the pill list so dead sessions drop out (tmux is gone)
      // or get the `dead` class applied when they're still on the list.
      termRenderSessionList();
    }
  }

  // User-initiated clear of the dead state. Called when the user clicks
  // a pill explicitly, or creates/reloads sessions — a manual nudge means
  // "I know, try again".
  function _termClearDead(name) {
    termDeadSessions.delete(name);
    delete termReconnectAttempts[name];
  }

  // Resolve the right xterm for a session name without depending on a
  // closure capture. Returns:
  //   - termXterm  if `name` is the currently-active session
  //   - cached entry's xterm if the session is parked (soft-detached)
  //   - null otherwise (caller should drop the data)
  // Used by the WS onmessage handler so a stale closure can never crash
  // the page with "myXterm is not defined" — there's no `myXterm` to
  // reference; the lookup happens fresh on every frame.
  function _xtermFor(name, workspaceId = termCurrentWorkspaceId || _termActiveWorkspaceId()) {
    if (workspaceId === termCurrentWorkspaceId && name === termCurrentSession && termXterm) return termXterm;
    const entry = _termCache.get(_termCacheKey(workspaceId, name));
    return entry && entry.xterm ? entry.xterm : null;
  }

  // Evict a session from the xterm cache: close its WS, dispose the
  // Terminal instance, and remove its container from the DOM.
  function _termEvictCache(name, workspaceId = termCurrentWorkspaceId || _termActiveWorkspaceId()) {
    const keys = [];
    if (workspaceId) {
      keys.push(_termCacheKey(workspaceId, name));
    } else {
      for (const [key, entry] of _termCache.entries()) {
        if (entry && entry.name === name) keys.push(key);
      }
    }
    console.log('[term] EVICT', name, 'workspace=', workspaceId, 'keys=', keys);
    for (const key of keys) {
      const entry = _termCache.get(key);
      if (!entry) continue;
      _termCache.delete(key);
      try { entry.ws.send(JSON.stringify({ type: 'detach' })); } catch {}
      try { entry.ws.close(); } catch {}
      try { entry.xterm.dispose(); } catch {}
      try { entry.container.remove(); } catch {}
    }
  }

  async function termAttach(name, workspaceId = _termActiveWorkspaceId()) {
    workspaceId = workspaceId || _termActiveWorkspaceId();
    console.log('[term] termAttach', name, 'workspace=', workspaceId, 'currentSession=', termCurrentSession, 'currentWorkspace=', termCurrentWorkspaceId, 'cacheHas=', _termCache.has(_termCacheKey(workspaceId, name)));
    if (!name || !workspaceId) return;
    if (!_termCanAttach(workspaceId, name)) return;
    // A selection counts as recent immediately. termDetach records the
    // previous tab again when the user leaves it, keeping the timestamp true
    // to the end of a long viewing session.
    if (typeof _termMarkRecent === 'function') _termMarkRecent(workspaceId, name);
    if (workspaceId === '__self__') {
      const selected = (termSessions || []).find(s => s.name === name);
      if (selected?.logical_name) _termRememberLast(workspaceId, selected.logical_name);
    }
    const attachRequestSeq = ++termAttachRequestSeq;
    if (name === termCurrentSession && workspaceId === termCurrentWorkspaceId && termWS && termWS.readyState === WebSocket.OPEN) {
      console.log('[term] early return — same session already open');
      _termShowPane(termContainer);
      _termFocusActiveSoon();
      return;
    }
    // A previous connect confirmed the session is gone. Don't hammer
    // the server — show the recovery UI and wait for a user click.
    if (termDeadSessions.has(name)) {
      console.log('[term] dead session', name);
      termSetStatus('err', 'session ended: ' + name);
      termShowRecovery();
      return;
    }

    try {
      await ensureTerminalLibs();
    } catch (e) {
      console.warn('[term] terminal assets failed to load', e);
      termSetStatus('err', 'terminal assets failed to load');
      return;
    }
    if (!_termAttachRequestIsCurrent(attachRequestSeq, workspaceId, name)) return;

    // Park the current session: hide its container, stash refs in cache.
    termDetach(true);
    termUserDetached = false;  // fresh attach — future drops should trigger recovery
    termCurrentSession = name;
    termCurrentWorkspaceId = workspaceId;
    // Persist the selection so a full page reload (workspace-tab navigation)
    // can restore the same pill instead of snapping back to "claude".
    const _attachMeta = (termSessions || []).find(s => s.name === name);
    if (_attachMeta && _attachMeta.logical_name) {
      _termRememberLast(workspaceId, _attachMeta.logical_name);
    }
    console.log('[term] after soft detach, cache keys=', Array.from(_termCache.keys()));
    // Hide the empty/recovery overlay if visible.
    const _emptyEl = document.getElementById('termEmpty');
    if (_emptyEl) _emptyEl.style.display = 'none';

    const scopeKey = _termCacheKey(workspaceId, name);
    let cached = _termCache.get(scopeKey);
    if (cached && cached.ws && cached.ws.readyState === WebSocket.OPEN && !_termCachedPaneIsFresh(cached)) {
      console.info('[term] evicting aged parked pane before attach', name, workspaceId);
      _termEvictCache(name, workspaceId);
      cached = null;
    }
    // Shared WS-open logic. `freshPane` is currently informational only —
    // both branches behave identically on the wire (no Ctrl-L, no clear).
    // Kept on the signature so callers in cache-miss vs cache-stale paths
    // stay self-documenting; remove if it stays unused.
    //
    // We deliberately do NOT capture `xterm` in a closure here. Earlier
    // revisions used `const myXterm = termXterm;` and called `myXterm.write`
    // in onmessage, but during the cache-refactor sequence (8f8508f →
    // 76f063f) intermediate WIP states had the const declared in a scope
    // that didn't enclose every reachable handler call site, causing
    // ReferenceError storms (logs/errors.log showed 539 hits at
    // 20:39:05–20:42:51). Resolving the right xterm at write-time via
    // `_xtermFor(name)` is robust to every cache state: active session,
    // parked-via-soft-detach, mid-restore — and can never throw
    // "myXterm is not defined" because there is no closure-captured
    // identifier to fall out of scope.
    const _openWS = (freshPane, _attempt = 0) => {
      if (termCurrentSession !== name || termCurrentWorkspaceId !== workspaceId) return null;
      termSetStatus('idle', 'connecting to ' + name);
      // Pass the fitted geometry so the server forks the PTY at the right
      // size. Without it tmux attaches at 80x24 and reflows the whole
      // session twice (once to 80x24, once to the real size when our
      // first resize lands) — the leftovers of that double redraw showed
      // up as a corrupted pane on every reconnect.
      //
      // On a COLD page load the panel may not be laid out yet (zero-size
      // container → fit() can't compute dims). Connecting anyway would
      // reintroduce the 80x24 bounce, so wait for layout — the pane has
      // no visible size at that point, so there's nothing to show yet
      // anyway. Bounded retry; after ~1s we connect with defaults rather
      // than never attaching.
      let dims = '';
      try {
        const p = termFitAddon && termFitAddon.proposeDimensions();
        if (p && p.cols > 2 && p.rows > 2) {
          termFitAddon.fit();
          dims = `?cols=${termXterm.cols}&rows=${termXterm.rows}`;
        }
      } catch {}
      if (!dims && _attempt < 20) {
        setTimeout(() => {
          // Abort the deferred dial if the user moved on meanwhile.
          if (termCurrentSession !== name || termCurrentWorkspaceId !== workspaceId || termUserDetached) return;
          _openWS(freshPane, _attempt + 1);
        }, 50);
        return null;
      }
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      const myWS = new WebSocket(`${proto}//${location.host}/ws/term/${encodeURIComponent(name)}${dims}`);
      termWS = myWS;
      const isParked = () => _termCache.get(scopeKey)?.ws === myWS;
      const isStale = () => {
        if (isParked()) return false;
        return termWS !== myWS || termCurrentSession !== name || termCurrentWorkspaceId !== workspaceId;
      };
      const detachListeners = () => {
        try { myWS.onopen = null; } catch {}
        try { myWS.onmessage = null; } catch {}
        try { myWS.onclose = null; } catch {}
        try { myWS.onerror = null; } catch {}
      };
      myWS.onopen = () => {
        if (isStale()) { detachListeners(); return; }
        _termClearDead(name);
        if (isParked()) return;
        const meta = termSessions.find(s => s.name === name);
        const badge = document.getElementById('termAutoBadge');
        if (badge) badge.style.display = (meta && meta.auto) ? 'inline-block' : 'none';
        termSetStatus('live', 'attached · ' + name);
        // Reconnect into an EXISTING xterm (freshPane=false): wipe the
        // local grid before tmux's replay arrives. The old content was
        // drawn by a previous connection — replaying on top of it leaves
        // stale fragments wherever the repaint doesn't cover. This is a
        // purely client-side reset: nothing is sent to tmux/claude (the
        // historical "typed input got wiped" bug was a Ctrl-L sent to the
        // app, which this is not); the replay repaints the full screen
        // including claude's in-progress input line.
        if (!freshPane && termXterm) { try { termXterm.reset(); } catch {} }
        try { termFitAddon.fit(); } catch {}
        termSendResize();
        // NOTE: we deliberately do NOT send Ctrl-L on connect.
        //
        // The previous version sent `\x0c` on `freshPane=true` to force a
        // redraw, but `freshPane=true` fires on EVERY cache-miss connect —
        // including the common case where the user navigated away from a
        // workspace tab (full page reload → cache empty → cache miss) and
        // came back. The tmux session is still alive with claude inside,
        // and any unsubmitted text in claude's input line was being wiped
        // by the Ctrl-L every reload. The user's "typed content is gone"
        // bug was this clear-on-reconnect, not the cache itself.
        //
        // tmux's pane replay (with our `alternate-screen off` option set
        // server-side) already redraws the current pane state — including
        // claude's input — without us needing to send anything. If the
        // server-side replay ever needs nudging on a brand-new tmux
        // session, do it explicitly in the `+ New` flow (termSpawnSession),
        // not on every reconnect.
        termRenderSessionList();
      };
      myWS.onmessage = (ev) => {
        if (isStale()) return;
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        if (msg.type === 'data') {
          // Resolve the live xterm at write-time — not a closure-captured
          // reference. See _openWS comment for the regression context.
          const xt = _xtermFor(name, workspaceId);
          if (xt) xt.write(_termStripModes(msg.data));
        } else if (msg.type === 'exit') {
          // If this WS is parked (we're viewing a different session /
          // workspace), don't surface the exit. The user has no UI for
          // this pane right now, and the next attach will discover
          // the dead socket via cached.ws.readyState !== OPEN and
          // reconnect through _openWS.
          if (name !== termCurrentSession || workspaceId !== termCurrentWorkspaceId) return;
          if (msg.reason === 'no-session') {
            // Warm-switch race: the pill came from _termSessionsCache,
            // which can lag actual tmux state by up to one background
            // refresh. Before showing the recovery overlay, confirm
            // the session really is gone — if a fresh
            // /api/term/sessions still lists it, the "no-session" was
            // for a stale name and we should silently re-attach to
            // whatever the server now considers canonical. Same wait-
            // for-refresh-then-decide dance the close-loop reconnect
            // path already uses below.
            const pid = _termActiveWorkspaceId();
            (async () => {
              let refreshOk = false;
              if (pid) {
                try { refreshOk = !!(await _termRefreshSessionsForWorkspaceId(pid)); } catch {}
              }
              if (_termCanAttach(workspaceId, name)) {
                // tmux still has it — the "no-session" was stale.
                // Reconnect without showing the recovery overlay.
                termWS = null;
                termCurrentSession = null;
                termCurrentWorkspaceId = null;
                termAttach(name, workspaceId);
              } else if (refreshOk && _termIsScopeActive(workspaceId)) {
                // Confirmed gone — respawn saved sessions and reattach
                // instead of asking the user what to do.
                _termSessionGone(name, workspaceId);
              } else if (_termIsScopeActive(workspaceId)) {
                _termMarkDead(name, 'session not found', workspaceId);
              }
            })();
          } else {
            termSetStatus('idle', 'detached — ' + (msg.reason || 'closed'));
          }
        }
      };
      myWS.onclose = (ev) => {
        console.log('[term] WS onclose name=', name, 'workspace=', workspaceId, 'currentSession=', termCurrentSession, 'currentWorkspace=', termCurrentWorkspaceId, 'userDetached=', termUserDetached, 'cacheHas=', _termCache.has(scopeKey), 'code=', ev.code);
        detachListeners();
        if (isStale()) return;
        if (termUserDetached || termCurrentSession !== name || termCurrentWorkspaceId !== workspaceId) return;
        if (termDeadSessions.has(name)) return;
        _termScheduleReconnect(name, workspaceId, myWS);
      };
      myWS.onerror = () => {
        if (isStale()) { detachListeners(); return; }
        if (!termUserDetached) termSetStatus('err', 'ws error');
      };
      return myWS;
    };

    // --- Cache hit, WS open: show existing container, no clear, no Ctrl-L ---
    if (cached && cached.ws.readyState === WebSocket.OPEN) {
      console.log('[term] cache HIT name=', name, 'ws.readyState=', cached.ws.readyState, 'xterm.element parent=', cached.xterm.element?.parentElement?.id);
      termXterm = cached.xterm;
      termFitAddon = cached.fitAddon;
      termWS = cached.ws;
      termContainer = cached.container;
      termCurrentWorkspaceId = workspaceId;
      _termCache.delete(scopeKey);
      _termShowPane(termContainer);
      _termEnableWebgl();
      try { termFitAddon.fit(); } catch {}
      _termFocusActiveSoon();
      // Do NOT send resize here — SIGWINCH causes Claude TUI to redraw and
      // clear any in-progress input. ResizeObserver on the container handles
      // genuine size changes once the pane is visible.
      const meta = termSessions.find(s => s.name === name);
      const badge = document.getElementById('termAutoBadge');
      if (badge) badge.style.display = (meta && meta.auto) ? 'inline-block' : 'none';
      termSetStatus('live', 'attached · ' + name);
      termRenderSessionList();
      return;
    }

    // --- Cache hit, WS closed: keep xterm/container, reconnect WS only ---
    if (cached) {
      console.log('[term] cache STALE — falling through, ws.readyState=', cached.ws.readyState);
      termXterm = cached.xterm;
      termFitAddon = cached.fitAddon;
      termContainer = cached.container;
      termCurrentWorkspaceId = workspaceId;
      _termCache.delete(scopeKey);
      _termShowPane(termContainer);
      _termEnableWebgl();
      try { termFitAddon.fit(); } catch {}
      _termFocusActiveSoon();
      // Reconnect without clobbering claude's in-progress input: see _openWS.
      _openWS(false);
      return;
    }

    // --- Cache miss: fresh container + xterm + WebSocket ---
    // Dispose any lingering module-level xterm (e.g. left over from a dropped WS
    // reconnect where termCurrentSession was nulled before termAttach was called).
    console.log('[term] cache MISS — fresh connect for', name);
    if (termXterm) { try { termXterm.dispose(); } catch {} termXterm = null; }
    if (termContainer) { try { termContainer.remove(); } catch {} termContainer = null; }
    termEnsureXterm();
    if (!termXterm) return;
    const myContainer = _termMakeContainer();
    myContainer.classList.add('term-pane');
    termContainer = myContainer;
    termXterm.open(myContainer);
    // Debounced ResizeObserver: only send resize when rows/cols actually change.
    let _resizeTimer = null;
    let _lastRows = 0, _lastCols = 0;
    const myRO = new ResizeObserver(() => {
      clearTimeout(_resizeTimer);
      _resizeTimer = setTimeout(() => {
        // Only the ACTIVE pane may drive fit/resize. This observer also
        // fires when ITS container is hidden by a session switch (size →
        // 0x0); at that point the module-level termFitAddon/termWS belong
        // to a DIFFERENT session and must not be poked from here.
        if (termContainer !== myContainer) return;
        try { termFitAddon.fit(); } catch {}
        if (termXterm && (termXterm.rows !== _lastRows || termXterm.cols !== _lastCols)) {
          _lastRows = termXterm.rows;
          _lastCols = termXterm.cols;
          termSendResize();
        }
      }, 100);
    });
    myRO.observe(myContainer);
    termXterm.onData(data => {
      if (termCurrentSession !== name || termCurrentWorkspaceId !== workspaceId) return;
      if (termContainer !== myContainer) return;
      if (termWS && termWS.readyState === WebSocket.OPEN) {
        termWS.send(JSON.stringify({ type: 'input', data }));
      }
    });
    _termShowPane(myContainer);
    _termFocusActiveSoon(myContainer, termXterm);
    // Fit BEFORE dialing the WebSocket so _openWS can pass the real
    // geometry in the URL and tmux attaches at the right size from byte
    // one (no 80x24 → real-size double reflow). Prime the RO's last-seen
    // dims so its initial fire doesn't send a redundant resize.
    try {
      termFitAddon.fit();
      _lastRows = termXterm.rows;
      _lastCols = termXterm.cols;
    } catch {}
    // Enable the GPU renderer once the pane is visible (the addon reads
    // cell metrics from the live DOM, so it must come after display:block).
    _termEnableWebgl();
    termXterm.clear();
    _openWS(true);
  }

  function termSetStatus(state, text) {
    const el = document.getElementById('termStatus');
    const t = document.getElementById('termStatusText');
    if (!el || !t) return;
    el.classList.remove('live', 'err');
    if (state === 'live') el.classList.add('live');
    else if (state === 'err') el.classList.add('err');
    t.textContent = text;
    _termRenderActiveSessionHeader();
  }

  // Deep-link support: #/nb?path=workspaces/<id>/<rest>.ipynb
  // The fragment-style URL points at a notebook directly. We resolve the
  // owning workspace, plant the doc in last-opened state so the existing
  // `selectRepo → getLastWorkspaceDoc → openWorkspaceDoc` flow opens it, and
  // rewrite the URL to the canonical ?workspace=<abs> form for refreshes.
  let _nbHashWorkspace = null;
  (function consumeNbHash() {
    const hash = location.hash || '';
    const m = hash.match(/^#\/nb\?(.*)$/);
    if (!m) return;
    const params = new URLSearchParams(m[1]);
    const rel = params.get('path') || '';
    const seg = rel.match(/^(?:workspaces|projects)\/([^/]+)\/(.+\.ipynb)$/i);
    if (!seg) return;
    const workspaceId = seg[1];
    const docPath = seg[2];
    if (workspaceId === '.' || workspaceId === '..'
        || docPath.split('/').some((part) => part === '..')) return;
    // A cross-vault workspace tab already carries its absolute workspace in
    // ?workspace=. Prefer that authoritative owner over the shell vault;
    // otherwise a Local notebook opened while the SSD vault is active is
    // remembered under the wrong workspace and silently falls back to read-only.
    const explicitWorkspace = _normalizeAbsolutePath(urlWorkspace);
    const workspaceFolder = rel.split('/')[0];
    const workspaceSuffix = `/${workspaceFolder}/${workspaceId}`;
    let absWorkspace = explicitWorkspace && explicitWorkspace.endsWith(workspaceSuffix)
      ? explicitWorkspace : null;
    if (!absWorkspace) {
      const vaultRoot = _normalizeAbsolutePath(VAULT_ROOT);
      if (!vaultRoot) return;
      const rootPrefix = vaultRoot === '/' ? '/' : vaultRoot + '/';
      absWorkspace = rootPrefix + workspaceFolder + '/' + workspaceId;
    }
    setLastWorkspaceDoc(absWorkspace, docPath);
    _nbHashWorkspace = absWorkspace;
    const url = new URL(location.href);
    url.hash = '';
    url.searchParams.set('workspace', absWorkspace);
    history.replaceState(null, '', url);
  })();
  const _effectiveWorkspace = urlWorkspace || _nbHashWorkspace;

  // Compatibility handler for cached markup that still calls goHome().
  function goHome(ev) {
    if (ev) ev.preventDefault();
    goToProductivity();
  }

  // ─── In-page navigation (workspace tabs + dashboard cards) ────────────────
  //
  // Workspace-tab clicks USED to do `window.location.href = '/?workspace=…'`
  // which is a full page reload — the entire JS scope (including
  // `_termCache`) was destroyed every time the user moved between workspaces,
  // and the brief blank-screen flash on every click was a real UX
  // annoyance. These helpers do the same logical navigation in-page via
  // history.pushState + view-class swap, mirroring the goHome pattern.
  //
  // Bonus: `_termCache` survives now, so returning to a workspace the user
  // recently visited is a cache HIT — the WS + xterm buffer come back
  // intact instead of the user seeing a fresh tmux re-attach replay.
  // Look for `[term] cache HIT` in DevTools to confirm on a return visit.

  // Park the previous view's state cleanly before swapping. Detaches the
  // active terminal session into _termCache (soft-park, NOT eviction) and
  // strips the mutually-exclusive body classes; the destination init will
  // assert its own.
  function _swapViewState({preserveHomeTerminal = false} = {}) {
    if ((!preserveHomeTerminal || !_termHomeViewActive()) && typeof termDetach === 'function') termDetach(true);
    document.body.classList.remove(
      'cerebro-active', 'self-active', 'assistant-active', 'vault-active',
      'workspace-active', 'has-diff-tabs',
    );
    currentWorkspace = null;
    currentRepo = null;
    currentRepoInWorkspace = null;
    const dt = document.getElementById('diffTabs');
    if (dt) dt.style.display = 'none';
  }

  // Navigate to a real workspace by absolute path. `replace` is true when
  // called from popstate (browser already updated URL — replaceState would
  // create a duplicate; do nothing).
  function goToWorkspace(path, opts = {}) {
    if (!path) return;
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.set('workspace', path);
      url.searchParams.delete('repo');
      url.searchParams.delete('view');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('vault');
      url.searchParams.delete('subview');
      history.pushState({nav: 'workspace', path}, '', url.pathname + url.search + url.hash);
    }
    const dispatch = () => {
      const workspace = (workspacesList || []).find(p => p.path === path);
      if (workspace) selectRepo(workspace.path);
    };
    if (workspacesList && workspacesList.length) {
      dispatch();
    } else {
      fetchRepos().then(workspaces => { workspacesList = workspaces; dispatch(); });
    }
  }

  // Navigate to a workspace by its id (CLAUDE-style /p/<id> URLs in the DOM).
  // Translates to a path lookup and delegates to goToWorkspace. Falls back
  // to the legacy server-side redirect if the workspace isn't in workspacesList.
  function goToWorkspaceById(pid, opts = {}) {
    if (!pid) return;
    const fromCache = (workspacesList || []).find(p => p.name === pid);
    if (fromCache && fromCache.path) { goToWorkspace(fromCache.path, opts); return; }
    fetchRepos().then(workspaces => {
      workspacesList = workspaces;
      const workspace = workspaces.find(p => p.name === pid);
      if (workspace && workspace.path) goToWorkspace(workspace.path, opts);
      else window.location.href = '/p/' + encodeURIComponent(pid); // genuinely missing
    });
  }

  // Minimal YAML-frontmatter parser for `.md` files. Handles plain
  // `key: value`, folded blocks (`>-`/`>`), and literal blocks (`|`/`|-`).
  // Indented continuation lines belong to the most recent key. Returns
  // ({fm: {key: string}}, body: remaining markdown).
  function _parseFrontmatter(text) {
    const m = text.match(/^---\s*\n([\s\S]*?)\n---\s*\n?/);
    if (!m) return { fm: {}, body: text };
    const fmText = m[1];
    const body = text.slice(m[0].length);
    const fm = {};
    let currentKey = null;
    let currentValue = '';
    let folded = false;
    let literal = false;
    const commit = () => {
      if (currentKey) fm[currentKey] = currentValue.trim();
    };
    for (const line of fmText.split('\n')) {
      const keyMatch = line.match(/^([a-zA-Z0-9_-]+):\s*(.*)$/);
      if (keyMatch && !/^\s/.test(line)) {
        commit();
        currentKey = keyMatch[1];
        let val = keyMatch[2];
        folded = false;
        literal = false;
        if (val === '>-' || val === '>') { folded = true; val = ''; }
        else if (val === '|-' || val === '|') { literal = true; val = ''; }
        currentValue = val;
      } else if (currentKey) {
        const trimmed = line.replace(/^\s+/, '');
        if (currentValue === '') currentValue = trimmed;
        else if (folded) currentValue += ' ' + trimmed;
        else if (literal) currentValue += '\n' + trimmed;
        else currentValue += ' ' + trimmed;
      }
    }
    commit();
    return { fm, body };
  }

  // Renders the parsed frontmatter as a compact metadata block above the
  // markdown body. Plain key: value rows, monospace, muted background.
  function _renderFrontmatterBlock(fm) {
    const keys = Object.keys(fm);
    if (!keys.length) return '';
    const rows = keys.map(k => {
      return `<div style="margin:3px 0"><span style="color:var(--text-secondary);font-weight:600">${esc(k)}:</span> <span style="color:var(--text-primary)">${esc(fm[k])}</span></div>`;
    }).join('');
    return `<div class="fm-block" style="margin:0 0 24px;padding:12px 16px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:6px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;line-height:1.6;white-space:normal">${rows}</div>`;
  }

  // Renders any monorepo-relative "shared" file inline in the workspace doc
  // pane — used by Meta sidebar entries for `workspaces/CLAUDE.md`
  // and any file under the shared `.claude/`. For `.md` we use the same
  // marked.js client renderer the workspace doc pane uses (so styling
  // matches the rest of the UI); for `.json/.csv` we use the same
  // viewers Cerebro uses; for `.html` we get the rendered/code toggle.
  async function openSharedFile(path) {
    if (!currentWorkspace) return;
    const content = document.getElementById('content');
    if (!content) return;
    // Highlight whichever Meta entry corresponds to this path. The CLAUDE.md
    // entry has a fixed label; other shared files match by trailing filename.
    const lastSeg = path.split('/').pop();
    document.querySelectorAll('.sidebar-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar-file').forEach(el => {
      const t = el.textContent.trim();
      if (t.endsWith(lastSeg) || (path.endsWith('workspaces/CLAUDE.md') && t.includes('CLAUDE.md (shared)'))) {
        el.classList.add('active');
      }
    });
    content.innerHTML = '<div class="loading">Loading…</div>';

    const isMd = /\.(md|markdown)$/i.test(path);
    const isJson = /\.json$/i.test(path);
    const isCsv = /\.csv$/i.test(path);
    const isHtml = /\.(html|htm)$/i.test(path);

    const header = `
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid var(--border)">
        <span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(path)} <span style="opacity:.6">— shared</span></span>
        <a href="/view?path=${encodeURIComponent(path)}" target="_blank" style="font-size:11px;color:var(--text-dim)">open in new tab ↗</a>
      </div>`;

    try {
      if (isHtml) {
        // Reuse the same HTML toggle pattern as in-workspace HTML files —
        // sticky pref via the shared `htmlView:` localStorage namespace.
        const wrapper = document.createElement('div');
        wrapper.style.padding = '24px';
        wrapper.innerHTML = header;
        const innerHost = document.createElement('div');
        wrapper.appendChild(innerHost);
        content.innerHTML = '';
        content.appendChild(wrapper);
        const mode = getHtmlViewPref(path);
        _sharedRenderHtml(innerHost, path, mode);
        return;
      }

      const r = await fetch('/api/cerebro/file?path=' + encodeURIComponent(path));
      if (!r.ok) {
        const msg = await r.json().catch(() => ({}));
        content.innerHTML = `<div class="no-repo"><p>Error: ${esc(msg.detail || r.statusText)}</p></div>`;
        return;
      }
      const body = await r.json();
      const raw = body.content || '';
      await Promise.all([
        isMd ? ensureMarked().catch(() => {}) : Promise.resolve(),
        (isJson || (!isMd && !isCsv)) ? ensureHighlight().catch(() => {}) : Promise.resolve(),
      ]);

      let rendered = '';
      if (isMd) {
        try {
          // Skill SKILL.md files start with YAML frontmatter (name +
          // description). Show that as a compact metadata block so it
          // doesn't render as a giant paragraph; pass only the body to
          // marked so headings/code/lists look like any other .md.
          const { fm, body } = _parseFrontmatter(raw);
          const fmHtml = _renderFrontmatterBlock(fm);
          rendered = fmHtml + LabMarkdown.render(body);
        } catch (e) {
          rendered = `<pre>${esc(raw)}</pre>`;
        }
      } else if (isJson) {
        let pretty = raw;
        try { pretty = JSON.stringify(JSON.parse(raw), null, 2); } catch {}
        rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow:auto"><code class="language-json">${esc(pretty)}</code></pre>`;
      } else if (isCsv) {
        const rows = cerebroParseCSV(raw);
        rendered = `<div class="doc">${cerebroRenderCSV(rows)}</div>`;
      } else {
        // Code / plain-text fallback. Wrap in <pre><code class="language-…">
        // so the hljs.highlightElement loop below colors it (matches what
        // the JSON branch already does). getHljsLang returns null for
        // unknown extensions; hljs then falls back to plain text without
        // an exception.
        const lang = getHljsLang(path);
        const codeClass = lang ? ` class="language-${lang}"` : '';
        rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow:auto"><code${codeClass}>${esc(raw)}</code></pre>`;
      }

      content.innerHTML = `<div class="workspace-content" style="padding:24px;max-width:900px">${header}${rendered}</div>`;
      if (isMd) renderMermaidBlocks(content);
      if (isCsv) cerebroAttachCSVFilter();
      if (window.hljs) {
        content.querySelectorAll('pre code:not(.language-mermaid)').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
      }
    } catch (e) {
      content.innerHTML = `<div class="no-repo"><p>Error: ${esc(e.message || e)}</p></div>`;
    }
  }

  // HTML render helper used by openSharedFile — mirrors _workspaceRenderHtml
  // but uses the cerebro asset/file endpoints and stays inside the given
  // host element rather than reaching for currentWorkspace's path.
  async function _sharedRenderHtml(host, path, mode) {
    const toolbar = `
      <div style="display:flex;justify-content:flex-end;margin:0 0 8px">
        <span class="html-toolbar" style="display:flex;gap:4px">
          <button class="html-toggle ${mode==='rendered'?'active':''}" data-mode="rendered">🖼 Rendered</button>
          <button class="html-toggle ${mode==='code'?'active':''}" data-mode="code">&lt;/&gt; Code</button>
        </span>
      </div>`;
    if (mode === 'rendered') {
      const src = '/api/cerebro/asset?path=' + encodeURIComponent(path);
      // Same iframe re-mount guard as _workspaceRenderHtml — avoids a white
      // flash on every WS index-updated event.
      const existing = host.querySelector('iframe.html-iframe');
      const activeBtn = host.querySelector('.html-toolbar .html-toggle.active');
      if (existing && existing.getAttribute('src') === src
          && activeBtn && activeBtn.getAttribute('data-mode') === 'rendered') {
        return;
      }
      host.innerHTML = toolbar + `<iframe class="html-iframe" src="${src}" onload="applyIframeDarkMode(this)"></iframe>`;
    } else {
      try {
        const r = await fetch('/api/cerebro/file?path=' + encodeURIComponent(path));
        if (!r.ok) {
          const msg = await r.json().catch(() => ({}));
          host.innerHTML = toolbar + `<p style="color:var(--red)">Error: ${esc(msg.detail || r.statusText)}</p>`;
        } else {
          const body = await r.json();
          await ensureHighlight().catch(() => {});
          host.innerHTML = toolbar + `<pre style="background:var(--bg-secondary);padding:14px;border-radius:6px;overflow:auto"><code class="language-html">${esc(body.content)}</code></pre>`;
          if (window.hljs) {
            host.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
          }
        }
      } catch (e) {
        host.innerHTML = toolbar + `<p style="color:var(--red)">Error: ${esc(e.message || e)}</p>`;
      }
    }
    host.querySelectorAll('.html-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = btn.getAttribute('data-mode');
        if (next === mode) return;
        setHtmlViewPref(path, next);
        _sharedRenderHtml(host, path, next);
      });
    });
  }

  function _fetchCerebroTree({force = false} = {}) {
    const fresh = cerebroTreeData && cerebroTreeData.length
      && (Date.now() - _cerebroTreeFetchedAt) < CEREBRO_TREE_TTL_MS;
    if (!force && fresh) return Promise.resolve(cerebroTreeData);
    if (_cerebroTreePromise) return _cerebroTreePromise;
    _cerebroTreePromise = fetch('/api/cerebro/tree')
      .then(r => r.ok ? r.json() : [])
      .then(tree => {
        cerebroTreeData = tree || [];
        _cerebroTreeFetchedAt = Date.now();
        return cerebroTreeData;
      })
      .finally(() => { _cerebroTreePromise = null; });
    return _cerebroTreePromise;
  }

  async function goToCerebro(initialPath = '', opts = {}) {
    if (!LAB_IS_ADMIN) {
      const data = await fetchVaultCatalog();
      const first = (data.vaults || [])[0];
      if (first) goToVault(first.id, opts);
      return;
    }
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('workspace');
      url.searchParams.delete('repo');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.set('view', 'cerebro');
      if (initialPath) url.searchParams.set('path', initialPath);
      else url.searchParams.delete('path');
      history.pushState({nav: 'cerebro', path: initialPath}, '', url.pathname + url.search + url.hash);
    }
    initCerebro(initialPath);
  }

  async function goToProductivity(opts = {}) {
    if (!LAB_IS_ADMIN) {
      const data = await fetchVaultCatalog();
      const first = (data.vaults || [])[0];
      if (first) goToVault(first.id, opts);
      return;
    }
    _swapViewState({preserveHomeTerminal: true});
    _contextSubView = 'overview';
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('workspace');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('vault');
      url.searchParams.set('view', 'productivity');
      if (opts.subview) url.searchParams.set('subview', opts.subview);
      else url.searchParams.delete('subview');
      history.pushState({nav: 'productivity'}, '', url.pathname + url.search + url.hash);
    }
    initSelf();
    if (opts.subview === 'logs') selfShowLogs();
    else if (opts.subview === 'admin') selfShowAdmin();
    else if (opts.subview === 'code-search') showScopedCodeSearch();
  }

  async function goToAssistant(taskPath = '', opts = {}) {
    if (!LAB_IS_ADMIN) {
      const data = await fetchVaultCatalog();
      const first = (data.vaults || [])[0];
      if (first) goToVault(first.id, opts);
      return;
    }
    _swapViewState();
    const section = opts.subview === 'meetings' ? 'meetings'
      : (opts.subview === 'tasks' || /^tasks-[1-5]$/.test(opts.subview || '') || taskPath ? 'tasks' : 'overview');
    _contextSubView = section;
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('workspace');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('vault');
      url.searchParams.set('view', 'assistant');
      if (section === 'meetings') {
        url.searchParams.set('subview', 'meetings');
        url.searchParams.delete('task');
        if (opts.meeting) url.searchParams.set('meeting', opts.meeting);
        else url.searchParams.delete('meeting');
      } else if (section === 'tasks') {
        url.searchParams.set('subview', 'tasks');
        url.searchParams.delete('meeting');
        if (taskPath) url.searchParams.set('task', taskPath);
        else url.searchParams.delete('task');
      } else {
        url.searchParams.delete('subview');
        url.searchParams.delete('task');
        url.searchParams.delete('meeting');
        url.searchParams.delete('assistant_workspace');
      }
      history.pushState({nav: 'assistant', task: taskPath, meeting: opts.meeting || ''}, '', url.pathname + url.search + url.hash);
    }
    initAssistant(taskPath, opts);
  }

  function goToVault(vaultId, opts = {}) {
    // Backwards compatibility for the old goToVault({replace:true}) form.
    if (vaultId && typeof vaultId === 'object') {
      opts = vaultId;
      vaultId = null;
    }
    vaultId = vaultId
      || _workspaceVaultId(currentWorkspace)
      || (_vaultCurrent && _vaultCurrent.id)
      || currentVaultId;
    if (!vaultId) return;
    _swapViewState({preserveHomeTerminal: true});
    _contextSubView = 'overview';
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('workspace');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('subview');
      url.searchParams.set('view', 'vault');
      url.searchParams.set('vault', vaultId);
      history.pushState({nav: 'vault', vault: vaultId}, '', url.pathname + url.search + url.hash);
    }
    return initVaultView(vaultId);
  }

  // Compatibility entry points for old bookmarks and cached inline handlers.
  // The standalone surfaces are retired; both now land in Productivity.
  function goToLogs(opts = {}) {
    return goToProductivity({replace: !!opts.replace, subview: 'logs'});
  }
  function goToCodeSearch(opts = {}) {
    goToProductivity({replace: !!opts.replace, subview: 'code-search'});
  }
  window.goToLogs = goToLogs;
  window.goToCodeSearch = goToCodeSearch;

  // Browser back/forward → re-run the same dispatch the initial-load
  // chain runs, but with `{replace: true}` so we don't push duplicate
  // entries on top of the history state the browser just restored.
  window.addEventListener('popstate', () => {
    const params = new URLSearchParams(location.search);
    const workspace = params.get('workspace');
    const repo = params.get('repo');
    const view = params.get('view');
    const cerebroPath = params.get('path') || '';
    if (workspace) {
      goToWorkspace(workspace, {replace: true});
    } else if (view === 'cerebro') {
      goToCerebro(cerebroPath, {replace: true});
    } else if (view === 'assistant') {
      goToAssistant(params.get('task') || '', {
        replace: true,
        subview: params.get('subview') || '',
        meeting: params.get('meeting') || '',
        workspace: params.get('assistant_workspace') || '',
      });
    } else if (view === 'productivity') {
      goToProductivity({replace: true, subview: params.get('subview') || null});
    } else if (view === 'vault') {
      goToVault(params.get('vault') || currentVaultId, {replace: true});
    } else if (view === 'code-search') {
      goToCodeSearch({replace: true});
    } else if (view === 'logs') {
      goToLogs({replace: true});
    } else if (repo) {
      _swapViewState();
      fetchRepos().then(workspaces => {
        workspacesList = workspaces;
        const workspace = workspaces.find(p => p.repos.some(r => r.path === repo));
        if (workspace) selectRepo(workspace.path);
      });
    } else {
      goToProductivity({replace: true});
    }
  });

  function escapeHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  // ─── Dashboard: Servers section ─────────────────────────────────────────
  // GET /api/servers → {"servers": [{workspace_id, vault, path, port,
  // state: "running"|"starting"|"unhealthy"|"stopped", desired, healthy,
  // session_name, attach_command, session_created, restarts, has_stop,
  // health_url}]}. Rows come from every registered vault, sorted
  // (vault, workspace_id) — a workspace id can repeat across vaults, so
  // every lookup/action below is keyed on the (vault, workspace_id) pair,
  // never workspace_id alone. Start/stop/restart post to
  // /api/servers/{vault}/{workspace_id}/{start|stop|restart}.

  // All three Admin sections (#dashKpis, #dashServers, #dashTerms) render
  // inside the active Productivity content host.
  function dashSectionEl(id) {
    const host = document.body.classList.contains('self-active')
      ? document.getElementById('content')
      : null;
    return host ? host.querySelector('#' + id) : null;
  }

  function dashSectionHeadHtml(el, label, count) {
    const countHtml = count == null ? '' : `<span class="count">${count}</span>`;
    return `<h2>${label} ${countHtml}</h2>`;
  }

  // ─── Dashboard: KPI strip ────────────────────────────────────────────────
  // One row of stat tiles above Servers/Terminals, derived from the same
  // _dashServersRows/_dashTermsRows the two sections below already fetch —
  // no extra endpoint. Reuses the .s-summary/.s-metric classes from the
  // workbench's own header tiles (Open tasks, Changed files, Tests touched,
  // Last commit) so the strip reads as the same component, not a bolted-on
  // widget. Re-rendered at the end of both dashServersRender and
  // dashTermsRender so a refresh of either section keeps it current.
  function dashKpiTileHtml(label, value, warn) {
    const warnAttr = warn ? ' class="warn"' : '';
    return `<div class="s-metric"><span>${escapeHtml(label)}</span><strong${warnAttr}>${escapeHtml(String(value))}</strong></div>`;
  }

  function dashKpisRender() {
    const el = dashSectionEl('dashKpis');
    if (!el) return;
    const servers = _dashServersAvailable ? (_dashServersRows || []) : [];
    const runningCount = servers.filter(r => r.status === 'running' || r.status === 'starting' || r.status === 'external').length;
    const unhealthyCount = servers.filter(r => r.status === 'unhealthy').length;
    const termRows = _dashTermsRows || [];
    const attachedCount = termRows.filter(s => s.attached).length;
    el.innerHTML = `
      ${dashSectionHeadHtml(el, 'Overview')}
      <div class="s-summary dash-kpis">
        ${dashKpiTileHtml('Servers running', `${runningCount}/${servers.length}`)}
        ${dashKpiTileHtml('Unhealthy', unhealthyCount, unhealthyCount > 0)}
        ${dashKpiTileHtml('Terminals', termRows.length)}
        ${dashKpiTileHtml('Attached', attachedCount)}
      </div>`;
  }

  function dashServerStateWord(row) {
    switch (row.status) {
      case 'running': return 'running';
      case 'starting': return 'starting…';
      case 'unhealthy': return 'unhealthy';
      case 'external': return 'external';
      case 'stopped': return 'stopped';
      default: return row.status || 'unknown';
    }
  }

  // One of "running"/"starting"/"unhealthy"/"external"/"stopped" — drives
  // both the card's left border tint and the status dot. "external" = alive
  // but not started from this dashboard (someone ran it by hand); it gets
  // its own accent-colored treatment (see .srv-card-external/.srv-dot-
  // external) so it reads as "seen, not owned" rather than a managed state.
  // Falls back to "stopped" (neutral border color) for anything else.
  function dashServerStateClass(row) {
    switch (row.status) {
      case 'running': return 'running';
      case 'starting': return 'starting';
      case 'unhealthy': return 'unhealthy';
      case 'external': return 'external';
      default: return 'stopped';
    }
  }

  // "up 2h 14m" / "up 14m" from a unix-seconds timestamp — session_created
  // on the /api/servers row (set once the session is alive, null otherwise).
  function dashFmtUptime(unixSeconds) {
    if (!unixSeconds) return null;
    const diff = Math.max(0, Math.floor(Date.now() / 1000) - unixSeconds);
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    return h > 0 ? `up ${h}h ${m}m` : `up ${m}m`;
  }

  function dashServerCardHtml(row) {
    const pid = row.workspace_id;
    const vault = row.vault || '';
    const key = vault + '/' + pid;
    const pending = _dashServersPending.has(key);
    const cls = dashServerStateClass(row);
    const vaultBadge = vault
      ? `<span class="vault-badge" title="vault: ${escapeHtml(vault)}">${escapeHtml(vault)}</span>`
      : '';
    // Status line carries state via the dot + word pair only — the word
    // itself always renders in a plain text color, never the status color
    // (dataviz rule: color is reserved for the dot).
    const suffixBits = [];
    if (row.status === 'unhealthy' && row.desired === 'running') suffixBits.push('restarting');
    if (row.restarts > 0) suffixBits.push(row.restarts + (row.restarts === 1 ? ' restart' : ' restarts'));
    const suffixHtml = suffixBits.length
      ? `<span class="srv-suffix">· ${escapeHtml(suffixBits.join(' · '))}</span>`
      : '';
    const metaBits = [row.port != null ? ':' + row.port : 'no port'];
    if (row.status === 'running' && row.session_created) metaBits.push(dashFmtUptime(row.session_created));
    else if (row.status === 'stopped') metaBits.push('stopped');
    else if (row.status === 'external') metaBits.push('external');
    // `url` is non-null whenever the server is actually listening (managed
    // or external); fall back to deriving it from the port for older
    // backends that don't send it yet.
    const openUrl = row.url || (row.port != null ? `http://127.0.0.1:${row.port}/` : null);
    const openBtn = openUrl
      ? `<a class="mini-btn" href="${escapeHtml(openUrl)}" target="_blank" rel="noopener" title="Open ${escapeHtml(openUrl)} in a new tab">Open</a>`
      : '';
    const copyBtn = row.attach_command
      ? `<button type="button" class="mini-btn" data-act="copy-attach" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}" data-attach="${escapeHtml(row.attach_command)}" title="Copy tmux attach command: ${escapeHtml(row.attach_command)}">⧉ Copy</button>`
      : '';
    const actionBtns = row.status === 'stopped'
      ? `<button type="button" class="mini-btn primary" data-act="start" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}" ${pending ? 'disabled' : ''}>Start</button>`
      : `<button type="button" class="mini-btn danger" data-act="stop" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}" ${pending ? 'disabled' : ''}>Stop</button>
         <button type="button" class="mini-btn" data-act="restart" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}" ${pending ? 'disabled' : ''}>Restart</button>`;
    const titleAttr = row.path ? ` title="${escapeHtml(row.path)}"` : '';
    return `
      <div class="srv-card srv-card-${cls}" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}"${titleAttr}>
        <div class="srv-card-body">
          <div class="srv-card-head">
            <span class="srv-name">${escapeHtml(pid)}</span>
            ${vaultBadge}
          </div>
          <div class="srv-status-line">
            <span class="srv-dot srv-dot-${cls}"></span>
            <span class="srv-state-word">${escapeHtml(dashServerStateWord(row))}</span>
            ${suffixHtml}
          </div>
          <div class="srv-meta">${escapeHtml(metaBits.join(' · '))}</div>
        </div>
        <div class="srv-card-footer">${openBtn}${copyBtn}${actionBtns}</div>
      </div>`;
  }

  function dashServersRender() {
    const el = dashSectionEl('dashServers');
    if (!el) return;
    if (!_dashServersAvailable) { el.innerHTML = ''; dashKpisRender(); return; }
    const rows = _dashServersRows || [];
    const err = _dashServersActionErr || _dashServersLoadErr;
    const errHtml = err ? `<div class="srv-err on">${escapeHtml(err)}</div>` : '';
    const body = rows.length === 0
      ? '<div class="srv-empty">No workspaces with a server Makefile (server-start target).</div>'
      : `<div class="srv-grid">${rows.map(dashServerCardHtml).join('')}</div>`;
    el.innerHTML = `
      ${dashSectionHeadHtml(el, 'Servers', rows.length)}
      ${errHtml}
      ${body}`;
    dashKpisRender();
  }

  async function dashServersRefresh() {
    try {
      const r = await fetch('/api/servers');
      if (r.status === 404) {
        _dashServersAvailable = false;
        _dashServersLoadErr = null;
      } else if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        _dashServersAvailable = true;
        _dashServersLoadErr = (body && body.detail) || `Failed to load servers (${r.status})`;
      } else {
        const data = await r.json();
        _dashServersAvailable = true;
        _dashServersLoadErr = null;
        _dashServersRows = Array.isArray(data && data.servers) ? data.servers : [];
      }
    } catch (e) {
      // Network hiccup: keep whatever we last had, surface it inline. The
      // fetch itself is already logged to /api/log/client by the wrapper in
      // error-report.js — no need to console.log/error here too.
      _dashServersLoadErr = 'Failed to load servers: ' + e.message;
    }
    dashServersRender();
  }

  async function dashServersOnClick(e) {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    const pid = btn.getAttribute('data-workspace-id');
    const vault = btn.getAttribute('data-vault') || '';
    if (act === 'copy-attach') {
      const cmd = btn.getAttribute('data-attach') || '';
      if (cmd) await _copyToClipboard(cmd, btn);
      return;
    }
    if (!pid || !['start', 'stop', 'restart'].includes(act)) return;
    const key = vault + '/' + pid;
    if (_dashServersPending.has(key)) return;
    _dashServersPending.add(key);
    _dashServersActionErr = null;
    // Optimistic chip flip on Start/Restart: the actual state lags behind
    // the spawned tmux session by a beat, and sitting on "stopped" until
    // the next poll reads as broken. Stop needs no such nudge — the card's
    // own "disabled" state already gives immediate feedback.
    if (act === 'start' || act === 'restart') {
      const row = (_dashServersRows || []).find(r => (r.vault || '') === vault && r.workspace_id === pid);
      if (row) row.status = 'starting';
    }
    dashServersRender();  // disable the card's buttons immediately
    try {
      const url = '/api/servers/' + encodeURIComponent(vault) + '/' + encodeURIComponent(pid) + '/' + act;
      const r = await fetch(url, {method: 'POST'});
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        _dashServersActionErr = (body && body.detail) || `Failed to ${act} ${pid} (${r.status})`;
      }
    } catch (err) {
      _dashServersActionErr = `Failed to ${act} ${pid}: ` + err.message;
    }
    _dashServersPending.delete(key);
    await dashServersRefresh();  // section refreshes right after the response
  }

  // ─── Dashboard: Terminals section ───────────────────────────────────────
  // GET /api/term/sessions — see term.py list_sessions() ~:982. Rows carry
  // {name, created, attached, windows, vault} from tmux plus
  // {workspace_id, logical_name, kind, agent, cwd, created_at, label, summary,
  // attach_command} from the runtime registry. Grouped by (vault,
  // workspace_id) — a workspace id can exist in two vaults, so the group
  // key must carry both; vault-root sessions carry workspace_id
  // "__self__" (SELF_WORKSPACE_ID) and are labeled "vault". Sessions
  // whose workspace_id couldn't be resolved at all (pre-existing orphaned
  // tmux sessions from before a naming-scheme change) fall back to a single
  // "(unassigned)" group with no "Close all" button, since there's no
  // workspace id (or vault) to scope that call to.

  function dashFmtAgo(unixSeconds) {
    if (!unixSeconds) return null;
    const diff = Math.max(0, Math.floor(Date.now() / 1000) - unixSeconds);
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }

  function dashTermGroupKey(s) {
    if (!s.workspace_id) return '__unknown__';
    return (s.vault || '') + '/' + s.workspace_id;
  }

  function dashTermGroupLabel(pid) {
    if (pid === SELF_WORKSPACE_ID) return 'vault';
    if (pid === '__unknown__') return '(unassigned)';
    return pid;
  }

  function dashTermRowHtml(s) {
    const name = s.name;
    const pending = _dashTermsPending.has(name);
    const label = s.logical_name || name;
    const metaBits = [];
    if (s.windows != null) metaBits.push(s.windows + (s.windows === 1 ? ' window' : ' windows'));
    const ago = dashFmtAgo(s.created || s.created_at);
    if (ago) metaBits.push(ago);
    const attachedHtml = s.attached ? '<span class="term-attached" title="a client is attached">attached</span>' : '';
    return `
      <div class="term-row" data-name="${escapeHtml(name)}">
        <span class="term-name">${escapeHtml(label)}</span>
        <span class="term-meta">${escapeHtml(metaBits.join(' · '))}</span>
        ${attachedHtml}
        <button type="button" class="mini-btn danger" data-act="term-close" data-name="${escapeHtml(name)}" data-logical="${escapeHtml(label)}" ${pending ? 'disabled' : ''}>Close</button>
      </div>`;
  }

  function dashTermGroupHtml(key, sessions) {
    const first = sessions[0] || {};
    const pid = first.workspace_id || '__unknown__';
    const vault = first.vault || '';
    const label = dashTermGroupLabel(pid);
    const vaultBadge = (key !== '__unknown__' && vault)
      ? `<span class="vault-badge" title="vault: ${escapeHtml(vault)}">${escapeHtml(vault)}</span>`
      : '';
    const pending = _dashTermsPending.has('group:' + key);
    const closeAllBtn = key === '__unknown__'
      ? ''
      : `<button type="button" class="mini-btn danger" data-act="term-close-all" data-workspace-id="${escapeHtml(pid)}" data-vault="${escapeHtml(vault)}" data-key="${escapeHtml(key)}" ${pending ? 'disabled' : ''}>Close all</button>`;
    return `
      <div class="term-card">
        <div class="term-card-head">
          <span class="term-card-label">${escapeHtml(label)}</span>
          ${vaultBadge}
          <span class="count">${sessions.length}</span>
          ${closeAllBtn}
        </div>
        <div class="term-card-body">${sessions.map(dashTermRowHtml).join('')}</div>
      </div>`;
  }

  function dashTermsRender() {
    const el = dashSectionEl('dashTerms');
    if (!el) return;
    const rows = _dashTermsRows || [];
    const errHtml = _dashTermsErr ? `<div class="term-err on">${escapeHtml(_dashTermsErr)}</div>` : '';
    let body;
    if (rows.length === 0) {
      body = '<div class="term-empty">No active terminal sessions.</div>';
    } else {
      const groups = new Map();
      for (const s of rows) {
        const key = dashTermGroupKey(s);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(s);
      }
      body = `<div class="term-grid">${Array.from(groups.entries()).map(([key, sessions]) => dashTermGroupHtml(key, sessions)).join('')}</div>`;
    }
    el.innerHTML = `
      ${dashSectionHeadHtml(el, 'Terminals', rows.length)}
      ${errHtml}
      ${body}`;
    dashKpisRender();
  }

  async function dashTermsRefresh() {
    try {
      const r = await fetch('/api/term/sessions');
      if (!r.ok) {
        _dashTermsErr = `Failed to load terminal sessions (${r.status})`;
      } else {
        const data = await r.json();
        _dashTermsRows = Array.isArray(data) ? data : [];
        _dashTermsErr = null;
      }
    } catch (e) {
      _dashTermsErr = 'Failed to load terminal sessions: ' + e.message;
    }
    dashTermsRender();
  }

  async function dashTermsOnClick(e) {
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.getAttribute('data-act');
    if (act === 'term-close') {
      const name = btn.getAttribute('data-name');
      const logical = btn.getAttribute('data-logical') || name;
      if (!name || _dashTermsPending.has(name)) return;
      let msg = `Close terminal session "${logical}"? It will stay closed after reload.`;
      if (logical === 'server') {
        msg += ' This is a managed server session; the server will be marked stopped.';
      }
      if (!confirm(msg)) return;
      _dashTermsPending.add(name);
      dashTermsRender();
      try {
        await fetch('/api/term/sessions/' + encodeURIComponent(name), {method: 'DELETE'});
      } catch (err) { /* best-effort, matches termKillCurrent */ }
      _dashTermsPending.delete(name);
      await dashTermsRefresh();
      if (typeof workspaceTabsRefresh === 'function') workspaceTabsRefresh();
    } else if (act === 'term-close-all') {
      const pid = btn.getAttribute('data-workspace-id');
      const vault = btn.getAttribute('data-vault') || '';
      const key = btn.getAttribute('data-key') || (vault + '/' + pid);
      if (!pid || _dashTermsPending.has('group:' + key)) return;
      const sessions = (_dashTermsRows || []).filter(s => dashTermGroupKey(s) === key);
      const label = dashTermGroupLabel(pid);
      if (!confirm(`Close all ${sessions.length} terminal sessions for ${label}? This kills their tmux sessions.`)) return;
      _dashTermsPending.add('group:' + key);
      dashTermsRender();
      try {
        await fetch('/api/term/sessions/workspace/' + encodeURIComponent(pid) + '?vault=' + encodeURIComponent(vault), {method: 'DELETE'});
      } catch (err) { /* best-effort */ }
      _dashTermsPending.delete('group:' + key);
      await dashTermsRefresh();
      if (typeof workspaceTabsRefresh === 'function') workspaceTabsRefresh();
    }
  }

  // ─── Dashboard: shared poll loop for all three sections above ───────────
  // One interval, fetching both endpoints in parallel every 5s (the KPI
  // strip piggybacks on the same two responses — see dashKpisRender).
  // Self-cleans when #dashServers leaves the DOM (view navigated away /
  // dashboard re-rendered) so navigating home repeatedly never stacks
  // intervals — dashStartPolling also clears any prior timer up front,
  // belt-and-braces.

  function dashStopPolling() {
    if (_dashPollTimer) { clearInterval(_dashPollTimer); _dashPollTimer = null; }
  }

  async function dashPollTick() {
    if (!dashSectionEl('dashServers')) { dashStopPolling(); return; }
    // Pause while the browser tab itself isn't visible — no point hammering
    // tmux/health-check calls for a dashboard nobody's looking at. The
    // visibilitychange listener below (registered once, at init) picks the
    // poll back up immediately on return instead of waiting out the rest
    // of the 5s interval.
    if (document.hidden) return;
    await Promise.all([dashServersRefresh(), dashTermsRefresh()]);
  }

  function dashStartPolling() {
    dashStopPolling();
    _dashPollTimer = setInterval(dashPollTick, 5000);
  }

  // ─── Workspace server bar (below top tabs, above diff tabs) ───
  // Deliberately narrow: workspace planning metadata belongs in workspace files,
  // so this chrome only exposes the local-server configuration.

  async function refreshAttrsBar() {
    const bar = document.getElementById('workspaceAttrsBar');
    if (!bar) return;
    if (!currentWorkspace || !currentWorkspace.is_workspace) {
      bar.innerHTML = '';
      document.body.classList.remove('workspace-active');
      return;
    }
    const pid = currentWorkspace.name;
    const workspacePath = currentWorkspace.path;

    // Warm switch: paint synchronously from the last-known workspace record.
    // Background reconcile re-paints only on change. Cache miss falls
    // through to the foreground fetch below.
    const cached = _workspaceAttrsCache.get(workspacePath);
    if (cached) {
      _renderAttrsBarFromRecord(bar, pid, cached);
      Promise.resolve().then(async () => {
        try {
          const r = await fetch('/api/workspace-info?path=' + encodeURIComponent(workspacePath));
          if (!r.ok) return;
          const fresh = await r.json();
          const prev = _workspaceAttrsCache.get(workspacePath);
          _workspaceAttrsCache.set(workspacePath, fresh);
          if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
          if (!currentWorkspace || currentWorkspace.path !== workspacePath) return;
          _renderAttrsBarFromRecord(bar, pid, fresh);
        } catch {}
      });
      return;
    }

    let p = null;
    try {
      const r = await fetch('/api/workspace-info?path=' + encodeURIComponent(workspacePath));
      if (r.ok) p = await r.json();
    } catch {}
    if (!p) { bar.innerHTML = ''; return; }
    _workspaceAttrsCache.set(workspacePath, p);
    _renderAttrsBarFromRecord(bar, pid, p);
  }

  // Extracted from refreshAttrsBar so both the cold and warm-switch
  // paths share one render. Pure DOM write — no network, no state
  // mutation. Reads only the server declarations on workspace record `p`.
  function _renderAttrsBarFromRecord(bar, pid, p) {
    const proxyCount = Array.isArray(p.proxies) ? p.proxies.length : 0;
    const proxiesLabel = proxyCount ? `${proxyCount} server${proxyCount === 1 ? '' : 's'}` : 'add server';
    const proxiesCls = proxyCount ? '' : 'empty';

    bar.innerHTML = `
      <span class="ab-spacer"></span>
      <span class="ab-chip" data-act="proxies" title="manage proxied local servers for this workspace">&#x1F310; <span class="v ${proxiesCls}">${escapeHtml(proxiesLabel)}</span></span>
    `;
    bar.querySelectorAll('[data-act]').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const act = chip.getAttribute('data-act');
        if (act === 'proxies') openProxiesModal();
      });
    });
  }

  // ─── Proxies modal (manage workspace-root servers.json from the UI) ───
  // Opened from the attrs-bar "Servers" chip. Saved proxies render as
  // management cards; fields only become editable after an explicit Edit.
  // Optional make commands power Start / Restart and Stop controls through
  // routes/proxy.py. Saving migrates legacy workspace.json proxies to servers.json.
  let _proxiesEscHandler = null;
  let _proxiesRowSeq = 0;
  let _proxiesWorkspacePath = null;
  let _proxiesWorkspaceId = null;
  let _proxiesVaultId = null;
  let _proxiesListDirty = false;
  let _proxiesHasConfigFile = false;

  async function openProxiesModal() {
    if (!currentWorkspace || !currentWorkspace.is_workspace) return;
    const overlay = document.getElementById('proxiesModal');
    if (!overlay) return;
    _proxiesWorkspacePath = currentWorkspace.path;
    _proxiesWorkspaceId = currentWorkspace.name;
    _proxiesVaultId = _workspaceVaultId(currentWorkspace);
    const workspacePath = _proxiesWorkspacePath;
    const err = document.getElementById('proxiesError');
    const addBtn = document.getElementById('proxiesAddBtn');
    const saveBtn = document.getElementById('proxiesSaveBtn');
    const createBtn = document.getElementById('proxiesCreateBtn');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    if (addBtn) addBtn.disabled = true;
    if (saveBtn) saveBtn.disabled = false;
    _proxiesHasConfigFile = false;
    if (createBtn) createBtn.disabled = true;
    const cached = _workspaceSidebarCache.get(currentWorkspace.path);
    const proxies = (cached && Array.isArray(cached.proxies)) ? cached.proxies : [];
    _renderProxiesRows(proxies);
    overlay.classList.add('active');
    _proxiesEscHandler = (ev) => { if (ev.key === 'Escape') closeProxiesModal(); };
    document.addEventListener('keydown', _proxiesEscHandler);
    await reloadProxyConfig(true);
    if (workspacePath === _proxiesWorkspacePath && addBtn) addBtn.disabled = false;
  }

  function _serverConfigUrl(endpoint) {
    const params = new URLSearchParams({workspace_id: _proxiesWorkspaceId || ''});
    if (_proxiesVaultId) params.set('vault', _proxiesVaultId);
    return `${endpoint}?${params.toString()}`;
  }

  function _setProxyConfigSource(text) {
    const source = document.getElementById('proxiesConfigSource');
    if (source) source.textContent = text;
  }

  function _proxyRowsAreDirty() {
    return _proxiesListDirty || !!document.querySelector('#proxiesRows .proxies-card[data-dirty="1"]');
  }

  function _syncProxyCreateButton(busy = false) {
    const button = document.getElementById('proxiesCreateBtn');
    if (!button) return;
    button.disabled = busy || _proxiesHasConfigFile;
    button.textContent = _proxiesHasConfigFile ? 'servers.json exists' : '+ Create servers.json';
  }

  async function reloadProxyConfig(initialLoad = false) {
    if (!_proxiesWorkspaceId) return false;
    if (!initialLoad && _proxyRowsAreDirty() && !confirm('Discard unsaved server changes and reload servers.json?')) return false;
    const workspacePath = _proxiesWorkspacePath;
    const err = document.getElementById('proxiesError');
    const reloadBtn = document.getElementById('proxiesReloadBtn');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    if (reloadBtn) reloadBtn.disabled = true;
    _syncProxyCreateButton(true);
    _setProxyConfigSource('loading…');
    try {
      const r = await fetch(_serverConfigUrl('/api/server-config'));
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `GET server-config → ${r.status}`);
      if (workspacePath !== _proxiesWorkspacePath || workspacePath !== (currentWorkspace && currentWorkspace.path)) return false;
      _renderProxiesRows(Array.isArray(body.servers) ? body.servers : []);
      _proxiesHasConfigFile = body.source === 'servers.json';
      if (_proxiesHasConfigFile) _setProxyConfigSource('servers.json · automatic');
      else if (body.is_legacy) _setProxyConfigSource(`${body.source} · legacy; Create or Save writes servers.json`);
      else _setProxyConfigSource('No servers.json yet · create the template');
      return true;
    } catch (e) {
      _setProxyConfigSource('Could not load config');
      if (err) { err.textContent = `Could not refresh servers: ${e.message || e}`; err.classList.add('on'); }
      return false;
    } finally {
      if (workspacePath === _proxiesWorkspacePath) {
        if (reloadBtn) reloadBtn.disabled = false;
        _syncProxyCreateButton(false);
      }
    }
  }

  async function createProxyConfigTemplate() {
    if (!_proxiesWorkspaceId) return;
    const err = document.getElementById('proxiesError');
    const reloadBtn = document.getElementById('proxiesReloadBtn');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    if (_proxyRowsAreDirty()) {
      if (err) { err.textContent = 'Save or reload the current edits before creating servers.json.'; err.classList.add('on'); }
      return;
    }
    const {proxies, errors} = _collectProxiesFromRows();
    if (errors.length) {
      if (err) { err.textContent = errors.join(' · '); err.classList.add('on'); }
      return;
    }
    if (reloadBtn) reloadBtn.disabled = true;
    _syncProxyCreateButton(true);
    _setProxyConfigSource('Creating servers.json…');
    try {
      const r = await fetch(_serverConfigUrl('/api/server-config'), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({servers: proxies}),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `Could not create servers.json (${r.status})`);
      _proxiesHasConfigFile = true;
      _renderProxiesRows(Array.isArray(body.servers) ? body.servers : []);
      _setProxyConfigSource('servers.json · template ready for your agent');
      _workspaceSidebarCache.delete(_proxiesWorkspacePath);
      _workspaceAttrsCache.delete(_proxiesWorkspacePath);
    } catch (e) {
      _setProxyConfigSource('Could not create servers.json');
      if (err) { err.textContent = e.message || String(e); err.classList.add('on'); }
    } finally {
      if (reloadBtn) reloadBtn.disabled = false;
      _syncProxyCreateButton(false);
    }
  }

  function closeProxiesModal() {
    const overlay = document.getElementById('proxiesModal');
    if (overlay) overlay.classList.remove('active');
    if (_proxiesEscHandler) {
      document.removeEventListener('keydown', _proxiesEscHandler);
      _proxiesEscHandler = null;
    }
  }

  function _renderProxiesRows(proxies, dirty = false) {
    const host = document.getElementById('proxiesRows');
    if (!host) return;
    let html = '';
    if (!proxies || proxies.length === 0) {
      html = `<div class="proxies-empty">No servers configured yet. Add one to expose a local app and optionally manage it with make commands.</div>`;
    } else {
      proxies.forEach(p => { html += _proxyRowHtml(p || {}, false); });
    }
    host.innerHTML = html;
    _proxiesListDirty = dirty;
    if (dirty) {
      host.querySelectorAll('.proxies-card[data-row-id]').forEach(row => {
        row.dataset.dirty = '1';
        _syncProxyRowSummary(row);
      });
    }
  }

  function _proxyRowHtml(p, editing) {
    const id = 'pr-' + (++_proxiesRowSeq);
    const directChecked = (p.mode === 'direct') ? 'checked' : '';
    const name = String(p.name || '');
    const label = String(p.label || name || 'Unnamed server');
    const host = String(p.host || 'localhost');
    const port = String(p.port == null ? '' : p.port);
    const path = String(p.path || '/');
    const startCommand = String(p.start_command || '');
    const stopCommand = String(p.stop_command || '');
    const endpoint = `${host}${port ? ':' + port : ''}${path.startsWith('/') ? path : '/' + path}`;
    const startDisabled = startCommand.trim() ? '' : 'disabled';
    const stopDisabled = stopCommand.trim() ? '' : 'disabled';
    return `
      <article class="proxies-card${editing ? ' editing' : ''}" data-row-id="${id}"${editing ? ' data-dirty="1"' : ''}>
        <div class="proxies-view">
          <div class="proxies-identity">
            <span class="proxies-server-icon" aria-hidden="true">&#x1F310;</span>
            <span class="proxies-title-stack"><strong data-display="label">${escapeHtml(label)}</strong><code data-display="name">${escapeHtml(name)}</code></span>
          </div>
          <div class="proxies-endpoint">
            <span class="proxies-endpoint-line" data-display="endpoint">${escapeHtml(endpoint)}</span>
            <span class="proxies-mode" data-display="mode">${p.mode === 'direct' ? 'direct' : 'proxied'}</span>
          </div>
          <div class="proxies-command-list">
            <div class="proxies-command-row${startCommand ? '' : ' missing'}" data-command-row="start"><span>Start</span><code data-display="start-command">${escapeHtml(startCommand || 'Not configured')}</code></div>
            <div class="proxies-command-row${stopCommand ? '' : ' missing'}" data-command-row="stop"><span>Stop</span><code data-display="stop-command">${escapeHtml(stopCommand || 'Not configured')}</code></div>
          </div>
          <div class="proxies-actions">
            <button type="button" class="proxies-start" data-proxy-action="start" ${startDisabled} onclick="proxyServerAction('${id}', 'start')">&#x25B6; Start / Restart</button>
            <button type="button" class="proxies-stop" data-proxy-action="stop" ${stopDisabled} onclick="proxyServerAction('${id}', 'stop')">&#x25A0; Stop</button>
            <button type="button" onclick="editProxyRow('${id}')">&#x270E; Edit</button>
          </div>
          <div class="proxies-action-status" aria-live="polite"></div>
        </div>
        <div class="proxies-editor">
          <div class="proxies-editor-grid">
            <label>Name <input type="text" data-field="name" value="${escapeHtml(name)}" placeholder="frontend" /></label>
            <label>Label <input type="text" data-field="label" value="${escapeHtml(String(p.label || ''))}" placeholder="Optional display name" /></label>
            <label>Host <input type="text" data-field="host" value="${escapeHtml(String(p.host || ''))}" placeholder="localhost" /></label>
            <label>Port <input type="text" data-field="port" value="${escapeHtml(port)}" placeholder="3000" inputmode="numeric" /></label>
            <label>Path <input type="text" data-field="path" value="${escapeHtml(String(p.path || ''))}" placeholder="/" /></label>
          </div>
          <div class="proxies-command-grid">
            <label>Start / restart command <span class="hint">Optional · must begin with make</span><input type="text" data-field="start-command" value="${escapeHtml(startCommand)}" placeholder="make server-start" /></label>
            <label>Stop command <span class="hint">Optional · must begin with make</span><input type="text" data-field="stop-command" value="${escapeHtml(stopCommand)}" placeholder="make server-stop" /></label>
          </div>
          <label class="proxies-direct" title="Iframe directly to host:port — skips the Lab proxy."><input type="checkbox" data-field="direct" ${directChecked} /> Open iframe directly at host:port</label>
          <div class="proxies-editor-actions">
            <button type="button" class="proxies-del" onclick="removeProxyRow('${id}')">Remove server</button>
            <button type="button" onclick="finishProxyRowEdit('${id}')">Done editing</button>
          </div>
        </div>
      </article>`;
  }

  function addProxyRow() {
    const host = document.getElementById('proxiesRows');
    if (!host) return;
    _proxiesListDirty = true;
    const empty = host.querySelector('.proxies-empty');
    if (empty) empty.remove();
    host.insertAdjacentHTML('beforeend', _proxyRowHtml({}, true));
    const rows = host.querySelectorAll('.proxies-card[data-row-id]');
    const last = rows[rows.length - 1];
    if (last) {
      const nameInput = last.querySelector('input[data-field="name"]');
      if (nameInput) nameInput.focus();
    }
  }

  function editProxyRow(rowId) {
    const row = document.querySelector(`#proxiesRows .proxies-card[data-row-id="${rowId}"]`);
    if (!row) return;
    _proxiesListDirty = true;
    row.dataset.dirty = '1';
    _syncProxyRowSummary(row);
    row.classList.add('editing');
    const nameInput = row.querySelector('input[data-field="name"]');
    if (nameInput) nameInput.focus();
  }

  function _proxyRowValues(row) {
    const value = (field) => (row.querySelector(`input[data-field="${field}"]`) || {}).value || '';
    const directEl = row.querySelector('input[data-field="direct"]');
    return {
      name: value('name').trim(),
      label: value('label').trim(),
      host: value('host').trim(),
      portRaw: value('port').trim(),
      path: value('path').trim(),
      startCommand: value('start-command').trim(),
      stopCommand: value('stop-command').trim(),
      direct: !!(directEl && directEl.checked),
    };
  }

  function _proxyRowEntry(row, index) {
    const v = _proxyRowValues(row);
    const errors = [];
    const entirelyEmpty = !v.name && !v.label && !v.host && !v.portRaw && !v.path
      && !v.startCommand && !v.stopCommand && !v.direct;
    if (entirelyEmpty) return {entry: null, errors};
    if (!v.name) errors.push(`Server ${index + 1}: name is required.`);
    else if (!/^[A-Za-z0-9_-]+$/.test(v.name)) errors.push(`Server ${index + 1}: name may only contain letters, digits, _ and -.`);
    if (!v.portRaw) errors.push(`Server ${index + 1}: port is required.`);
    const port = parseInt(v.portRaw, 10);
    if (v.portRaw && (!Number.isInteger(port) || port <= 0 || port > 65535)) errors.push(`Server ${index + 1}: port must be between 1 and 65535.`);
    if (v.startCommand && !/^make(?:\s|$)/.test(v.startCommand)) errors.push(`Server ${index + 1}: start command must begin with make.`);
    if (v.stopCommand && !/^make(?:\s|$)/.test(v.stopCommand)) errors.push(`Server ${index + 1}: stop command must begin with make.`);
    if (errors.length) return {entry: null, errors};
    const entry = {name: v.name, port};
    if (v.host) entry.host = v.host;
    if (v.path) entry.path = v.path;
    if (v.label) entry.label = v.label;
    if (v.direct) entry.mode = 'direct';
    if (v.startCommand) entry.start_command = v.startCommand;
    if (v.stopCommand) entry.stop_command = v.stopCommand;
    return {entry, errors};
  }

  function _syncProxyRowSummary(row) {
    const v = _proxyRowValues(row);
    const setText = (key, value) => {
      const target = row.querySelector(`[data-display="${key}"]`);
      if (target) target.textContent = value;
    };
    const host = v.host || 'localhost';
    const path = v.path || '/';
    setText('label', v.label || v.name || 'Unnamed server');
    setText('name', v.name);
    setText('endpoint', `${host}${v.portRaw ? ':' + v.portRaw : ''}${path.startsWith('/') ? path : '/' + path}`);
    setText('mode', v.direct ? 'direct' : 'proxied');
    setText('start-command', v.startCommand || 'Not configured');
    setText('stop-command', v.stopCommand || 'Not configured');
    const startRow = row.querySelector('[data-command-row="start"]');
    const stopRow = row.querySelector('[data-command-row="stop"]');
    if (startRow) startRow.classList.toggle('missing', !v.startCommand);
    if (stopRow) stopRow.classList.toggle('missing', !v.stopCommand);
    const dirty = row.dataset.dirty === '1';
    const startBtn = row.querySelector('[data-proxy-action="start"]');
    const stopBtn = row.querySelector('[data-proxy-action="stop"]');
    if (startBtn) {
      startBtn.disabled = dirty || !v.startCommand;
      startBtn.title = dirty ? 'Save changes before starting this server' : (!v.startCommand ? 'Configure a start command in Edit' : 'Run the configured start/restart command');
    }
    if (stopBtn) {
      stopBtn.disabled = dirty || !v.stopCommand;
      stopBtn.title = dirty ? 'Save changes before stopping this server' : (!v.stopCommand ? 'Configure a stop command in Edit' : 'Run the configured stop command');
    }
  }

  function finishProxyRowEdit(rowId) {
    const row = document.querySelector(`#proxiesRows .proxies-card[data-row-id="${rowId}"]`);
    if (!row) return;
    const rows = Array.from(document.querySelectorAll('#proxiesRows .proxies-card[data-row-id]'));
    const result = _proxyRowEntry(row, Math.max(0, rows.indexOf(row)));
    const err = document.getElementById('proxiesError');
    if (result.errors.length) {
      if (err) { err.textContent = result.errors.join(' · '); err.classList.add('on'); }
      return;
    }
    if (!result.entry) {
      removeProxyRow(rowId);
      if (err) { err.textContent = ''; err.classList.remove('on'); }
      return;
    }
    row.dataset.dirty = '1';
    _proxiesListDirty = true;
    _syncProxyRowSummary(row);
    row.classList.remove('editing');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
  }

  function removeProxyRow(rowId) {
    const row = document.querySelector(`#proxiesRows .proxies-card[data-row-id="${rowId}"]`);
    if (row) { row.remove(); _proxiesListDirty = true; }
    const host = document.getElementById('proxiesRows');
    if (host && !host.querySelector('.proxies-card[data-row-id]')) {
      host.innerHTML = `<div class="proxies-empty">No servers configured yet. Add one to expose a local app and optionally manage it with make commands.</div>`;
    }
  }

  function _collectProxiesFromRows() {
    const rows = document.querySelectorAll('#proxiesRows .proxies-card[data-row-id]');
    const out = [];
    const errors = [];
    const seenNames = new Set();
    rows.forEach((row, idx) => {
      const result = _proxyRowEntry(row, idx);
      errors.push(...result.errors);
      if (!result.entry) return;
      if (seenNames.has(result.entry.name)) errors.push(`Duplicate name "${result.entry.name}".`);
      else { seenNames.add(result.entry.name); out.push(result.entry); }
    });
    return {proxies: out, errors};
  }

  function _proxyVaultQuery() {
    return _proxiesVaultId ? `?vault=${encodeURIComponent(_proxiesVaultId)}` : '';
  }

  async function proxyServerAction(rowId, action) {
    const row = document.querySelector(`#proxiesRows .proxies-card[data-row-id="${rowId}"]`);
    if (!row || !_proxiesWorkspaceId) return;
    const values = _proxyRowValues(row);
    const status = row.querySelector('.proxies-action-status');
    const buttons = Array.from(row.querySelectorAll('[data-proxy-action]'));
    buttons.forEach(btn => { btn.disabled = true; btn.classList.add('busy'); });
    if (status) { status.textContent = `${action === 'stop' ? 'Stopping' : 'Starting / restarting'} ${values.label || values.name}…`; status.className = 'proxies-action-status'; }
    try {
      const url = `/api/proxies/${encodeURIComponent(_proxiesWorkspaceId)}/${encodeURIComponent(values.name)}/${action}${_proxyVaultQuery()}`;
      const r = await fetch(url, {method: 'POST'});
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || `${action} failed (${r.status})`);
      if (status) { status.textContent = `Server ${body.action || action}.`; status.className = 'proxies-action-status ok'; }
    } catch (e) {
      if (status) { status.textContent = e.message || String(e); status.className = 'proxies-action-status err'; }
    } finally {
      buttons.forEach(btn => btn.classList.remove('busy'));
      _syncProxyRowSummary(row);
    }
  }

  async function submitProxies(ev) {
    ev.preventDefault();
    const err = document.getElementById('proxiesError');
    const saveBtn = document.getElementById('proxiesSaveBtn');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    const {proxies, errors} = _collectProxiesFromRows();
    if (errors.length) {
      if (err) { err.textContent = errors.join(' · '); err.classList.add('on'); }
      return;
    }
    if (!_proxiesWorkspacePath) { closeProxiesModal(); return; }
    if (saveBtn) saveBtn.disabled = true;
    try {
      const put = await fetch(_serverConfigUrl('/api/server-config'), {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({servers: proxies}),
      });
      if (!put.ok) {
        const detail = await put.json().catch(() => ({}));
        throw new Error(detail.detail || `PUT server-config → ${put.status}`);
      }
    } catch (e) {
      if (err) { err.textContent = `Save failed: ${e.message || e}`; err.classList.add('on'); }
      if (saveBtn) saveBtn.disabled = false;
      return;
    }
    // Invalidate caches that hold the stale proxies list, then refresh.
    _workspaceSidebarCache.delete(_proxiesWorkspacePath);
    _workspaceAttrsCache.delete(_proxiesWorkspacePath);
    closeProxiesModal();
    if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
    if (typeof _refreshWorkspaceSidebar === 'function') _refreshWorkspaceSidebar({preserveScroll: true});
  }

  // ─── Client-global Assistant view ───

  async function termOpenForAssistant() {
    if (!_termIsScopeActive(ASSISTANT_WORKSPACE_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(ASSISTANT_WORKSPACE_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForWorkspace(ASSISTANT_WORKSPACE_ID);
    termStartPeriodicRefresh();
  }

  function initAssistant(initialTask = '', options = {}) {
    if (!LAB_IS_ADMIN) {
      goToProductivity({replace: true});
      return;
    }
    document.body.classList.remove('cerebro-active', 'self-active', 'vault-active', 'workspace-active');
    document.body.classList.add('assistant-active');
    document.title = 'Assistant';
    currentWorkspace = {
      name: ASSISTANT_WORKSPACE_ID,
      path: ASSISTANT_ROOT,
      is_workspace: true,
      repos: [],
      vault_id: ASSISTANT_VAULT_ID,
      vault: ASSISTANT_VAULT_ID,
    };
    _sidebarActivateFileConfig();
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    window.LAB_ASSISTANT_DOCUMENT_OPEN = false;
    const section = options.subview === 'meetings' ? 'meetings'
      : (options.subview === 'tasks' || /^tasks-[1-5]$/.test(options.subview || '') || initialTask ? 'tasks' : 'overview');
    _contextSubView = section;
    const diffTabs = document.getElementById('diffTabs');
    if (diffTabs) diffTabs.style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
    if (window.AssistantView) window.AssistantView.init({
      section,
      task: initialTask,
      meeting: options.meeting || '',
      workspace: options.workspace || '',
    });
    renderRepoTabs();
    _sidebarApplyForView();
    if (ASSISTANT_ROOT) _refreshWorkspaceSidebar();
    afterPageQuiet(() => {
      if (ASSISTANT_ROOT && !UI_CHECK) termOpenForAssistant();
    });
  }

  function assistantSectionShell(section) {
    if (!document.body.classList.contains('assistant-active')) return;
    _contextSubView = section === 'overview' ? 'overview' : section;
    _workspaceDocPath = null;
    _workspaceDocRoot = null;
    window.LAB_ASSISTANT_DOCUMENT_OPEN = false;
    currentRepo = null;
    renderRepoTabs();
    _sidebarApplyForView();
    if (ASSISTANT_ROOT) _refreshWorkspaceSidebar({preserveScroll: true});
  }
  window.assistantSectionShell = assistantSectionShell;

  // ─── Productivity self-view (file tree sidebar + Lab framework workbench) ───

  async function initSelf() {
    if (!LAB_IS_ADMIN) {
      const data = await fetchVaultCatalog();
      const first = (data.vaults || [])[0];
      if (first) goToVault(first.id, {replace: true});
      return;
    }
    document.body.classList.add('self-active');
    document.title = 'Home';
    // Set up a synthetic currentWorkspace so openWorkspaceDoc(), the sidebar, and
    // the terminal panel all work exactly like a real workspace tab.
    currentWorkspace = {
      name: '__self__',
      path: SELF_REPO_PATH,
      is_workspace: true,
      repos: [],
      vault_id: null,
    };
    _sidebarActivateFileConfig();
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    // Re-render the tab strip so the Productivity tab flips to `.active`
    // immediately. On in-page navigation (the common case) workspaceTabsAll
    // is already populated so all tabs render correctly. On the very
    // first page load with `?view=productivity` workspaceTabsAll may still
    // be empty for ~50ms — the in-flight workspaceTabsRefresh() will repaint
    // with the full tab list as soon as it returns. Mirrors what
    // initCerebro and selectRepo already do.
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
    renderRepoTabs();

    // Paint the workbench scaffold synchronously. The refresh fills in
    // tasks, changed areas, and recent commits after first paint.
    selfPaintWorkbench();
    const homeWorkspace = currentWorkspace;
    afterPageQuiet(() => {
      if (currentWorkspace !== homeWorkspace || !document.body.classList.contains('self-active')) return;
      selfPopulateSidebar();
      selfRefreshWorkbench();
      if (!UI_CHECK) termOpenForSelf();
    });
  }

  // Shared file-tree row renderer for the self + vault sidebars. One
  // implementation (not a sixth render site): both views feed it a
  // buildSidebarTree() node and differ only in tree scope (persisted
  // expand state), top-level auto-open folders, and active path. Rows use
  // the same fileIconHtml icons, symlink markers, notebook running/unseen
  // dots, and data-filepath hooks the git decorations poller keys on.
  const _AUTO_OPEN_SELF = new Set(['apps', 'docs', 'knowledge']);
  const _AUTO_OPEN_VAULT = new Set(['workspaces', 'content', 'docs']);

  function renderSidebarFileTree(node, depth, parentPath, opts) {
    const {scope, autoOpen, activePath, root} = opts;
    const sortMode = opts.sortMode || _sidebarCurrentSortMode('files');
    let html = '';
    treeFolderNames(node, sortMode).forEach(folder => {
      const fid = 'sf-' + Math.random().toString(36).substr(2, 6);
      const fullPath = parentPath ? `${parentPath}/${folder}` : folder;
      const d = treeFolderEntry(node, folder, fullPath);
      const autoOpenHere = depth === 0 && autoOpen && autoOpen.has(folder);
      const open = _treeIsOpen(scope, fullPath, autoOpenHere);
      const arrowCls = open ? ' open' : '';
      const childrenCls = open ? ' open' : '';
      html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(scope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}" data-entry-kind="folder" data-entry-path="${escAttr(fullPath)}" data-entry-root="${escAttr(root || '')}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">▶</span>${symlinkMarker(d)}${esc(folder)}/</div>`;
      html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
      html += renderSidebarFileTree(node[folder], depth + 1, fullPath, opts);
      html += '</div>';
    });
    treeFiles(node, sortMode).forEach(f => {
      const safePath = f.path.replace(/'/g, "\\'");
      const safeRoot = String(root || (currentWorkspace && currentWorkspace.path) || '').replace(/'/g, "\\'");
      const fname = f.path.split('/').pop();
      const icon = fileIconHtml(fname, f);
      const activeCls = activePath === f.path ? ' active' : '';
      // Notebook running / unseen dots — same logic as the workspace view's
      // _refreshWorkspaceSidebar so these views surface in-flight notebooks
      // too. Running wins over unseen since "currently executing" is the
      // more urgent state.
      if (f.pending) _recentlyPending.set(f.path, Date.now());
      const recent = _recentlyPending.get(f.path);
      const stillFresh = recent && (Date.now() - recent) < _PENDING_GRACE_MS;
      const isRunning = f.pending || stillFresh;
      if (recent && !isRunning) _recentlyPending.delete(f.path);
      const lastViewed = (fname.endsWith('.ipynb') && f.mtime) ? _nbGetLastViewed(f.path) : 0;
      const hasUnseen = !isRunning && f.mtime && lastViewed && f.mtime > lastViewed + 0.5;
      let dotHtml = '';
      if (isRunning) {
        const dotTitle = f.pending ? 'A cell is currently running' : 'Cell just finished';
        dotHtml = `<span class="nb-running-dot" title="${dotTitle}"></span>`;
      } else if (hasUnseen) {
        dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openWorkspaceDocAndJumpToUnseen('${safePath}','${safeRoot}')"></span>`;
      }
      html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}" data-entry-kind="file" data-entry-path="${escAttr(f.path)}" data-entry-root="${escAttr(root || '')}"${symlinkTitle(f)} onclick="openWorkspaceDocFromFileClick('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openWorkspaceDocModal('${safePath}',{root:'${safeRoot}'})"><span class="sidebar-fname">${dotHtml}${symlinkMarker(f)}${icon}${fname}</span></a>`;
    });
    return html;
  }

  // Populate #sidebar with a file tree rooted at SELF_REPO_PATH.
  // Mirrors the pattern used by showWorkspaceInfo() for real workspaces.
  async function selfPopulateSidebar() {
    const sidebar = document.getElementById('sidebar');
    try {
      const baseRoot = SELF_REPO_PATH;
      await _sidebarEnsureWorktrees(baseRoot);
      const fileRoot = _sidebarScopedRoot(baseRoot);
      const files = await _sidebarFetchWorkspaceFiles(fileRoot);
      const recentFiles = await _sidebarResolveRecentFiles(files, fileRoot);
      if (!document.body.classList.contains('self-active')
          || !currentWorkspace || currentWorkspace.path !== baseRoot
          || _sidebarScopedRoot(baseRoot) !== fileRoot) return;
      _sidebarRememberAvailableExtensions(files);
      _sidebarMaybeLogRecentDiagnostics(files, fileRoot);
      _rememberNotebookFolders(fileRoot, files);

      // Bake .active onto the rendered HTML (data-filepath + class) so any
      // future sidebar rebuild — mtime poll, WS index-updated — keeps the
      // current file highlighted. Without this the active class is only
      // applied imperatively after rebuild and the selection flickers.
      const activePath = _workspaceDocRoot === fileRoot ? (_workspaceDocPath || null) : null;
      const workbenchActive = !activePath ? ' active' : '';
      let sbHtml = `<div class="sidebar-overview-row"><a class="sidebar-file${workbenchActive}" data-workbench="1" onclick="selfShowWorkbench()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Overview</span></a>${_sidebarFileConfigCogHtml()}</div>`;
      sbHtml += _sidebarRecentSelectorsHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(baseRoot);
      sbHtml += _sidebarWorktreePickerHtml(baseRoot);
      sbHtml += symlinkLegendHtml();
      sbHtml += _sidebarWorktreeScopeStartHtml(baseRoot);
      sbHtml += _sidebarRecentSectionHtml(recentFiles, activePath, fileRoot, {resolved: true});
      sbHtml += _sidebarFilesTitle(fileRoot);

      const tree = buildSidebarTree(files);

      sbHtml += renderSidebarFileTree(tree, 0, '', {scope: `self:${fileRoot}`, autoOpen: _AUTO_OPEN_SELF, activePath, root: fileRoot});
      sbHtml += _sidebarWorktreeScopeEndHtml(baseRoot);

      sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
      sbHtml += _agentContextMetaHtml();
      for (const path of ['AGENTS.md', 'CLAUDE.md', '.github/copilot-instructions.md']) {
        if (!files.some(file => file.path === path)) continue;
        const action = `openWorkspaceDoc(${JSON.stringify(path)}, {root:${JSON.stringify(fileRoot)}})`;
        sbHtml += `<a class="sidebar-file sidebar-file-meta" onclick="${escAttr(action)}"><span class="sidebar-fname">${fileIconHtml(path)}${esc(path)}</span></a>`;
      }
      sidebar.innerHTML = sbHtml;
    } catch(e) {
      sidebar.innerHTML = '<div class="sidebar-title">Home</div>';
    }
  }

  // Render the Productivity workbench scaffold into #content. The refresh
  // functions look for element IDs inside here.
  function selfPaintWorkbench() {
    _workspaceDocPath = null;
    _contextSubView = 'overview';
    renderRepoTabs();
    const content = document.getElementById('content');
    content.innerHTML = `
      <div class="s-inner self-workbench">
        <div class="s-head">
          <h1>Lab Workbench</h1>
          <span class="branch" id="selfBranch">...</span>
        </div>
        <div class="s-toolbar">
          <button class="refresh-btn" onclick="selfRefreshWorkbench()">Refresh</button>
          <button class="refresh-btn" onclick="openWorkspaceDoc('AGENTS.md')">AGENTS.md</button>
          <button class="refresh-btn" onclick="openWorkspaceDoc('Makefile')">Makefile</button>
          <button class="refresh-btn" onclick="openWorkspaceDoc('README.md')">README.md</button>
        </div>
        <div class="s-summary" id="selfSummary">
          <div class="s-metric"><span>Open tasks</span><strong>...</strong></div>
          <div class="s-metric"><span>Changed files</span><strong>...</strong></div>
          <div class="s-metric"><span>Tests touched</span><strong>...</strong></div>
          <div class="s-metric"><span>Last commit</span><strong>...</strong></div>
        </div>
        <div class="s-workbench-grid">
          <div class="s-section" id="selfAttentionSection">
            <h2>Attention</h2>
            <ul class="s-attention" id="selfAttentionList"><li class="s-empty">Loading...</li></ul>
          </div>
          <div class="s-section" id="selfTasksSection">
            <h2>Open tasks <span class="count" id="selfTasksCount"></span></h2>
            <ul class="s-tasks" id="selfTasksList"><li class="s-task-empty">Loading tasks...</li></ul>
            <form class="s-task-form" id="selfTaskForm" onsubmit="return selfAddTask(event)">
              <input type="text" id="selfTaskTitle" placeholder="New task title..." required />
              <select id="selfTaskPriority">
                <option value="P2" selected>P2</option>
                <option value="P0">P0</option>
                <option value="P1">P1</option>
                <option value="P3">P3</option>
              </select>
              <button type="submit">Add</button>
            </form>
          </div>
          <div class="s-section" id="selfDiffSection">
            <h2>Changed areas <span class="count" id="selfDiffCount"></span></h2>
            <ul class="s-files" id="selfDiffList"><li class="s-empty">Loading changes...</li></ul>
          </div>
          <div class="s-section" id="selfCommitsSection">
            <h2>Recent commits <span class="count" id="selfCommitsCount"></span></h2>
            <ul class="s-commits" id="selfCommitsList"><li class="s-empty">Loading commits...</li></ul>
          </div>
        </div>
      </div>`;
  }

  // Return to the workbench from a doc view.
  function selfShowWorkbench() {
    _workspaceDocPath = null;
    _contextSubView = 'overview';
    _termSelectHomeSection();
    const url = new URL(window.location);
    url.searchParams.set('view', 'productivity');
    url.searchParams.delete('subview');
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    renderRepoTabs();
    document.querySelectorAll('#sidebar .sidebar-file').forEach(el => el.classList.remove('active'));
    selfPaintWorkbench();
    afterFirstPaint(() => selfRefreshWorkbench());
  }

  // Compatibility for older inline handlers or cached pages.
  function selfShowDashboard() { return selfShowWorkbench(); }

  function selfShowAdmin() {
    if (!LAB_IS_ADMIN) return;
    _workspaceDocPath = null;
    _contextSubView = 'admin';
    _termSelectHomeSection();
    const url = new URL(window.location);
    url.searchParams.set('view', 'productivity');
    url.searchParams.set('subview', 'admin');
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    currentRepo = null;
    renderRepoTabs();
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="s-inner self-admin">
        <div class="s-head"><h1>Admin</h1></div>
        <div class="s-workbench-grid">
          <div class="s-section admin-access-section">
            <h2>Users &amp; vault access</h2>
            <form class="admin-access-toolbar" onsubmit="return adminCreateUser(event)">
              <label>User name<input id="adminNewUsername" autocomplete="off" required placeholder="username"></label>
              <label>Display name<input id="adminNewName" autocomplete="off" placeholder="Name"></label>
              <label>Role<select id="adminNewRole"><option value="user">User</option><option value="admin">Admin</option></select></label>
              <label>Password<input id="adminNewPassword" type="password" autocomplete="new-password" required placeholder="Password"></label>
              <button class="refresh-btn" type="submit">Add user</button>
            </form>
            <div class="admin-user-list" id="adminUsersList"><div class="vault-muted">Loading users…</div></div>
          </div>
          <div class="s-section admin-access-section">
            <h2>Add vault</h2>
            <form class="admin-access-toolbar admin-vault-form" onsubmit="return adminAddVault(event)">
              <label>Name<input id="adminVaultName" placeholder="Team vault"></label>
              <label>Path<input id="adminVaultPath" required placeholder="/absolute/path/to/vault"></label>
              <label style="flex-direction:row;align-items:center;padding-bottom:7px"><input id="adminVaultCreate" type="checkbox"> Create if missing</label>
              <button class="refresh-btn" type="submit">Add vault</button>
            </form>
            <div class="admin-user-status" id="adminVaultStatus"></div>
          </div>
          <div class="s-section admin-access-section assistant-config-section">
            <h2>Assistant</h2>
            <p class="vault-muted">Choose the one client-global folder that stores Assistant tasks, notes, instructions, and terminal state. It must live outside the Lab framework checkout.</p>
            <form class="admin-access-toolbar admin-assistant-form" onsubmit="return adminSaveAssistant(event)">
              <label>Folder<input id="adminAssistantPath" required placeholder="/absolute/path/to/assistant"></label>
              <button class="refresh-btn" type="submit">Use folder</button>
              <button class="refresh-btn" id="adminAssistantOpen" type="button" disabled>Open Assistant</button>
            </form>
            <div class="admin-user-status" id="adminAssistantStatus">Loading Assistant configuration…</div>
          </div>
          <div class="s-section" id="dashKpis"></div>
          <div class="s-section" id="dashServers"><h2>Servers</h2><div class="srv-empty">Loading servers…</div></div>
          <div class="s-section" id="dashTerms"><h2>Terminals</h2><div class="term-empty">Loading terminal sessions…</div></div>

        </div>
      </div>`;
    content.querySelector('#dashServers').addEventListener('click', dashServersOnClick);
    content.querySelector('#dashTerms').addEventListener('click', dashTermsOnClick);
    if (!UI_CHECK) dashStartPolling();
    dashPollTick();
    adminLoadAccess();
    adminLoadAssistant();
  }
  window.selfShowAdmin = selfShowAdmin;

  let _adminAccessVaults = [];

  function adminRenderUsers(users) {
    const host = document.getElementById('adminUsersList');
    if (!host) return;
    if (!users.length) {
      host.innerHTML = '<div class="vault-muted">No users.</div>';
      return;
    }
    host.innerHTML = users.map(user => {
      const builtIn = user.built_in === true;
      const permissions = _adminAccessVaults.map(vault => {
        const checked = (user.vaults || []).includes(vault.id) ? ' checked' : '';
        const disabled = user.role === 'admin' || builtIn ? ' disabled' : '';
        return `<label><input type="checkbox" data-vault-permission="${escAttr(vault.id)}"${checked}${disabled}>${selfEsc(vault.name || vault.id)}</label>`;
      }).join('') || '<span class="vault-muted">Add a vault before assigning access.</span>';
      return `<div class="admin-user-row" data-admin-user="${escAttr(user.username)}">
        <div class="admin-user-head">
          <div class="admin-user-identity"><strong>${selfEsc(user.name)}</strong><code>${selfEsc(user.username)}${builtIn ? ' · built-in' : ''}</code></div>
          <label class="admin-user-field">Role<select data-user-role${builtIn ? ' disabled' : ''}><option value="user"${user.role === 'user' ? ' selected' : ''}>User</option><option value="admin"${user.role === 'admin' ? ' selected' : ''}>Admin</option></select></label>
          <label class="admin-user-field">New password<input data-user-password type="password" autocomplete="new-password" placeholder="${builtIn ? 'Fixed local password' : 'Leave unchanged'}"${builtIn ? ' disabled' : ''}></label>
          <label class="admin-user-field" style="flex-direction:row;align-items:center;padding-bottom:7px"><input data-user-disabled type="checkbox"${user.disabled ? ' checked' : ''}${builtIn ? ' disabled' : ''}> Disabled</label>
          ${builtIn ? '<span class="admin-built-in-badge">Fixed admin</span>' : '<button class="refresh-btn" type="button" onclick="adminSaveUser(this)">Save</button>'}
        </div>
        <div class="admin-permissions">${permissions}</div>
        <div class="admin-user-status" data-user-status>${builtIn ? 'Built-in local administrator. Username and password are fixed.' : (user.role === 'admin' ? 'Admins can access every vault.' : '')}</div>
      </div>`;
    }).join('');
  }

  async function adminLoadAccess() {
    const host = document.getElementById('adminUsersList');
    try {
      const [usersRes, vaultsRes] = await Promise.all([
        fetch('/api/admin/users'),
        fetchVaultCatalog(),
      ]);
      if (!usersRes.ok) throw new Error((await usersRes.json().catch(() => ({}))).detail || 'Could not load users');
      const usersBody = await usersRes.json();
      _adminAccessVaults = Array.isArray(vaultsRes.vaults) ? vaultsRes.vaults : [];
      adminRenderUsers(usersBody.users || []);
    } catch (e) {
      if (host) host.innerHTML = `<div class="vault-muted">${selfEsc(e.message || e)}</div>`;
    }
  }
  window.adminLoadAccess = adminLoadAccess;

  async function adminSaveUser(button) {
    const row = button && button.closest('[data-admin-user]');
    if (!row) return;
    const username = row.getAttribute('data-admin-user');
    const status = row.querySelector('[data-user-status]');
    const password = row.querySelector('[data-user-password]').value;
    const payload = {
      role: row.querySelector('[data-user-role]').value,
      disabled: row.querySelector('[data-user-disabled]').checked,
      vaults: Array.from(row.querySelectorAll('[data-vault-permission]:checked')).map(input => input.getAttribute('data-vault-permission')),
    };
    if (password) payload.password = password;
    button.disabled = true;
    if (status) status.textContent = 'Saving…';
    try {
      const response = await fetch('/api/admin/users/' + encodeURIComponent(username), {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Save failed');
      if (status) status.textContent = 'Saved';
      row.querySelector('[data-user-password]').value = '';
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    } finally {
      button.disabled = false;
    }
  }
  window.adminSaveUser = adminSaveUser;

  async function adminCreateUser(event) {
    if (event) event.preventDefault();
    const payload = {
      username: document.getElementById('adminNewUsername').value.trim(),
      name: document.getElementById('adminNewName').value.trim() || null,
      role: document.getElementById('adminNewRole').value,
      password: document.getElementById('adminNewPassword').value,
      vaults: [],
    };
    try {
      const response = await fetch('/api/admin/users', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not add user');
      event.target.reset();
      await adminLoadAccess();
    } catch (e) {
      const host = document.getElementById('adminUsersList');
      if (host) host.insertAdjacentHTML('afterbegin', `<div class="admin-user-status">${selfEsc(e.message || e)}</div>`);
    }
    return false;
  }
  window.adminCreateUser = adminCreateUser;

  async function adminAddVault(event) {
    if (event) event.preventDefault();
    const status = document.getElementById('adminVaultStatus');
    const payload = {
      name: document.getElementById('adminVaultName').value.trim() || null,
      path: document.getElementById('adminVaultPath').value.trim(),
      create: document.getElementById('adminVaultCreate').checked,
    };
    if (status) status.textContent = 'Adding…';
    try {
      const response = await fetch('/api/vaults', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not add vault');
      vaultCatalog = [];
      _vaultCatalogInFlight = null;
      _reposInFlight = null;
      event.target.reset();
      if (status) status.textContent = 'Vault added';
      await adminLoadAccess();
      await workspaceTabsRefresh();
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.adminAddVault = adminAddVault;

  function adminAssistantSummary(data) {
    if (!data || !data.configured) return 'Not configured. Choose a folder to initialize the Assistant database.';
    if (!data.exists) return 'The configured folder is unavailable. Choose it again or select a new folder.';
    const open = (data.tasks || []).filter(task => task.status !== 'done').length;
    return `Using this folder · ${(data.workspaces || []).length} workspace${(data.workspaces || []).length === 1 ? '' : 's'} · ${open} open task${open === 1 ? '' : 's'}`;
  }

  async function adminLoadAssistant() {
    const input = document.getElementById('adminAssistantPath');
    const status = document.getElementById('adminAssistantStatus');
    const open = document.getElementById('adminAssistantOpen');
    try {
      const response = await fetch('/api/assistant');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not load Assistant configuration');
      if (input) input.value = data.root || '';
      if (status) status.textContent = adminAssistantSummary(data);
      if (open) {
        open.disabled = !data.exists;
        open.onclick = () => goToAssistant('', {});
      }
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
  }
  window.adminLoadAssistant = adminLoadAssistant;

  async function adminSaveAssistant(event) {
    if (event) event.preventDefault();
    const input = document.getElementById('adminAssistantPath');
    const status = document.getElementById('adminAssistantStatus');
    const submit = event && event.submitter;
    const oldRoot = ASSISTANT_ROOT;
    if (status) status.textContent = 'Initializing Assistant folder…';
    if (submit) submit.disabled = true;
    try {
      const response = await fetch('/api/assistant/config', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: input ? input.value.trim() : '', create: true}),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'Could not configure Assistant');
      ASSISTANT_ROOT = data.root || '';
      window.LAB_ASSISTANT_ROOT = ASSISTANT_ROOT;
      if (oldRoot) _workspaceSidebarCache.delete(oldRoot);
      if (ASSISTANT_ROOT) _workspaceSidebarCache.delete(ASSISTANT_ROOT);
      if (input) input.value = ASSISTANT_ROOT;
      if (status) status.textContent = adminAssistantSummary(data);
      const open = document.getElementById('adminAssistantOpen');
      if (open) {
        open.disabled = false;
        open.onclick = () => goToAssistant('', {});
      }
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    } finally {
      if (submit) submit.disabled = false;
    }
    return false;
  }
  window.adminSaveAssistant = adminSaveAssistant;

  function selfShowLogs() {
    if (!LAB_IS_ADMIN) return;
    _workspaceDocPath = null;
    currentRepo = null;
    _contextSubView = 'logs';
    _termSelectHomeSection();
    const url = new URL(window.location);
    url.searchParams.set('view', 'productivity');
    url.searchParams.set('subview', 'logs');
    history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    renderRepoTabs();
    const content = document.getElementById('content');
    content.innerHTML = `
      <section class="home-logs" aria-label="Logs">
        <nav class="home-logs-sources" aria-label="Log sources">
          <h1>Logs</h1>
          <p>All registered vaults</p>
          <button type="button" data-log="errors.log"><span class="log-source-dot errors"></span><span>Errors<small>Backend &amp; frontend errors</small></span></button>
          <button type="button" data-log="backend.log"><span class="log-source-dot backend"></span><span>Backend<small>Server activity</small></span></button>
          <button type="button" data-log="frontend.log"><span class="log-source-dot frontend"></span><span>Frontend<small>Browser activity</small></span></button>
          <div class="home-logs-note">Clear deletes the selected log’s history across all vaults. New activity continues to be recorded.</div>
        </nav>
        <div class="home-logs-main">
          <header class="home-logs-heading">
            <div><h2 id="adminLogTitle">Errors</h2><p id="adminLogCount">Loading…</p></div>
            <div class="home-logs-actions">
              <button class="refresh-btn" id="adminLogRefreshButton" type="button">↻ Refresh</button>
              <button class="refresh-btn" id="adminLogCopyButton" type="button" disabled>Copy errors</button>
              <button class="refresh-btn admin-log-flush" id="adminLogFlushButton" type="button" disabled>Clear errors</button>
            </div>
          </header>
          <div class="home-logs-options">
            <label>Show <select id="adminLogLimit"><option value="500">Latest 500 entries</option><option value="2000">Latest 2,000 entries</option><option value="5000">Latest 5,000 entries</option></select></label>
            <label><input id="adminLogLive" type="checkbox" checked> Live updates</label>
            <span id="adminLogStatus" role="status"></span>
          </div>
          <pre class="home-logs-output" id="adminLogOutput" tabindex="0" aria-label="Log entries">Loading…</pre>
        </div>
      </section>`;
    content.querySelectorAll('[data-log]').forEach(button => {
      button.addEventListener('click', () => adminRefreshLogs(button.getAttribute('data-log')));
    });
    content.querySelector('#adminLogCopyButton').addEventListener('click', event => adminCopyLogs(event.currentTarget));
    content.querySelector('#adminLogFlushButton').addEventListener('click', event => adminFlushLogs(event.currentTarget));
    const refresh = () => adminRefreshLogs(content.querySelector('#adminLogOutput').getAttribute('data-log-file'));
    content.querySelector('#adminLogRefreshButton').addEventListener('click', refresh);
    content.querySelector('#adminLogLimit').addEventListener('change', refresh);
    content.querySelector('#adminLogLive').addEventListener('change', refresh);
    adminRefreshLogs('errors.log');
  }
  window.selfShowLogs = selfShowLogs;

  function _adminLogLabel(file) {
    return String(file || 'errors.log').replace(/\.log$/i, '');
  }

  function _adminLogRowText(row) {
    const stamp = row.ts || row.timestamp || '';
    const level = String(row.level || '').toUpperCase();
    const message = row.msg || row.message || row.raw || JSON.stringify(row);
    const lines = [`[${row.vault || 'vault'}] ${stamp} ${level} ${message}`.trim()];
    const context = {};
    [
      'logger', 'source', 'path', 'method', 'status_code', 'duration_ms',
      'action', 'event_type', 'target', 'href', 'source_url',
    ].forEach(key => {
      if (row[key] !== undefined && row[key] !== null && row[key] !== '') context[key] = row[key];
    });
    if (Object.keys(context).length) lines.push('  ' + JSON.stringify(context));
    if (row.exc) lines.push(String(row.exc));
    return lines.join('\n');
  }

  async function adminRefreshLogs(file = 'errors.log', {quiet = false} = {}) {
    const output = document.getElementById('adminLogOutput');
    if (!output) return;
    if (!['errors.log', 'backend.log', 'frontend.log'].includes(file)) file = 'errors.log';
    clearTimeout(output._refreshTimer);
    const request = (output._request || 0) + 1;
    output._request = request;
    const current = () => document.getElementById('adminLogOutput') === output && output._request === request;
    const count = document.getElementById('adminLogCount');
    const status = document.getElementById('adminLogStatus');
    const copyButton = document.getElementById('adminLogCopyButton');
    const flushButton = document.getElementById('adminLogFlushButton');
    const title = document.getElementById('adminLogTitle');
    const limit = document.getElementById('adminLogLimit');
    const switched = output.getAttribute('data-log-file') !== file;
    output.setAttribute('data-log-file', file);
    document.querySelectorAll('.home-logs-sources [data-log]').forEach(button => {
      const active = button.getAttribute('data-log') === file;
      button.classList.toggle('active', active);
      button.setAttribute('aria-pressed', String(active));
    });
    const label = _adminLogLabel(file);
    if (title) title.textContent = label[0].toUpperCase() + label.slice(1);
    copyButton.textContent = `Copy ${label}`;
    flushButton.textContent = `Clear ${label}`;
    if (!quiet) status.textContent = 'Loading…';
    if (switched) {
      output._logText = '';
      output._loaded = false;
      output.textContent = 'Loading…';
      count.textContent = '';
      copyButton.disabled = true;
      flushButton.disabled = true;
    }
    try {
      const r = await fetch('/api/log/tail/all?file=' + encodeURIComponent(file) + '&tail=' + (limit ? limit.value : '500'));
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'load failed');
      const data = await r.json();
      if (!current()) return;
      const entries = data.entries || [];
      const text = entries.map(_adminLogRowText).join('\n');
      const follow = switched || output.scrollHeight - output.scrollTop - output.clientHeight < 50;
      if (text !== output._logText || !output._loaded) {
        output._logText = text;
        output._loaded = true;
        output.innerHTML = entries.length ? entries.map(row => {
          const level = String(row.level || '').toUpperCase();
          const tone = ['ERROR', 'CRITICAL'].includes(level) ? 'error' : ['WARNING', 'WARN'].includes(level) ? 'warning' : 'info';
          return `<span class="home-log-entry ${tone}">${esc(_adminLogRowText(row))}</span>`;
        }).join('\n') : '<span class="home-logs-empty">No log entries. New activity will appear here.</span>';
        if (follow) output.scrollTop = output.scrollHeight;
      }
      count.textContent = `${entries.length.toLocaleString()} entries · oldest to newest`;
      copyButton.disabled = !entries.length;
      flushButton.disabled = !!output._clearing;
      if (!quiet || status.textContent.startsWith('Could not load')) status.textContent = '';
      if (file === 'errors.log' && window.labLogAlertMarkSeen) window.labLogAlertMarkSeen();
    } catch (e) {
      if (!current()) return;
      status.textContent = 'Could not load logs: ' + (e.message || e);
      if (switched) output.textContent = 'Logs unavailable. Use Refresh to try again.';
    } finally {
      const live = document.getElementById('adminLogLive');
      if (current() && live && live.checked && !UI_CHECK && !output._clearing) {
        output._refreshTimer = setTimeout(() => {
          if (current()) adminRefreshLogs(file, {quiet: true});
        }, 5000);
      }
    }
  }
  window.adminRefreshLogs = adminRefreshLogs;

  async function adminCopyLogs(button) {
    const output = document.getElementById('adminLogOutput');
    const status = document.getElementById('adminLogStatus');
    if (!output || !output._logText) return;
    const file = output.getAttribute('data-log-file');
    const ok = await _copyToClipboard(output._logText, button);
    if (document.getElementById('adminLogOutput') === output && output.getAttribute('data-log-file') === file) {
      status.textContent = ok ? 'Copied to clipboard' : 'Copy failed';
    }
  }
  window.adminCopyLogs = adminCopyLogs;

  async function adminFlushLogs(button) {
    const output = document.getElementById('adminLogOutput');
    const status = document.getElementById('adminLogStatus');
    if (!output || output._clearing) return;
    const file = output.getAttribute('data-log-file') || 'errors.log';
    const label = _adminLogLabel(file);
    if (!confirm(`Clear all ${label} recorded so far across all registered vaults? This deletes the stored history, including entries beyond the displayed limit. New logs will still be recorded.`)) return;
    output._clearing = true;
    clearTimeout(output._refreshTimer);
    output._request += 1;
    button.disabled = true;
    status.textContent = `Clearing ${label}…`;
    const current = () => document.getElementById('adminLogOutput') === output && output.getAttribute('data-log-file') === file;
    try {
      const response = await fetch('/api/log/clear/all?file=' + encodeURIComponent(file), {method: 'DELETE'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'clear failed');
      const cleared = Array.isArray(data.cleared) ? data.cleared.length : 0;
      const failed = Array.isArray(data.failed) ? data.failed : [];
      if (current()) {
        await adminRefreshLogs(file);
        if (current()) status.textContent = failed.length
          ? `Cleared ${cleared} vaults; failed: ${failed.map(row => row.vault).join(', ')}`
          : `Cleared ${label} in ${cleared} vault${cleared === 1 ? '' : 's'}`;
      }
    } catch (e) {
      if (current()) status.textContent = 'Clear failed: ' + (e.message || e);
    } finally {
      output._clearing = false;
      if (document.getElementById('adminLogOutput') === output) {
        button.disabled = false;
        // Resume updates for whichever source is now selected.
        adminRefreshLogs(output.getAttribute('data-log-file'), {quiet: true});
      }
    }
  }
  window.adminFlushLogs = adminFlushLogs;

  // Toggle hidden-files visibility for the productivity sidebar.
  // Mirrors toggleWorkspaceDotFiles() but re-renders via selfPopulateSidebar()
  // instead of showWorkspaceInfo().
  function selfToggleDotFiles(checked) {
    showWorkspaceDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    _storeSidebarFileConfig();
    selfPopulateSidebar();
  }

  function selfEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  function selfPriorityRank(priority) {
    return ({P0: 0, P1: 1, P2: 2, P3: 3})[priority] ?? 9;
  }

  function selfOpenTasks(tasks) {
    return (tasks || []).filter(t => t.status !== 'done').sort((a, b) => {
      const byPriority = selfPriorityRank(a.priority) - selfPriorityRank(b.priority);
      if (byPriority !== 0) return byPriority;
      return String(a.title || '').localeCompare(String(b.title || ''));
    });
  }

  function selfAreaForFile(filename) {
    const f = String(filename || '');
    if (f.startsWith('core/cli/')) return {key: 'cli', label: 'CLI', rank: 10};
    if (f.startsWith('core/src/core/static/') || f.startsWith('core/src/core/templates/')) return {key: 'ui', label: 'UI', rank: 20};
    if (f.startsWith('core/src/core/routes/') || f.startsWith('core/src/core/')) return {key: 'server', label: 'Server', rank: 30};
    if (f.startsWith('core/tests/') || f.startsWith('core/cli/tests/')) return {key: 'tests', label: 'Tests', rank: 40};
    if (f.startsWith('docs/') || f === 'README.md' || f === 'AGENTS.md') return {key: 'docs', label: 'Docs', rank: 50};
    if (f === 'Makefile' || f.endsWith('pyproject.toml') || f === '.gitignore' || f.startsWith('.agents/')) return {key: 'config', label: 'Config', rank: 60};
    if (f.startsWith('apps/')) return {key: 'apps', label: 'Removed apps', rank: 70};
    return {key: 'other', label: 'Other', rank: 90};
  }

  function selfRenderSummary(tasks, files, commits) {
    const summary = document.getElementById('selfSummary');
    if (!summary) return;
    const open = selfOpenTasks(tasks);
    const urgent = open.filter(t => t.priority === 'P0' || t.priority === 'P1').length;
    const tests = files.filter(f => selfAreaForFile(f.filename).key === 'tests').length;
    const latest = commits[0];
    const latestText = latest ? (latest.short_sha || '').slice(0, 8) : '-';
    summary.innerHTML = `
      <div class="s-metric"><span>Open tasks</span><strong>${open.length}</strong>${urgent ? `<em>${urgent} urgent</em>` : ''}</div>
      <div class="s-metric"><span>Changed files</span><strong>${files.length}</strong></div>
      <div class="s-metric"><span>Tests touched</span><strong>${tests}</strong></div>
      <div class="s-metric"><span>Last commit</span><strong>${selfEsc(latestText)}</strong></div>`;
  }

  function selfRenderAttention(tasks, files) {
    const list = document.getElementById('selfAttentionList');
    if (!list) return;
    const rows = [];
    const urgentTasks = selfOpenTasks(tasks).filter(t => t.priority === 'P0' || t.priority === 'P1').slice(0, 5);
    urgentTasks.forEach(t => rows.push({
      kind: t.priority || 'P?',
      title: t.title || '(untitled task)',
      meta: `task #${t.id}`,
    }));

    const byArea = new Map();
    files.forEach(f => {
      const area = selfAreaForFile(f.filename);
      const current = byArea.get(area.key) || {area, files: []};
      current.files.push(f);
      byArea.set(area.key, current);
    });
    ['tests', 'server', 'ui', 'cli', 'config'].forEach(key => {
      const group = byArea.get(key);
      if (!group || group.files.length === 0) return;
      rows.push({
        kind: group.area.label,
        title: `${group.files.length} changed ${group.files.length === 1 ? 'file' : 'files'}`,
        meta: group.files.slice(0, 3).map(f => f.filename).join(', '),
        file: (group.files.find(f => f.status !== 'deleted') || {}).filename,
      });
    });
    if (files.length > 25) {
      rows.push({kind: 'Size', title: `${files.length} files changed`, meta: 'large working tree'});
    }

    if (rows.length === 0) {
      list.innerHTML = '<li class="s-empty">No urgent tasks or risky change areas.</li>';
      return;
    }
    list.innerHTML = rows.slice(0, 8).map(row => {
      const safePath = row.file ? row.file.replace(/'/g, "\\'") : '';
      const open = row.file ? ` onclick="openWorkspaceDoc('${safePath}')"` : '';
      return `<li class="s-attention-row"${open}>
        <span class="s-attention-kind">${selfEsc(row.kind)}</span>
        <span class="s-attention-title">${selfEsc(row.title)}</span>
        <span class="s-attention-meta">${selfEsc(row.meta || '')}</span>
      </li>`;
    }).join('');
  }

  async function selfRefreshWorkbench() {
    const [tasks, diffDoc, commits] = await Promise.all([
      selfRefreshTasks(),
      selfRefreshDiff(),
      selfRefreshCommits(),
    ]);
    const files = (diffDoc && diffDoc.files) || [];
    selfRenderSummary(tasks, files, commits);
    selfRenderAttention(tasks, files);
  }

  async function selfRefreshTasks() {
    const list = document.getElementById('selfTasksList');
    const count = document.getElementById('selfTasksCount');
    let doc = {tasks: []};
    try {
      const r = await fetch('/api/workspaces/' + SELF_WORKSPACE_ID + '/tasks');
      if (r.ok) doc = await r.json();
    } catch {}
    const tasks = (doc.tasks || []).slice();
    const openTasks = selfOpenTasks(tasks);
    if (!list) return tasks;
    count.textContent = openTasks.length ? `${openTasks.length} open` : '';
    if (openTasks.length === 0) {
      list.innerHTML = '<li class="s-task-empty">No tasks yet. Add one below.</li>';
      return tasks;
    }
    list.innerHTML = openTasks.slice(0, 12).map(t => {
      const due = t.due ? `<span class="meta">due ${selfEsc(t.due)}</span>` : '';
      const prClass = (t.priority || 'P2').toLowerCase();
      return `
        <li class="s-task" data-tid="${t.id}">
          <input type="checkbox" class="check" data-tid="${t.id}" />
          <span class="pr-chip ${prClass}">${selfEsc(t.priority || 'P2')}</span>
          <span class="title">${selfEsc(t.title)}</span>
          ${due}
        </li>`;
    }).join('');
    list.querySelectorAll('.check').forEach(cb => {
      cb.addEventListener('change', () => selfToggleTaskDone(Number(cb.getAttribute('data-tid')), cb.checked));
    });
    return tasks;
  }

  async function selfToggleTaskDone(taskId, done) {
    try {
      await fetch(`/api/tasks/${SELF_WORKSPACE_ID}/${taskId}/status`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({status: done ? 'done' : 'reopened'}),
      });
    } catch {}
    await selfRefreshWorkbench();
  }

  async function selfAddTask(ev) {
    ev.preventDefault();
    const input = document.getElementById('selfTaskTitle');
    const prio = document.getElementById('selfTaskPriority');
    const title = (input.value || '').trim();
    if (!title) return false;
    try {
      const r = await fetch('/api/tasks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({workspace_id: SELF_WORKSPACE_ID, title, priority: prio.value}),
      });
      if (!r.ok) {
        const msg = await r.json().catch(() => ({}));
        alert('Failed to add task: ' + (msg.detail || r.statusText));
        return false;
      }
    } catch (e) { alert('Failed to add task: ' + (e.message || e)); return false; }
    input.value = '';
    await selfRefreshWorkbench();
    return false;
  }

  async function selfRefreshDiff() {
    const list = document.getElementById('selfDiffList');
    const count = document.getElementById('selfDiffCount');
    const branchEl = document.getElementById('selfBranch');
    let doc = {files: [], branch: '?'};
    try {
      const u = `/api/diff?repo=${encodeURIComponent(SELF_REPO_PATH)}&type=uncommitted&exclude=repositories`;
      const r = await fetch(u);
      if (r.ok) doc = await r.json();
    } catch {}
    if (branchEl) branchEl.textContent = 'branch ' + (doc.branch || '?');
    const files = doc.files || [];
    if (!list) return doc;
    count.textContent = files.length ? `${files.length} file${files.length === 1 ? '' : 's'}` : '';
    if (files.length === 0) {
      list.innerHTML = '<li class="s-empty">Working tree clean.</li>';
      return doc;
    }
    const groups = new Map();
    files.forEach(f => {
      const area = selfAreaForFile(f.filename);
      const group = groups.get(area.key) || {area, files: [], additions: 0, deletions: 0};
      group.files.push(f);
      group.additions += f.additions || 0;
      group.deletions += f.deletions || 0;
      groups.set(area.key, group);
    });
    const sorted = Array.from(groups.values()).sort((a, b) => a.area.rank - b.area.rank);
    list.innerHTML = sorted.map(group => {
      const filesHtml = group.files.slice(0, 8).map(f => {
        const safePath = f.filename.replace(/'/g, "\\'");
        const isDeleted = f.status === 'deleted';
        const name = selfEsc(f.filename);
        const fileLabel = isDeleted
          ? `<span class="s-file-link disabled">${name}</span>`
          : `<button type="button" class="s-file-link" onclick="openWorkspaceDoc('${safePath}')">${name}</button>`;
        return `<li class="s-area-file">${fileLabel}<span class="stats"><span class="adds">+${f.additions || 0}</span><span class="dels">-${f.deletions || 0}</span></span></li>`;
      }).join('');
      const more = group.files.length > 8 ? `<li class="s-area-more">+${group.files.length - 8} more</li>` : '';
      return `<li class="s-area">
        <div class="s-area-head"><strong>${selfEsc(group.area.label)}</strong><span>${group.files.length} file${group.files.length === 1 ? '' : 's'}</span><span class="stats"><span class="adds">+${group.additions}</span><span class="dels">-${group.deletions}</span></span></div>
        <ul class="s-area-files">${filesHtml}${more}</ul>
      </li>`;
    }).join('');
    return doc;
  }

  async function selfRefreshCommits() {
    const list = document.getElementById('selfCommitsList');
    const count = document.getElementById('selfCommitsCount');
    let commits = [];
    try {
      const u = `/api/commits?repo=${encodeURIComponent(SELF_REPO_PATH)}&count=30&exclude=repositories`;
      const r = await fetch(u);
      if (r.ok) commits = await r.json();
    } catch {}
    if (!list) return commits;
    count.textContent = commits.length ? `${commits.length}` : '';
    if (commits.length === 0) {
      list.innerHTML = '<li class="s-empty">No commits yet.</li>';
      return commits;
    }
    list.innerHTML = commits.map(c => `
      <li class="s-commit" data-sha="${selfEsc(c.sha)}">
        <span class="sha">${selfEsc(c.short_sha || '')}</span>
        <span class="msg">${selfEsc(c.message || '')}</span>
        <span class="who">${selfEsc(c.author || '')} · ${selfEsc(c.date || '')}</span>
      </li>`).join('');
    return commits;
  }

  // Terminal panel for the Productivity pseudo-workspace: claude session at repo root.
  // Terminal panel for the Productivity pseudo-workspace: sessions rooted at the
  // repo root. Mirrors termOpenForCerebro() exactly, substituting SELF_WORKSPACE_ID.
  async function termOpenForSelf() {
    if (!_termIsScopeActive(SELF_WORKSPACE_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    // Select the section's last session from the same mounted Home pool.
    if (termCurrentWorkspaceId === SELF_WORKSPACE_ID && termCurrentSession) {
      _termSelectHomeSection();
      termStartPeriodicRefresh();
      return;
    }
    if (await _termTryWarmOpen(SELF_WORKSPACE_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForWorkspace(SELF_WORKSPACE_ID);
    termStartPeriodicRefresh();
  }

  // ─── Vault view (vault-scoped management surface) ───
  // Mirrors initSelf(): synthetic currentWorkspace rooted at the selected
  // registered vault. It renders inside Home while preserving the owning
  // vault scope for files and workspaces. Terminals belong to Home.

  let _vaultViewRequestSeq = 0;

  async function initVaultView(vaultId) {
    const request = ++_vaultViewRequestSeq;
    // Publish the destination before awaiting the catalog so a terminal click
    // during loading can navigate back out of this vault correctly.
    currentWorkspace = {name: VAULT_WORKSPACE_ID, vault_id: vaultId,
      path: (vaultCatalog || []).find(v => v.id === vaultId)?.path || '',
      is_workspace: true, repos: []};
    // The initial `?view=…` dispatch calls us directly without
    // _swapViewState, so strip mutually exclusive view classes here.
    document.body.classList.remove(
      'cerebro-active', 'self-active', 'assistant-active', 'workspace-active',
    );
    document.body.classList.add('vault-active');
    if (!LAB_IS_ADMIN) document.body.classList.remove('term-open');
    document.title = 'Vault';
    const dt = document.getElementById('diffTabs');
    if (dt) dt.style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    // Re-render the tab strip so Home stays `.active`
    // immediately (same first-load caveat as initSelf: workspaceTabsRefresh
    // repaints with the full list once it returns).
    _workspaceDocPath = null;

    // Scaffold synchronously; the fetch below fills in the real content.
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="s-inner vault-overview"><div class="loading">Loading vault…</div></div>';

    const data = await fetchVaultCatalog();
    // The user may have navigated away while the fetch was in flight.
    if (request !== _vaultViewRequestSeq || !document.body.classList.contains('vault-active')) return;
    const current = ((data && data.vaults) || []).find(w => w.id === vaultId)
      || ((data && data.vaults) || []).find(w => w.active)
      || null;
    _vaultCurrent = current;
    if (!current || !current.path) {
      if (content) content.innerHTML = '<div class="s-inner vault-overview"><div class="loading">Could not load the active vault.</div></div>';
      return;
    }
    document.title = 'Vault — ' + (current.name || current.id);
    // Synthetic workspace rooted at the vault root (same trick as the
    // self view) so the doc pane, sidebar, and pollers treat it like a
    // real workspace.
    currentWorkspace = {
      name: VAULT_WORKSPACE_ID,
      path: current.path,
      is_workspace: true,
      repos: [],
      vault_id: current.id,
      vault_name: current.name || current.id,
      vault_color: current.color || '#8b949e',
    };
    _sidebarActivateFileConfig();
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
    renderRepoTabs();
    _sidebarApplyForView();
    vaultPaintOverview(current);
    const vaultWorkspace = currentWorkspace;
    afterPageQuiet(() => {
      if (currentWorkspace !== vaultWorkspace || !document.body.classList.contains('vault-active')) return;
      vaultPopulateSidebar();
      vaultRefreshCards();
      if (!UI_CHECK) termOpenForSelf();
    });
  }

  // Overview scaffold: header (name + id badge + active pill + path) and
  // the three cards. Reuses the productivity workbench's .s-inner /
  // .s-workbench-grid / .s-section card classes so it reads like the
  // existing dashboards. vaultRefreshCards() fills the card bodies.
  function vaultPaintOverview(current) {
    _workspaceDocPath = null;
    _contextSubView = 'overview';
    renderRepoTabs();
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="s-inner vault-overview">
        <div class="s-head vault-ov-head">
          <h1>${selfEsc(current.name || current.id)}
            <span class="vault-badge" title="vault id">${selfEsc(current.id)}</span></h1>
        </div>
        <div class="vault-ov-path" title="${escAttr(current.path)}">${selfEsc(current.path)}</div>
        ${LAB_IS_ADMIN ? '<div class="s-toolbar"><button class="refresh-btn" onclick="showScopedCodeSearch()">Search this vault</button></div>' : ''}
        <div class="s-workbench-grid vault-ov-grid">
          <div class="s-section" id="vaultAppearanceCard">
            <h2>Appearance</h2>
            <form class="vault-appearance-form" onsubmit="return vaultSaveAppearance(event)">
              <label>Name or alias
                <input id="vaultAppearanceName" type="text" value="${escAttr(current.name || current.id)}" maxlength="80" required>
              </label>
              <label>Tab color
                <span class="vault-color-row">
                  <input id="vaultAppearanceColor" type="color" value="${escAttr(current.color || '#8b949e')}" oninput="this.nextElementSibling.textContent=this.value">
                  <span class="vault-color-value">${selfEsc(current.color || '#8b949e')}</span>
                </span>
              </label>
              <div class="vault-card-actions"><button class="refresh-btn" type="submit">Save appearance</button><span class="vault-appearance-status" id="vaultAppearanceStatus"></span></div>
            </form>
          </div>
          <div class="s-section" id="vaultConfigCard">
            <h2>Configuration</h2>
            <div class="vault-card-body" id="vaultConfigBody"><div class="vault-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="vaultAgentsCard">
            <h2>Agents</h2>
            <div class="vault-card-body" id="vaultAgentsBody"><div class="vault-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="vaultWorkspacesCard">
            <h2>Workspaces <span class="count" id="vaultWorkspacesCount"></span>
              <button class="refresh-btn" type="button" onclick="openVaultWorkspaceModal()">+ New workspace</button></h2>
            <ul class="vault-workspace-list" id="vaultWorkspacesList"><li class="s-empty">Loading…</li></ul>
          </div>
        </div>
      </div>`;
  }

  // Return to the overview from a doc view (sidebar "Overview" link).
  function vaultShowOverview() {
    _workspaceDocPath = null;
    _contextSubView = 'overview';
    renderRepoTabs();
    document.querySelectorAll('#sidebar .sidebar-file').forEach(el => el.classList.remove('active'));
    if (_vaultCurrent && currentWorkspace && currentWorkspace.name === VAULT_WORKSPACE_ID) {
      vaultPaintOverview(_vaultCurrent);
      afterFirstPaint(() => vaultRefreshCards());
    } else {
      initVaultView(_vaultCurrent && _vaultCurrent.id);
    }
  }

  async function vaultSaveAppearance(event) {
    if (event) event.preventDefault();
    if (!_vaultCurrent) return false;
    const nameEl = document.getElementById('vaultAppearanceName');
    const colorEl = document.getElementById('vaultAppearanceColor');
    const status = document.getElementById('vaultAppearanceStatus');
    const name = (nameEl && nameEl.value || '').trim();
    const color = colorEl && colorEl.value;
    if (status) status.textContent = 'Saving…';
    try {
      const r = await fetch('/api/vaults/' + encodeURIComponent(_vaultCurrent.id) + '/appearance', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, color}),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'save failed');
      const updated = await r.json();
      _vaultCurrent.name = updated.name;
      _vaultCurrent.color = updated.color;
      const catalogRow = _vaultById(_vaultCurrent.id);
      if (catalogRow) Object.assign(catalogRow, updated);
      if (currentWorkspace) {
        currentWorkspace.vault_name = updated.name;
        currentWorkspace.vault_color = updated.color;
      }
      vaultPaintOverview(_vaultCurrent);
      workspaceTabsRender();
      renderRepoTabs();
      const savedStatus = document.getElementById('vaultAppearanceStatus');
      if (savedStatus) savedStatus.textContent = 'Saved';
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.vaultSaveAppearance = vaultSaveAppearance;

  async function vaultRefreshCards() {
    if (!document.body.classList.contains('vault-active')) return;
    await Promise.all([
      vaultRenderConfigCard(),
      vaultRenderAgentsCard(),
      vaultRenderWorkspacesCard(),
    ]);
  }

  // "Configuration" card: vault.json status from /api/vault/config.
  // The file is optional — absent is a normal, valid state. The card offers
  // a starter-file button when absent and, in every state, a "Copy setup
  // prompt" button that produces a state-aware prompt for the vault
  // agent (structure reference + the current validation problems).
  let _vaultCfgLast = null;

  async function vaultRenderConfigCard() {
    const body = document.getElementById('vaultConfigBody');
    if (!body) return;
    let cfg = null;
    try {
      const r = await fetch('/api/vault/config?vault=' + encodeURIComponent(_vaultCurrent.id));
      if (r.ok) cfg = await r.json();
    } catch {}
    if (!body.isConnected) return;  // view repainted/navigated meanwhile
    _vaultCfgLast = cfg;
    if (!cfg) {
      body.innerHTML = '<div class="vault-muted">Could not load vault.json status.</div>';
      return;
    }
    const copyBtn = '<button class="refresh-btn" onclick="vaultCopySetupPrompt(this)" title="Copy a prompt for your vault agent: expected vault.json structure plus the current validation state">Copy setup prompt</button>';
    if (!cfg.present) {
      body.innerHTML = [
        '<div class="vault-muted">vault.json not present (optional).</div>',
        `<div class="vault-card-actions"><button class="refresh-btn" onclick="vaultCreateConfig(this)">Create vault config</button>${copyBtn}</div>`,
      ].join('');
      return;
    }
    const errors = cfg.errors || [];
    const warnings = cfg.warnings || [];
    const rows = [];
    if (cfg.valid) {
      rows.push(`<div class="vault-cfg-status ok">✓ vault.json is valid${warnings.length ? ' (with warnings)' : ''}</div>`);
    } else {
      rows.push('<div class="vault-cfg-status err">✗ vault.json has problems</div>');
    }
    for (const e of errors) rows.push(`<div class="vault-cfg-issue err">${selfEsc(e)}</div>`);
    for (const w of warnings) rows.push(`<div class="vault-cfg-issue warn">${selfEsc(w)}</div>`);
    rows.push(`<div class="vault-card-actions"><button class="refresh-btn" onclick="openVaultConfig()">Open vault config</button>${copyBtn}</div>`);
    body.innerHTML = rows.join('');
  }

  function openVaultConfig() {
    // Legacy vaults retain their source filename until the first config update.
    const source = _vaultCfgLast && _vaultCfgLast.source === 'workspace.json'
      ? 'workspace.json' : 'vault.json';
    openWorkspaceDoc(source);
  }
  window.openVaultConfig = openVaultConfig;

  // The setup prompt handed to the vault agent. Self-contained: the
  // agent works inside the vault repo and may not have framework docs.
  function _vaultSetupPromptText() {
    const cfg = _vaultCfgLast || {};
    const root = cfg.root || (_vaultCurrent && _vaultCurrent.path) || '(vault root)';
    const configUrl = location.origin + '/api/vault/config?vault=' +
      encodeURIComponent((_vaultCurrent && _vaultCurrent.id) || '');
    const issues = [];
    for (const e of (cfg.errors || [])) issues.push('- ERROR: ' + e);
    for (const w of (cfg.warnings || [])) issues.push('- warning: ' + w);
    let state;
    if (!cfg.present) {
      state = 'There is no vault.json yet. Create it at ' + root + '/vault.json.';
    } else if (cfg.source === 'workspace.json') {
      state = 'Shared config is still stored at ' + root + '/workspace.json. Create vault.json with the same settings, translating the old project section to workspace. The config API below returns normalized fields. Preserve the legacy source file.';
      if (issues.length) state += '\nResolve these validation issues: \n' + issues.join('\n');
    } else if (!cfg.valid) {
      state = 'vault.json exists but is INVALID. Fix these problems:\n' + issues.join('\n');
    } else if (issues.length) {
      state = 'vault.json exists and is valid, but has warnings to clean up:\n' + issues.join('\n');
    } else {
      state = 'vault.json exists and is valid. Review it against the structure below and extend it to describe what this vault actually uses.';
    }
    return [
      "Set up this vault's vault.json — the declarative configuration Neurona",
      'reads at the vault root. Work from the vault root: ' + root,
      '',
      'Current state: ' + state,
      '',
      'Expected structure (version 1). Everything except "version" is optional —',
      'describe only what this vault actually uses:',
      '',
      '{',
      '  "version": 1,',
      '  "id": "vault-id",',
      '  "name": "Readable Name",',
      '  "agents": {',
      '    "supported": ["claude", "codex", "copilot"],',
      '    "default": "claude",',
      '    "projections": [',
      '      {"source": "agents/instructions.md", "target": "AGENTS.md", "mode": "symlink"},',
      '      {"source": "agents/instructions.md", "target": "CLAUDE.md", "mode": "symlink", "when": "claude"},',
      '      {"source": "agents/instructions.md", "target": ".github/copilot-instructions.md", "mode": "adapter", "when": "copilot"}',
      '    ]',
      '  },',
      '  "workspace": {',
      '    "template": "templates/workspace",',
      '    "features": ["tasks", "docs", "notebooks", "prs", "diffs"],',
      '    "mounts": []',
      '  },',
      '  "notebooks": {',
      '    "enabled": true,',
      '    "provider": "local",',
      '    "kernels": ["python3", "pyspark"],',
      '    "mounts": [{"source": "code", "target": "code"}]',
      '  },',
      '  "display": {',
      '    "autoOpen": ["docs", "notebooks"],',
      '    "hide": ["worktrees"],',
      '    "showProjectionOrigin": true',
      '  },',
      '  "repositories": [],',
      '  "services": []',
      '}',
      '',
      'Field notes:',
      '- "version" is required, an integer, currently 1. Unknown top-level fields are',
      '  ignored with a warning, so stay within this schema.',
      '- "agents.supported" lists the agent CLIs this vault uses ("claude",',
      '  "codex", "copilot"); "agents.default" must be one of them.',
      '- "agents.projections" map one tool-neutral source file to the per-tool',
      '  surfaces (AGENTS.md, CLAUDE.md, .github/copilot-instructions.md).',
      '  "mode" is "symlink" | "adapter" | "copy"; "when" limits an entry to one',
      '  supported agent.',
      '- "workspace.features" are the surfaces workspaces get; "workspace.mounts" are',
      '  optional data mounts. Skills belong locally to each workspace; do not mount shared skill directories.',
      '- "notebooks" selects the executor ("local" uses the configured Jupyter runtime).',
      '- "display" holds UI hints: "autoOpen", "hide", "showProjectionOrigin".',
      '',
      'How to work:',
      '1. Look at what actually exists in the vault tree (agents/, skills/,',
      '   code/, templates/, workspaces/, repositories/) and write configuration that',
      '   matches reality, not aspiration.',
      '2. Write valid JSON (no comments, no trailing commas) at',
      '   ' + root + '/vault.json.',
      '3. Projections declare intent. If you also apply them, use relative symlinks',
      '   and never overwrite a real file — only replace links that already point',
      '   into vault sources, or files whose first line marks them generated.',
      '4. Verify when done: ' + configUrl + ' must show',
      '   "valid": true with an empty "errors" list. The Vault tab\'s',
      '   Configuration card shows the same.',
    ].join('\n');
  }

  async function vaultCopySetupPrompt(btn) {
    await _copyToClipboard(_vaultSetupPromptText(), btn);
  }
  window.vaultCopySetupPrompt = vaultCopySetupPrompt;

  async function vaultCreateConfig(btn) {
    if (btn) btn.disabled = true;
    try {
      const r = await fetch('/api/vault/config/init?vault=' + encodeURIComponent(_vaultCurrent.id), { method: 'POST' });
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail || 'create failed';
        if (btn) { btn.textContent = String(detail); btn.disabled = false; }
        return;
      }
      _vaultCfgLast = await r.json();
      // Hand the user the next step in one motion: starter written, prompt
      // for the agent already on the clipboard.
      await _copyToClipboard(_vaultSetupPromptText(), btn);
      await vaultRenderConfigCard();
    } finally {
      if (btn && btn.isConnected) btn.disabled = false;
    }
  }
  window.vaultCreateConfig = vaultCreateConfig;

  // "Agents" card: vault.json controls which agent choices appear in
  // every terminal/settings menu. Autopilot remains a launch setting edited
  // in Settings; availability is toggled here at vault scope.
  async function vaultRenderAgentsCard() {
    const body = document.getElementById('vaultAgentsBody');
    if (!body) return;
    let s = _settings;
    // force: the vault agent may have edited vault.json directly
    // (that's the documented flow) — a cached policy would keep stale
    // agents in every menu until a full reload.
    let policy = await loadVaultAgentPolicy({force: true});
    try {
      const r = await fetch('/api/settings');
      if (r.ok) { s = await r.json(); _settings = s; }
    } catch {}
    if (!body.isConnected) return;
    const autopilot = s.autopilot || {};
    const flags = s.autopilotFlags || {};
    const enabled = new Set(policy.supported || []);
    const defaultAgent = policy.default || s.defaultAgent || 'claude';
    const rows = Object.keys(AGENT_LABELS).map(a => {
      const on = !!autopilot[a];
      const available = enabled.has(a);
      const flag = on && flags[a] ? ` (${flags[a]})` : '';
      const lastEnabled = available && enabled.size === 1;
      return `<label class="vault-agent-row${available ? '' : ' off'}">
        <input type="checkbox" ${available ? 'checked' : ''} ${lastEnabled ? 'disabled' : ''}
               onchange="vaultToggleAgent('${a}', this.checked, this)"
               title="${lastEnabled ? 'At least one agent must remain enabled' : `Show ${escAttr(AGENT_LABELS[a])} in vault menus`}">
        <span class="vault-agent-name">${selfEsc(AGENT_LABELS[a])}</span>
        ${available && a === defaultAgent ? '<span class="vault-agent-default">default</span>' : ''}
        <span class="vault-agent-auto${on ? ' on' : ''}">autopilot ${on ? 'on' : 'off'}${selfEsc(flag)}</span>
      </label>`;
    });
    rows.unshift('<div class="vault-agent-hint">Enabled agents appear in every <strong>+ New</strong> menu.</div>');
    rows.push('<div class="vault-card-actions"><button class="refresh-btn" onclick="openSettings()">Launch settings</button></div>');
    body.innerHTML = rows.join('');
  }

  async function vaultToggleAgent(agent, checked, checkbox) {
    const policy = await loadVaultAgentPolicy();
    const next = new Set(policy.supported || []);
    if (checked) next.add(agent);
    else next.delete(agent);
    if (!next.size) {
      if (checkbox) checkbox.checked = true;
      return;
    }
    const card = document.getElementById('vaultAgentsBody');
    if (card) card.querySelectorAll('input,button').forEach(el => { el.disabled = true; });
    try {
      const r = await fetch('/api/vault/agents', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          vault: _vaultCurrent && _vaultCurrent.id,
          supported: Object.keys(AGENT_LABELS).filter(a => next.has(a)),
        }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'update failed');
      _vaultAgentPolicy = Object.assign({vault: _vaultCurrent && _vaultCurrent.id}, await r.json());
      await Promise.all([vaultRenderAgentsCard(), vaultRenderConfigCard()]);
    } catch (e) {
      if (card && card.isConnected) {
        card.innerHTML = `<div class="vault-cfg-issue err">${selfEsc(e.message || e)}</div>`;
        setTimeout(() => vaultRenderAgentsCard(), 1800);
      }
    }
  }
  window.vaultToggleAgent = vaultToggleAgent;

  let _vaultWorkspaceCreateBusy = false;
  let _vaultWorkspaceCreateVault = null;

  function openVaultWorkspaceModal(vault = _vaultCurrent) {
    if (_vaultWorkspaceCreateBusy || !vault || vault.unavailable) return;
    const modal = document.getElementById('vaultWorkspaceModal');
    const form = document.getElementById('vaultWorkspaceForm');
    const context = document.getElementById('vaultWorkspaceContext');
    const error = document.getElementById('vaultWorkspaceError');
    if (!modal || !form) return;
    form.reset();
    _vaultWorkspaceCreateVault = vault.id;
    if (context) context.textContent = vault.name || vault.id;
    if (error) {
      error.textContent = '';
      error.classList.remove('on');
    }
    modal.classList.add('active');
    setTimeout(() => {
      const input = document.getElementById('vaultWorkspaceId');
      if (input) input.focus();
    }, 0);
  }
  window.openVaultWorkspaceModal = openVaultWorkspaceModal;

  function closeVaultWorkspaceModal() {
    if (_vaultWorkspaceCreateBusy) return;
    const modal = document.getElementById('vaultWorkspaceModal');
    if (modal) modal.classList.remove('active');
  }
  window.closeVaultWorkspaceModal = closeVaultWorkspaceModal;

  function _vaultWorkspaceCsv(value) {
    return String(value || '').split(',').map(item => item.trim()).filter(Boolean);
  }

  async function submitVaultWorkspace(event) {
    if (event) event.preventDefault();
    if (_vaultWorkspaceCreateBusy || !_vaultWorkspaceCreateVault) return false;
    const form = document.getElementById('vaultWorkspaceForm');
    const error = document.getElementById('vaultWorkspaceError');
    const submit = document.getElementById('vaultWorkspaceSubmit');
    if (!form) return false;

    const vaultId = _vaultWorkspaceCreateVault;
    _vaultWorkspaceCreateBusy = true;
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Creating…';
    }
    if (error) {
      error.textContent = '';
      error.classList.remove('on');
    }

    try {
      const response = await fetch('/api/workspaces', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          id: form.elements.id.value.trim(),
          vault: vaultId,
          description: form.elements.description.value.trim(),
          priority: form.elements.priority.value || null,
          due: form.elements.due.value || null,
          tags: _vaultWorkspaceCsv(form.elements.tags.value),
          labels: _vaultWorkspaceCsv(form.elements.labels.value),
        }),
      });
      const created = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(created.detail || 'workspace creation failed');

      // A catalog request that started before creation may not contain the
      // new row. Let it settle, then fetch an authoritative post-create list.
      const pendingCatalog = _vaultCatalogInFlight;
      if (pendingCatalog) await pendingCatalog;
      const data = await fetchVaultCatalog();
      const vaults = (data && data.vaults) || [];
      const refreshed = vaults.find(row => row.id === vaultId);
      if (refreshed && _vaultCurrent?.id === vaultId) _vaultCurrent = refreshed;
      workspacesList = vaults.flatMap(row => row.workspace_rows || []);
      const workspace = workspacesList.find(row =>
        row.vault === vaultId && row.name === created.id);

      _vaultWorkspaceCreateBusy = false;
      closeVaultWorkspaceModal();
      if (workspace && workspace.path) goToWorkspace(workspace.path);
      else await vaultRenderWorkspacesCard();
    } catch (e) {
      if (error) {
        error.textContent = e.message || String(e);
        error.classList.add('on');
      }
    } finally {
      _vaultWorkspaceCreateBusy = false;
      if (submit) {
        submit.disabled = false;
        submit.textContent = 'Create workspace';
      }
    }
    return false;
  }
  window.submitVaultWorkspace = submitVaultWorkspace;

  // "Workspaces" card: the shown vault's workspace ids from
  // /api/vaults/workspaces. Rows open the workspace the same way Home's
  // active-vault rows do (goToWorkspaceById → in-page nav).
  function vaultWorkspaceResourceLabel(resources) {
    return [['terminals', 'terminal'], ['servers', 'server'], ['kernels', 'kernel']]
      .filter(([key]) => resources[key] > 0)
      .map(([key, label]) => `${resources[key]} ${label}${resources[key] === 1 ? '' : 's'}`)
      .join(' · ') || 'No active resources';
  }

  async function vaultRefreshWorkspaceResources() {
    const list = document.getElementById('vaultWorkspacesList');
    const vault = _vaultCurrent;
    if (!list?.isConnected || !vault || vault.unavailable || _vaultResourceRequests.has(vault.id)) return;
    _vaultResourceRequests.add(vault.id);
    try {
      const response = await fetch('/api/vaults/resources?vault=' + encodeURIComponent(vault.id));
      if (!response.ok) throw new Error('Could not load resources');
      const resources = await response.json();
      if (!list.isConnected || _vaultCurrent?.id !== vault.id) return;
      list.querySelectorAll('.vault-workspace-resources').forEach(badge => {
        const counts = resources.workspaces[badge.getAttribute('data-workspace-id')] || {};
        const label = vaultWorkspaceResourceLabel(counts);
        badge.textContent = label;
        badge.classList.toggle('active', Object.values(counts).some(count => count > 0));
        badge.title = label;
      });
    } catch {
      if (list.isConnected && _vaultCurrent?.id === vault.id) {
        list.querySelectorAll('.vault-workspace-resources').forEach(badge => {
          badge.textContent = 'Resources unavailable';
          badge.classList.remove('active');
          badge.title = 'Could not refresh running resources; retrying automatically';
        });
      }
    } finally {
      _vaultResourceRequests.delete(vault.id);
    }
  }

  async function vaultRenderWorkspacesCard() {
    const list = document.getElementById('vaultWorkspacesList');
    const count = document.getElementById('vaultWorkspacesCount');
    if (!list) return;
    if (!list.isConnected) return;
    const vault = _vaultCurrent;
    if (!vault) {
      if (count) count.textContent = '';
      list.innerHTML = '<li class="s-empty">Could not load workspaces.</li>';
      return;
    }
    if (vault.unavailable) {
      if (count) count.textContent = '';
      list.innerHTML = `<li class="s-empty">${selfEsc(vault.detail || 'vault volume unavailable')}</li>`;
      return;
    }
    const workspaces = vault.workspace_rows || [];
    if (count) count.textContent = workspaces.length ? String(workspaces.length) : '';
    if (!workspaces.length) {
      list.innerHTML = '<li class="s-empty">No workspaces yet.</li>';
      return;
    }
    list.innerHTML = workspaces.map(workspace => `
      <li class="vault-workspace-row" data-path="${escAttr(workspace.path)}" role="button" tabindex="0" title="Open ${escAttr(_workspaceDisplayName(workspace))}">
        <span class="vault-workspace-name">${selfEsc(_workspaceDisplayName(workspace))}</span>
        <span class="vault-workspace-resources" data-workspace-id="${escAttr(workspace.name)}">Loading resources…</span>
        <span class="p-caret">›</span>
      </li>`).join('');
    list.querySelectorAll('.vault-workspace-row').forEach(row => {
      row.addEventListener('click', () => goToWorkspace(row.getAttribute('data-path')));
    });
    vaultRefreshWorkspaceResources();
  }

  // Populate #sidebar with the vault root's real file tree. Same
  // renderer as the self view (renderSidebarFileTree) — icons, git
  // decorations, notebook dots, hidden-files toggle, symlink legend. No
  // Meta section: the vault tab shows the root exactly as on disk.
  async function vaultPopulateSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar || !currentWorkspace || currentWorkspace.name !== VAULT_WORKSPACE_ID) return;
    const rootPath = currentWorkspace.path;
    try {
      await _sidebarEnsureWorktrees(rootPath);
      const fileRoot = _sidebarScopedRoot(rootPath);
      const files = await _sidebarFetchWorkspaceFiles(fileRoot);
      const recentFiles = await _sidebarResolveRecentFiles(files, fileRoot);
      if (!document.body.classList.contains('vault-active')) return;
      if (!currentWorkspace || currentWorkspace.path !== rootPath) return;
      if (_sidebarScopedRoot(rootPath) !== fileRoot) return;
      _sidebarRememberAvailableExtensions(files);
      _sidebarMaybeLogRecentDiagnostics(files, fileRoot);
      _rememberNotebookFolders(fileRoot, files);

      const activePath = _workspaceDocRoot === fileRoot ? (_workspaceDocPath || null) : null;
      const overviewActive = !activePath ? ' active' : '';
      let sbHtml = `<div class="sidebar-overview-row"><a class="sidebar-file${overviewActive}" data-vault-overview="1" onclick="vaultShowOverview()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Overview</span></a>${_sidebarFileConfigCogHtml()}</div>`;
      sbHtml += _sidebarRecentSelectorsHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(rootPath);
      sbHtml += _sidebarWorktreePickerHtml(rootPath);
      sbHtml += symlinkLegendHtml();
      sbHtml += _sidebarWorktreeScopeStartHtml(rootPath);
      sbHtml += _sidebarRecentSectionHtml(recentFiles, activePath, fileRoot, {resolved: true});
      sbHtml += _sidebarFilesTitle(fileRoot);
      sbHtml += renderSidebarFileTree(buildSidebarTree(files), 0, '', {scope: `vault:${fileRoot}`, autoOpen: _AUTO_OPEN_VAULT, activePath, root: fileRoot});
      sbHtml += _sidebarWorktreeScopeEndHtml(rootPath);
      sidebar.innerHTML = sbHtml;
      // Fast first decoration pass (cached + rate-limited server-side);
      // the shared 6s poll keeps it fresh afterwards.
      _sidebarGitStatusRefresh();
    } catch (e) {
      sidebar.innerHTML = '<div class="sidebar-title">Vault</div>';
    }
  }

  // Toggle hidden-files visibility for the vault sidebar. Mirrors
  // selfToggleDotFiles().
  function vaultToggleDotFiles(checked) {
    showWorkspaceDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    _storeSidebarFileConfig();
    vaultPopulateSidebar();
  }

  async function initCerebro(initialPath) {
    document.body.classList.add('cerebro-active');
    document.title = 'Cerebro';
    // Re-render the tab strip so the Cerebro tab shows up as active.
    if (typeof workspaceTabsRender === 'function') workspaceTabsRender();
    // Open ancestors of the initial file so it's visible in the tree.
    if (initialPath) {
      const parts = initialPath.split('/');
      let acc = '';
      for (let i = 0; i < parts.length - 1; i++) {
        acc = acc ? `${acc}/${parts[i]}` : parts[i];
        cerebroExpanded.add(acc);
        _treeSetOpen('cerebro', acc, true);
      }
    }
    // Paint the file tree immediately from the last-known data so the
    // sidebar isn't blank for the round-trip to /api/cerebro/tree on
    // every tab switch. cerebroRefresh() then reconciles in the
    // background.
    if (cerebroTreeData && cerebroTreeData.length) {
      cerebroRenderTree();
    } else {
      const tree = document.getElementById('cerebroTree');
      if (tree) tree.innerHTML = '<ul><li><div class="row"><span class="caret">&nbsp;</span><span class="icon">...</span><span class="name">Loading...</span></div></li></ul>';
    }
    afterPageQuiet(() => {
      cerebroRefresh();
      if (!UI_CHECK) termOpenForCerebro();
    });
    if (initialPath) {
      // cerebroOpen can run in parallel with the tree refresh — the
      // file-content fetch and the tree fetch hit different endpoints.
      cerebroOpen(initialPath);
    }
    // The filter input is already in the shell; future refreshes use
    // its current value when they paint the tree.
    const f = document.getElementById('cerebroFilter');
    if (f) f.addEventListener('input', cerebroRenderTree);
  }

  async function cerebroRefresh() {
    try {
      cerebroTreeData = await _fetchCerebroTree();
    } catch { cerebroTreeData = []; }
    cerebroRenderTree();
  }

  function cerebroRenderTree() {
    const container = document.getElementById('cerebroTree');
    if (!container) return;
    const filterVal = (document.getElementById('cerebroFilter')?.value || '').toLowerCase();
    container.innerHTML = '<ul>' + cerebroTreeData.map(n => cerebroRenderNode(n, filterVal)).join('') + '</ul>';
    container.querySelectorAll('.row').forEach(row => {
      const path = row.getAttribute('data-path');
      const isDir = row.classList.contains('dir');
      row.addEventListener('click', () => {
        if (isDir) {
          const nowOpen = !cerebroExpanded.has(path);
          if (nowOpen) cerebroExpanded.add(path);
          else cerebroExpanded.delete(path);
          _treeSetOpen('cerebro', path, nowOpen);
          cerebroRenderTree();
        } else {
          cerebroOpen(path);
        }
      });
    });
  }

  function cerebroRenderNode(node, filterVal) {
    const path = node.path;
    if (node.type === 'dir') {
      const matches = !filterVal || nodeMatchesFilter(node, filterVal);
      if (!matches) return '';
      const open = cerebroExpanded.has(path) || !!filterVal;
      const caret = node.children && node.children.length ? (open ? '▾' : '▸') : '&nbsp;';
      const icon = '📁';
      const children = open && node.children
        ? '<ul>' + node.children.map(c => cerebroRenderNode(c, filterVal)).join('') + '</ul>'
        : '';
      return `<li>
        <div class="row dir${symlinkClass(node)}" data-path="${cerebroEsc(path)}"${symlinkTitle(node)}>
          <span class="caret">${caret}</span>
          <span class="icon">${icon}</span>
          ${symlinkMarker(node)}<span class="name">${cerebroEsc(node.name)}</span>
        </div>${children}
      </li>`;
    }
    // File
    if (filterVal && !node.name.toLowerCase().includes(filterVal)) return '';
    const kind = node.type === 'markdown' ? 'markdown' : (node.type === 'text' ? 'text' : 'file');
    const icon = node.type === 'markdown' ? '📄' : (node.type === 'text' ? '📝' : '📦');
    const active = path === cerebroActivePath ? ' active' : '';
    return `<li>
      <div class="row ${kind}${active}${symlinkClass(node)}" data-path="${cerebroEsc(path)}"${symlinkTitle(node)}>
        <span class="caret">&nbsp;</span>
        <span class="icon">${icon}</span>
        ${symlinkMarker(node)}<span class="name">${cerebroEsc(node.name)}</span>
        <span class="size">${cerebroFormatSize(node.size)}</span>
      </div>
    </li>`;
  }

  function nodeMatchesFilter(node, filterVal) {
    if (node.name.toLowerCase().includes(filterVal)) return true;
    if (node.type === 'dir' && node.children) {
      return node.children.some(c => nodeMatchesFilter(c, filterVal));
    }
    return false;
  }

  function cerebroFormatSize(bytes) {
    if (!bytes && bytes !== 0) return '';
    if (bytes < 1024) return bytes + 'B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'K';
    return (bytes / (1024 * 1024)).toFixed(1) + 'M';
  }

  function cerebroEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  async function cerebroOpen(relPath) {
    cerebroActivePath = relPath;
    // Update URL without reloading.
    const u = new URL(window.location);
    u.searchParams.set('view', 'knowledge');
    u.searchParams.set('path', relPath);
    history.replaceState(null, '', u);
    cerebroRenderTree();  // refresh highlight

    const pane = document.getElementById('cerebroPane');
    if (!pane) return;
    // Cerebro paths are normally relative to content/. The shared
    // `.claude/` subtree is the exception — it lives at the monorepo
    // root and is surfaced as a virtual top-level entry.
    const isShared = relPath.startsWith('.claude/') || relPath === '.claude';
    const full = isShared ? relPath : 'content/' + relPath;
    const isMd = /\.(md|markdown)$/i.test(relPath);
    const isJson = /\.json$/i.test(relPath);
    const isCsv = /\.csv$/i.test(relPath);
    const isHtml = /\.(html|htm)$/i.test(relPath);

    pane.innerHTML = `
      <div class="k-crumbs">
        <span class="path">content/${cerebroEsc(relPath)}</span>
      </div>
      <div id="kDoc" class="doc"><p style="color:var(--text-secondary)">Loading…</p></div>`;
    const doc = document.getElementById('kDoc');

    if (isMd) {
      try {
        const r = await fetch('/api/markdown?path=' + encodeURIComponent(full));
        if (!r.ok) {
          const msg = await r.json().catch(() => ({}));
          doc.innerHTML = `<p style="color:var(--red)">Error: ${cerebroEsc(msg.detail || r.statusText)}</p>`;
          return;
        }
        const body = await r.json();
        const fm = body.frontmatter || {};
        const fmChips = Object.keys(fm).length ? (
          '<div class="fm-chips">' +
          ['date', 'type', 'scope', 'workspaces', 'tags', 'people'].filter(k => k in fm).map(k => {
            const v = Array.isArray(fm[k]) ? fm[k].join(', ') : String(fm[k] == null ? '' : fm[k]);
            return `<span class="fm-chip"><b>${cerebroEsc(k)}:</b> ${cerebroEsc(v)}</span>`;
          }).join('') + '</div>'
        ) : '';
        pane.innerHTML = `
          <div class="k-crumbs">
            <span class="path">content/${cerebroEsc(relPath)}</span>
            <a class="open-ext" href="/view?path=${encodeURIComponent(full)}" target="_blank">open in new tab ↗</a>
          </div>
          ${fmChips}
          <div class="doc">${body.html}</div>`;
        // Run highlight.js on fresh code blocks if available.
        await ensureHighlight().catch(() => {});
        if (window.hljs) {
          pane.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
        }
      } catch (e) {
        doc.innerHTML = `<p style="color:var(--red)">Error: ${cerebroEsc(e.message || e)}</p>`;
      }
      return;
    }

    if (isHtml) {
      const mode = getHtmlViewPref(full);
      cerebroRenderHtml(pane, relPath, full, mode);
      return;
    }

    if (isJson || isCsv) {
      try {
        const r = await fetch('/api/cerebro/file?path=' + encodeURIComponent(full));
        if (!r.ok) {
          const msg = await r.json().catch(() => ({}));
          doc.innerHTML = `<p style="color:var(--red)">Error: ${cerebroEsc(msg.detail || r.statusText)}</p>`;
          return;
        }
        const body = await r.json();
        if (isJson) {
          let pretty = body.content;
          let valid = true;
          try { pretty = JSON.stringify(JSON.parse(body.content), null, 2); } catch { valid = false; }
          const warn = valid ? '' : '<div class="fm-chips"><span class="fm-chip" style="background:#3c1a1a;color:#f0938a">⚠ invalid JSON — showing raw text</span></div>';
          pane.innerHTML = `
            <div class="k-crumbs">
              <span class="path">content/${cerebroEsc(relPath)}</span>
            </div>
            ${warn}
            <div class="doc"><pre><code class="language-json">${cerebroEsc(pretty)}</code></pre></div>`;
          await ensureHighlight().catch(() => {});
          if (window.hljs) {
            pane.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
          }
        } else {
          const rows = cerebroParseCSV(body.content);
          const nCols = rows[0]?.length || 0;
          pane.innerHTML = `
            <div class="k-crumbs">
              <span class="path">content/${cerebroEsc(relPath)}</span>
              <span style="margin-left:8px;color:var(--text-secondary);font-size:11px">${nCols} cols</span>
            </div>
            <div class="doc">${cerebroRenderCSV(rows)}</div>`;
          cerebroAttachCSVFilter();
        }
      } catch (e) {
        doc.innerHTML = `<p style="color:var(--red)">Error: ${cerebroEsc(e.message || e)}</p>`;
      }
      return;
    }

    doc.innerHTML = `<p style="color:var(--text-secondary)">No inline viewer for this file type. Open it from iTerm with <code>open ${cerebroEsc(full)}</code> or paste the path into the terminal.</p>`;
  }

  // Sticky per-file HTML-view preference (rendered vs source). Both the
  // Cerebro viewer and the workspace doc pane use this so a file viewed in
  // one place comes back the same way the next time.
  function getHtmlViewPref(absPath, fallback = 'rendered') {
    try { return localStorage.getItem('htmlView:' + absPath) || fallback; } catch { return fallback; }
  }
  function setHtmlViewPref(absPath, mode) {
    try { localStorage.setItem('htmlView:' + absPath, mode); } catch {}
  }

  // Minimal RFC-4180 CSV parser — handles quoted fields, escaped quotes,
  // and both LF/CRLF line endings. Embedded newlines inside quoted fields
  // are preserved.
  function cerebroParseCSV(text) {
    const rows = [];
    let row = [];
    let field = '';
    let inQuotes = false;
    let fieldStarted = false;
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (inQuotes) {
        if (c === '"') {
          if (text[i+1] === '"') { field += '"'; i++; }
          else { inQuotes = false; }
        } else {
          field += c;
        }
      } else {
        if (c === '"' && !fieldStarted) {
          inQuotes = true;
        } else if (c === ',') {
          row.push(field); field = ''; fieldStarted = false;
        } else if (c === '\n' || c === '\r') {
          if (c === '\r' && text[i+1] === '\n') i++;
          row.push(field); field = ''; fieldStarted = false;
          rows.push(row); row = [];
        } else {
          field += c; fieldStarted = true;
        }
      }
    }
    if (field !== '' || row.length > 0) { row.push(field); rows.push(row); }
    // Drop a trailing empty row caused by a final newline.
    if (rows.length && rows[rows.length-1].length === 1 && rows[rows.length-1][0] === '') rows.pop();
    return rows;
  }

  function cerebroRenderCSV(rows) {
    if (!rows.length) return '<p style="color:var(--text-secondary)">Empty CSV</p>';
    const headers = rows[0];
    const data = rows.slice(1);
    let html = '<div class="csv-toolbar">'
      + '<input id="csvFilter" type="search" placeholder="Filter rows… (any cell substring match)" autocomplete="off" spellcheck="false">'
      + `<span id="csvCount" class="csv-count">${data.length} rows</span>`
      + '</div>';
    html += '<div class="csv-wrap"><table class="csv-table"><thead><tr>';
    headers.forEach(h => { html += `<th>${cerebroEsc(h)}</th>`; });
    html += '</tr></thead><tbody>';
    data.forEach(r => {
      html += '<tr>';
      // Pad short rows so cells align under headers.
      for (let i = 0; i < headers.length; i++) {
        html += `<td>${cerebroEsc(r[i] == null ? '' : r[i])}</td>`;
      }
      html += '</tr>';
    });
    html += '</tbody></table></div>';
    return html;
  }

  // Renders an HTML file in Cerebro. `mode` is "rendered" (iframe) or
  // "code" (syntax-highlighted source). Stores the chosen mode per-file
  // so the next open lands in the same view.
  async function cerebroRenderHtml(pane, relPath, full, mode) {
    const toolbar = `
      <div class="k-crumbs">
        <span class="path">${full.startsWith('.claude/') ? '' : 'content/'}${cerebroEsc(relPath)}</span>
        <span class="html-toolbar" style="margin-left:auto;display:flex;gap:4px">
          <button class="html-toggle ${mode==='rendered'?'active':''}" data-mode="rendered">🖼 Rendered</button>
          <button class="html-toggle ${mode==='code'?'active':''}" data-mode="code">&lt;/&gt; Code</button>
        </span>
      </div>`;
    if (mode === 'rendered') {
      const src = '/api/cerebro/asset?path=' + encodeURIComponent(full);
      // Same iframe re-mount guard as _workspaceRenderHtml — avoids a white
      // flash on every WS index-updated event.
      const existing = pane.querySelector('iframe.html-iframe');
      const activeBtn = pane.querySelector('.html-toolbar .html-toggle.active');
      if (existing && existing.getAttribute('src') === src
          && activeBtn && activeBtn.getAttribute('data-mode') === 'rendered') {
        return;
      }
      pane.innerHTML = toolbar + `<iframe class="html-iframe" src="${src}" onload="applyIframeDarkMode(this)"></iframe>`;
    } else {
      try {
        const r = await fetch('/api/cerebro/file?path=' + encodeURIComponent(full));
        if (!r.ok) {
          const msg = await r.json().catch(() => ({}));
          pane.innerHTML = toolbar + `<div class="doc"><p style="color:var(--red)">Error: ${cerebroEsc(msg.detail || r.statusText)}</p></div>`;
        } else {
          const body = await r.json();
          await ensureHighlight().catch(() => {});
          pane.innerHTML = toolbar + `<div class="doc"><pre><code class="language-html">${cerebroEsc(body.content)}</code></pre></div>`;
          if (window.hljs) {
            pane.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
          }
        }
      } catch (e) {
        pane.innerHTML = toolbar + `<div class="doc"><p style="color:var(--red)">Error: ${cerebroEsc(e.message || e)}</p></div>`;
      }
    }
    // Wire toggle clicks. Each click swaps mode, persists, re-renders.
    pane.querySelectorAll('.html-toggle').forEach(btn => {
      btn.addEventListener('click', () => {
        const next = btn.getAttribute('data-mode');
        if (next === mode) return;
        setHtmlViewPref(full, next);
        cerebroRenderHtml(pane, relPath, full, next);
      });
    });
  }

  // Wires up the CSV filter input. Hides rows whose joined-cell text
  // doesn't contain the query (case-insensitive, single substring). The
  // header row never hides. We pre-cache lowercase text once so typing
  // stays cheap even on thousands of rows.
  function cerebroAttachCSVFilter() {
    const inp = document.getElementById('csvFilter');
    const tbody = document.querySelector('.csv-table tbody');
    const countEl = document.getElementById('csvCount');
    if (!inp || !tbody) return;
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const rowTexts = rows.map(r => r.textContent.toLowerCase());
    const total = rows.length;
    inp.addEventListener('input', () => {
      const q = inp.value.trim().toLowerCase();
      let shown = 0;
      for (let i = 0; i < rows.length; i++) {
        const match = !q || rowTexts[i].includes(q);
        rows[i].style.display = match ? '' : 'none';
        if (match) shown++;
      }
      if (countEl) countEl.textContent = q ? `${shown} of ${total} rows` : `${total} rows`;
    });
  }

  // Terminal panel for the Knowledge pseudo-workspace: claude session rooted at knowledge/.
  async function termOpenForCerebro() {
    // Mirror termOpenForWorkspace, but wired to the __cerebro__ pseudo-workspace.
    if (!_termIsScopeActive(CEREBRO_WORKSPACE_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(CEREBRO_WORKSPACE_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForWorkspace(CEREBRO_WORKSPACE_ID);
    termStartPeriodicRefresh();
  }

  async function termRefreshSessionsByWorkspaceId(pid) {
    // Fetches the live session list and re-renders the pill row.
    let fresh = [];
    let ok = false;
    const vaultId = _termVaultId();
    const sessionCacheKey = _termSessionsKey(pid, vaultId);
    try {
      const r = await fetch('/api/term/sessions?workspace_id=' + encodeURIComponent(pid) + _vaultQuery(vaultId));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(sessionCacheKey, fresh);
    // Stale-response guard — see termRefreshSessions for why.
    if (pid !== _termActiveWorkspaceId() || vaultId !== _termVaultId()) return ok;
    // Failed fetch → keep the last-known list (see termRefreshSessions).
    termSessions = ok ? fresh : (_termSessionsCache.get(sessionCacheKey) || []);
    if (ok) {
      // Forget dead/backoff bookkeeping for sessions tmux no longer has.
      const live = new Set(termSessions.map(s => s.name));
      for (const n of Array.from(termDeadSessions)) {
        if (!live.has(n)) termDeadSessions.delete(n);
      }
      for (const n of Object.keys(termReconnectAttempts)) {
        if (!live.has(n)) delete termReconnectAttempts[n];
      }
    }
    termRenderSessionList();
    return ok;
  }

  // Live notebook execution events share the global authenticated WebSocket
  // but are applied only to the currently-open notebook. Each event has a
  // monotonically increasing per-run sequence; a gap triggers a full
  // /api/nb + /api/nb/live reconciliation rather than rendering partial or
  // out-of-order output.
  const _nbLivePaths = new Set();
  let _nbLiveEventChain = Promise.resolve();

  function _nbLiveKey(vaultId, relPath) {
    return `${String(vaultId || '')}::${String(relPath || '')}`;
  }

  function _currentOpenNotebookRelPath() {
    if (!currentWorkspace || !_workspaceDocPath || !/\.ipynb$/i.test(_workspaceDocPath)) return null;
    const root = _workspaceDocRoot || currentWorkspace.path;
    if (root !== currentWorkspace.path) return null;
    const vault = _notebookVaultContext(currentWorkspace);
    return _vaultRelativeNotebookPathOrNull(
      currentWorkspace.path, _workspaceDocPath, vault.vaultRoot,
    );
  }

  async function _reconcileOpenNotebook(relPath, vaultId = null) {
    if (_currentOpenNotebookRelPath() !== relPath) return;
    if (vaultId && vaultId !== _workspaceVaultId(currentWorkspace)) return;
    await openWorkspaceDoc(_workspaceDocPath, { preserveScroll: true });
  }

  async function _handleNotebookExecutionEvent(event) {
    if (!event || !event.path) return;
    const relPath = String(event.path);
    const vaultId = String(event.vault || '');
    const liveKey = _nbLiveKey(vaultId, relPath);
    const phase = String(event.phase || '');
    const terminal = phase === 'finished' || phase === 'failed' || phase === 'interrupted';
    if (phase === 'started' || phase === 'output' || phase === 'execution-count') {
      _nbLivePaths.add(liveKey);
    }
    if (terminal) _nbLivePaths.delete(liveKey);

    if (vaultId && vaultId !== _workspaceVaultId(currentWorkspace)) return;
    if (_currentOpenNotebookRelPath() !== relPath) return;
    if (phase === 'started' || terminal) {
      await _reconcileOpenNotebook(relPath, vaultId);
      return;
    }
    if (phase !== 'output' && phase !== 'execution-count') return;

    const cellId = String(event.cell_id || '');
    if (!cellId) {
      await _reconcileOpenNotebook(relPath, vaultId);
      return;
    }
    let wrap = document.querySelector(`.nb-cell-interactive[data-cell-id="${CSS.escape(cellId)}"]`);
    if (!wrap) {
      await _reconcileOpenNotebook(relPath, vaultId);
      return;
    }

    const incomingSequence = Number(event.sequence);
    const currentSequence = Number(wrap.getAttribute('data-live-sequence'));
    if (!Number.isFinite(incomingSequence) || !Number.isFinite(currentSequence)
        || incomingSequence > currentSequence + 1) {
      await _reconcileOpenNotebook(relPath, vaultId);
      return;
    }
    // Reconciliation may already have included this event in its /live
    // snapshot while it was queued behind an earlier transition.
    if (incomingSequence <= currentSequence) return;

    if (event.execution_count != null) {
      const count = Number(event.execution_count);
      if (Number.isFinite(count)) {
        wrap.setAttribute('data-exec-count', String(count));
        const gutter = wrap.querySelector('.nb-exec');
        if (gutter) gutter.textContent = `[${count}]`;
      }
    }

    if (phase === 'output') {
      const outputs = wrap.querySelector(':scope > .nb-outputs');
      const body = outputs && outputs.querySelector('.nb-outputs-body');
      if (!body) {
        // The started snapshot should always include the running placeholder.
        // If an extension/external mutation removed it, reconcile rather than
        // inventing incomplete notebook chrome in-place.
        await _reconcileOpenNotebook(relPath, vaultId);
        return;
      }
      if (event.reset || event.operation === 'clear') body.innerHTML = '';
      if (event.output) {
        const displayId = event.output.display_id ? String(event.output.display_id) : '';
        let existing = null;
        if (event.operation === 'replace' && displayId) {
          existing = body.querySelector(`[data-display-id="${CSS.escape(displayId)}"]`);
        }
        const rendered = _renderNbOutput(event.output);
        if (existing) existing.outerHTML = rendered;
        else body.insertAdjacentHTML('beforeend', rendered);
      }
    }
    wrap.setAttribute('data-live-sequence', String(incomingSequence));
  }

  // WS live refresh — re-render current view (home panel or workspace view)
  // on index-updated. The workspace view also has a 2s mtime poller as
  // fallback, but WS refreshes within ~50ms so the sidebar + dashboard
  // reflect new files without a manual reload.
  let _liveWsSubscribed = false;
  function subscribeLiveWS() {
    if (_liveWsSubscribed) return;
    _liveWsSubscribed = true;
    let ws = null;
    let delay = 1000;
    let lastTs = null;
    let hasConnected = false;
    const MAX_DELAY = 30000;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${location.host}/ws`);
      ws.onopen = () => {
        delay = 1000;
        try { ws.send('hello'); } catch {}
        // Events emitted while the socket was down cannot be replayed from the
        // socket itself. Re-open the current notebook once after each reconnect
        // so /api/nb/live supplies the complete sequence snapshot before new
        // deltas arrive.
        const reconnectNotebook = hasConnected ? _currentOpenNotebookRelPath() : null;
        const reconnectVaultId = reconnectNotebook && currentWorkspace
          ? _workspaceVaultId(currentWorkspace) : null;
        hasConnected = true;
        if (reconnectNotebook) {
          _nbLiveEventChain = _nbLiveEventChain
            .then(() => _reconcileOpenNotebook(reconnectNotebook, reconnectVaultId))
            .catch(() => {});
        }
      };
      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          if (event.type === 'notebook-execution') {
            _nbLiveEventChain = _nbLiveEventChain
              .then(() => _handleNotebookExecutionEvent(event))
              .catch(() => {});
            return;
          }
          if (event.type !== 'index-updated') return;
          if (event.ts && event.ts === lastTs) return;
          lastTs = event.ts;
          if (document.body.classList.contains('self-active')
                     && !currentRepo && !_workspaceDocEditing) {
            if (_workspaceDocPath) openWorkspaceDoc(_workspaceDocPath, {preserveScroll: true});
            else {
              selfRefreshWorkbench();
              selfPopulateSidebar();
            }
          } else if (document.body.classList.contains('vault-active')
                     && !currentRepo && !_workspaceDocEditing) {
            if (_workspaceDocPath) openWorkspaceDoc(_workspaceDocPath, {preserveScroll: true});
            else vaultPopulateSidebar();
          } else if (document.body.classList.contains('assistant-active')) {
            if (_workspaceDocPath) {
              openWorkspaceDoc(_workspaceDocPath, {preserveScroll: true});
            } else if (window.AssistantView) {
              window.AssistantView.refresh();
            }
            if (ASSISTANT_ROOT) _refreshWorkspaceSidebar({preserveScroll: true});
          } else if (currentWorkspace && currentWorkspace.is_workspace
                     && !currentRepo && !_workspaceDocEditing) {
            const liveNotebook = _currentOpenNotebookRelPath();
            if (_workspaceDocPath) {
              const liveKey = _nbLiveKey(_workspaceVaultId(currentWorkspace), liveNotebook);
              if (!(liveNotebook && _nbLivePaths.has(liveKey))) {
                openWorkspaceDoc(_workspaceDocPath, {preserveScroll: true});
              }
            } else if (!document.body.classList.contains('self-active')) {
              showWorkspaceInfo({preserveScroll: true});
            }
          }
        } catch {}
      };
      ws.onclose = () => { setTimeout(connect, delay); delay = Math.min(delay * 2, MAX_DELAY); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
  }
  if (!UI_CHECK) subscribeLiveWS();

  // Start views only after all script state is initialized. afterPageQuiet
  // can run synchronously when this lazy-loaded script arrives after load.
  afterPageQuiet(loadRepos);
  if (!UI_CHECK) afterPageQuiet(() => setInterval(loadRepos, 8000), 1000);
  if (!UI_CHECK) afterPageQuiet(() => setInterval(refreshDiff, 5000), 1000);
  // Workspace tab strip: initial render + periodic refresh.
  afterPageQuiet(vaultRefresh, 250);
  afterPageQuiet(workspaceTabsRefresh);
  if (!UI_CHECK) afterPageQuiet(workspaceTabsStartPolling, 1000);

  // Cerebro view: when URL carries ?view=cerebro, we bypass the
  // workspace/repo init path entirely and render the mdview-style browser.
  const initialParams = new URLSearchParams(location.search);
  const urlView = initialParams.get('view');
  const urlCerebroPath = initialParams.get('path') || '';
  if (urlView === 'cerebro') {
    initCerebro(urlCerebroPath);
  } else if (urlView === 'assistant') {
    initAssistant(initialParams.get('task') || '', {
      subview: initialParams.get('subview') || '',
      meeting: initialParams.get('meeting') || '',
      workspace: initialParams.get('assistant_workspace') || '',
    });
  } else if (urlView === 'productivity') {
    initSelf();
    if (initialParams.get('subview') === 'logs') selfShowLogs();
    else if (initialParams.get('subview') === 'admin') selfShowAdmin();
    else if (initialParams.get('subview') === 'code-search') showScopedCodeSearch();
  } else if (urlView === 'vault') {
    initVaultView(initialParams.get('vault') || currentVaultId);
  } else if (urlView === 'code-search') {
    // Retired standalone route: keep old bookmarks useful by landing on the
    // framework-scoped Code Search subtab.
    initSelf();
    showScopedCodeSearch();
  } else if (urlView === 'logs') {
    initSelf();
    selfShowLogs();
  }

  // Workspace and default-Home startup also wait for all state declarations.
  if (_effectiveWorkspace) {
    const provisionalName = (_effectiveWorkspace.replace(/\/+$/, '').split('/').pop() || 'Workspace');
    currentWorkspace = {
      name: provisionalName,
      path: _effectiveWorkspace,
      is_workspace: true,
      description: 'Opening workspace dashboard...',
      repos: [],
    };
    document.body.classList.remove('cerebro-active', 'self-active', 'assistant-active', 'vault-active', 'has-diff-tabs');
    document.body.classList.add('workspace-active');
    document.getElementById('diffTabs').style.display = 'none';
    paintWorkspaceShell();
    // Share the in-flight /api/repos promise with loadRepos +
    // workspaceTabsRefresh instead of firing a third network call (all three
    // callers resolve to the same response on initial load).
    fetchRepos().then(workspaces => {
      workspacesList = workspaces;
      const workspace = workspaces.find(p => p.path === _effectiveWorkspace);
      if (workspace) {
        selectRepo(workspace.path);
      }
    });
  } else if (urlRepo) {
    fetchRepos().then(workspaces => {
      workspacesList = workspaces;
      const workspace = workspaces.find(p => p.repos.some(r => r.path === urlRepo));
      if (workspace) {
        selectRepo(workspace.path);
        if (workspace.repos.length > 1) {
          const targetRepo = workspace.repos.find(r => r.path === urlRepo);
          if (targetRepo) selectWorkspaceRepo(targetRepo.path);
        }
      }
    });
  } else if (urlView === 'cerebro' || urlView === 'assistant' || urlView === 'productivity' || urlView === 'vault' || urlView === 'code-search' || urlView === 'logs') {
    // These views were initialized by the dispatch above.
  } else {
    // No explicit target means the framework-owned Productivity home.
    initSelf();
  }
