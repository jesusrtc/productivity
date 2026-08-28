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
  let projectsList = [];
  let currentProject = null;
  let currentRepoInProject = null;
  let workspaceCatalog = [];
  let _workspaceCatalogInFlight = null;

  const urlRepo = new URLSearchParams(location.search).get('repo');

  // Global catalog: every registered workspace and its projects.  It is the
  // key to keeping tabs from several workspaces alive at once; selecting a
  // workspace no longer mutates the backend's process-wide root.
  let _reposInFlight = null;
  function fetchWorkspaceCatalog() {
    if (_workspaceCatalogInFlight) return _workspaceCatalogInFlight;
    const p = fetch('/api/workspaces/projects')
      .then(r => r.ok ? r.json() : {workspaces: []})
      .then(data => {
        workspaceCatalog = Array.isArray(data.workspaces) ? data.workspaces : [];
        currentWorkspaceId = data.active || currentWorkspaceId;
        return data;
      })
      .catch(() => ({workspaces: workspaceCatalog || []}));
    _workspaceCatalogInFlight = p;
    p.finally(() => { if (_workspaceCatalogInFlight === p) _workspaceCatalogInFlight = null; });
    return p;
  }

  function fetchRepos() {
    if (_reposInFlight) return _reposInFlight;
    const p = fetchWorkspaceCatalog()
      .then(data => (data.workspaces || []).flatMap(ws => ws.project_rows || []))
      .catch(() => []);
    _reposInFlight = p;
    p.finally(() => { if (_reposInFlight === p) _reposInFlight = null; });
    return p;
  }

  // Project ids remain stable for paths, terminal sessions, and API calls.
  // Only this helper should decide what human-facing label to render.
  function _projectDisplayName(project) {
    // The detail request may be newer than an in-flight catalog poll. Keep
    // the active tab aligned with the Overview heading in that short window.
    const activeDisplayName = currentProject && project
      && currentProject.path === project.path && currentProject.display_name;
    return String(activeDisplayName || (project && (project.display_name || project.name)) || 'Project');
  }

  let currentWorkspaceId = null;
  async function workspaceRefresh() {
    try {
      const data = await fetchWorkspaceCatalog();
      currentWorkspaceId = data.active || currentWorkspaceId;
      if (typeof renderRepoTabs === 'function' && currentProject) renderRepoTabs();
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
    if (window.marked) return Promise.resolve();
    return loadScriptOnce('/static/vendor/marked@12.0.1/marked.min.js');
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
      projectsList = await fetchRepos();
      const sel = document.getElementById('repoSelect');
      sel.innerHTML = '<option value="">Select project...</option>';
      projectsList.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.path;
        opt.textContent = (p.is_project ? '\u{1F4E6} ' : '') + _projectDisplayName(p);
        if (p.is_project) opt.style.color = '#58a6ff';
        if (p.name === (currentProject && currentProject.name)) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (err) {}
  }

  async function selectRepo(projectKey) {
    if (!projectKey) return;
    currentProject = projectsList.find(p => p.path === projectKey)
      || projectsList.find(p => p.name === projectKey);
    if (!currentProject) return;
    _sidebarActivateFileConfig();

    _contextSubView = 'overview';

    if (currentProject.is_project) projTabsSetOpen(currentProject.path, true);

    document.title = _projectDisplayName(currentProject);
    // replaceState (not pushState): the caller (goToProject / popstate
    // handler / initial-load dispatch) has already settled the URL. A
    // pushState here would create a duplicate history entry, breaking
    // the back button. replaceState normalizes (e.g., ?repo= → ?project=)
    // without adding to history.
    const url = new URL(window.location);
    url.searchParams.set('project', currentProject.path);
    url.searchParams.delete('repo');
    history.replaceState(null, '', url);

    renderRepoTabs();

    if (currentProject.is_project) {
      // Restore the last-viewed doc for this project (if any). Switching
      // between projects should land the user where they left off, not
      // force them through Dashboard every time.
      currentRepo = null;
      currentRepoInProject = null;
      document.getElementById('diffTabs').style.display = 'none';
      document.body.classList.remove('has-diff-tabs');
      // A real project is active — reveal the attrs bar.
      document.body.classList.add('project-active');
      const hydrateProjectChrome = () => {
        refreshAttrsBar();
        // The project shell (or a remembered document) is already painted.
        // Sidebar/dashboard hydration must never replace it with a dashboard
        // loading spinner; showProjectInfo's final race guard will paint the
        // dashboard only when no document owns the content area.
        showProjectInfo({keepShell: true});
      };
      // Decide synchronously whether a doc or the dashboard will paint
      // the content area. On cold full-page loads, keep the server-rendered
      // shell isolated from sidebar/dashboard fetches; warm in-app switches
      // hydrate immediately.
      // Set `_projDocPath` up-front so showProjectInfo's dashboard-paint
      // race guard knows a doc is on its way and doesn't stomp the doc
      // render. If no remembered doc, _projDocPath is null and
      // showProjectInfo paints the dashboard as usual.
      const remembered = getLastProjectDoc(currentProject.path);
      _projDocPath = remembered || null;
      if (!remembered) paintProjectShell();
      afterColdPageQuiet(hydrateProjectChrome);
      if (remembered) openProjectDoc(remembered);
      // Project-scoped terminal panel: auto-open + attach latest session (if any).
      // Skip under ?ui_check=1 so headless validator reaches network idle.
      if (!(new URLSearchParams(location.search).get('ui_check') === '1')) {
        const terminalProjectId = currentProject.name;
        afterPageQuiet(() => {
          if (typeof _termIsScopeActive === 'function' && !_termIsScopeActive(terminalProjectId)) return;
          termOpenForProject(terminalProjectId);
        });
      }
      // Re-render project tabs so the active highlight tracks the selection.
      if (typeof projTabsRender === 'function') projTabsRender();
    } else {
      // Single repo — go straight to diff. Not a real project, so hide
      // the attrs bar (matches the else-branch below the project init).
      document.body.classList.remove('project-active');
      currentRepoInProject = currentProject.repos[0];
      currentRepo = currentRepoInProject.path;
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
        const repoName = currentRepoInProject ? currentRepoInProject.name : '';
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
        const dt = currentDiffTab === 'project' ? 'uncommitted' : currentDiffTab;
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

  function currentRepoRelativeToProject() {
    if (!currentRepo) return null;
    if (!currentProject || !currentProject.path) return currentRepo;
    const p = currentProject.path.endsWith('/') ? currentProject.path : currentProject.path + '/';
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
    // pattern used in projDocBody for doc comments.
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
    const repo = currentRepoRelativeToProject();
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
    if (!currentProject || !currentProject.path) {
      if (errEl) errEl.textContent = 'no project loaded';
      return false;
    }
    const {scope, sha} = currentDiffScope();
    const body = {
      path: currentProject.path,
      file: ctx.file,
      text: ctx.text,          // the highlighted code snippet — anchors the comment
      comment,
      kind: 'code',
      repo: currentRepoRelativeToProject(),
      // Reference labels only; NOT used to filter where the comment renders.
      scope,
      sha: sha || undefined,
    };
    try {
      const r = await fetch('/api/project-comments', {
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
    if (!currentProject || !currentProject.path) return;
    let comments = [];
    try {
      const r = await fetch('/api/project-comments?path=' + encodeURIComponent(currentProject.path));
      comments = r.ok ? await r.json() : [];
    } catch { return; }
    const repo = currentRepoRelativeToProject();
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
          await fetch('/api/project-comments', {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({path: currentProject.path, comment_id: id}),
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

  function treeFolderNames(node) {
    return Object.keys(node || {}).filter(k => k !== '__files__' && k !== '__entry__').sort();
  }

  function treeFolderEntry(node, folder, fullPath) {
    return (node && node[folder] && node[folder].__entry__) || { name: folder, path: fullPath, type: 'dir' };
  }

  function treeFiles(node) {
    return (node && node.__files__) || [];
  }

  // ─── Explorer secondary-click menu ────────────────────────────────────
  // One delegated menu serves the project, workspace, framework, and repo
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
    if (!root || !currentProject || root !== currentProject.path) return false;
    return _workspaceRelativeNotebookPathOrNull(root, '__lab_notebook_probe__.ipynb') !== null;
  }

  function _sidebarFilesTitle(root) {
    const create = _canCreateExecutableNotebook(root)
      ? '<button class="sidebar-title-action" type="button" onclick="event.stopPropagation();openNewNotebookDialog()" title="Choose a repository folder and create a notebook">＋ Notebook</button>'
      : '';
    return `<div class="sidebar-title sidebar-title-with-action"><span>Files</span>${create}</div>`;
  }

  function _explorerContextFromRow(row) {
    if (!row) return null;
    const kind = row.getAttribute('data-entry-kind');
    const path = row.getAttribute('data-entry-path');
    if (!kind || !path) return null;
    const isRepoTree = row.classList.contains('tree-file') || row.classList.contains('tree-dir');
    const root = row.getAttribute('data-entry-root')
      || (isRepoTree ? currentRepo : (currentProject && currentProject.path));
    if (!root) return null;
    return {kind, path, root, row, surface: isRepoTree ? 'repo' : 'project'};
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
    return `<button type="button" role="menuitem" data-explorer-action="${action}"${danger ? ' class="danger"' : ''}>
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
    const notebookAction = ctx.surface === 'project' && _canCreateExecutableNotebook(ctx.root)
      ? _explorerMenuButton('new-notebook', '◉', 'New notebook here', '')
      : '';
    menu.innerHTML = `
      <div class="ecm-label" title="${escAttr(ctx.path)}">${esc(ctx.path)}</div>
      ${_explorerMenuButton('open', firstIcon, firstLabel, ctx.kind === 'file' ? 'Enter' : '')}
      ${_explorerMenuButton('history', '⑂', 'View Git history', '')}
      ${_explorerMenuButton('copy-path', '⧉', 'Copy relative path', '')}
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
      if (row && row.isConnected) row.click();
      return;
    }
    if (action === 'copy-path') {
      const copied = await _copyToClipboard(ctx.path, null);
      closeExplorerContextMenu();
      explorerToast(copied ? `Copied ${ctx.path}` : 'Could not copy path', !copied);
      return;
    }
    closeExplorerContextMenu();
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
      ? 'New name ' : `Name in ${parent || 'workspace root'} `;
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
    const root = (ctx && ctx.root) || (currentProject && currentProject.path);
    if (!_canCreateExecutableNotebook(root)) {
      explorerToast('Open a repository inside the active workspace to create an executable notebook.', true);
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

    const createContext = ctx || {kind: 'folder', path: parent, root, surface: 'project'};
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
      const response = await fetch('/api/project-entry', {
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
      const response = await fetch('/api/project-entry', {
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
    if (typeof _projDocCache === 'undefined') return;
    const prefix = root + '|';
    for (const key of _projDocCache.keys()) {
      if (!key.startsWith(prefix)) continue;
      const cachedPath = key.slice(prefix.length);
      if (_explorerPathAffected(cachedPath, path, kind)) _projDocCache.delete(key);
    }
  }

  async function _explorerAfterMutation(state, result) {
    const {action, ctx} = state;
    const kind = state.kind || ctx.kind;
    const oldPath = ctx.path;
    const newPath = action === 'rename' ? result.renamed_to : result.entry;
    _explorerClearDocCache(ctx.root, oldPath, ctx.kind);
    if (typeof _projectSidebarCache !== 'undefined') _projectSidebarCache.delete(ctx.root);

    if (ctx.surface === 'repo' && currentRepo === ctx.root) {
      const previous = projectOpenFile;
      const wasAffected = _explorerPathAffected(previous, oldPath, ctx.kind);
      let reopen = previous;
      if (action === 'rename' && wasAffected) reopen = _explorerRenamedActivePath(previous, oldPath, newPath, ctx.kind);
      if (action === 'delete' && wasAffected) reopen = null;
      if (action.startsWith('create') && kind === 'file') reopen = newPath;
      await loadProjectView();
      if (reopen) await openProjectFile(reopen);
      else if (action === 'delete' && wasAffected) {
        projectOpenFile = null;
        document.getElementById('content').innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
      }
      return;
    }

    if (!currentProject || !currentProject.path) return;
    const activeFileRoot = _sidebarScopedRoot(currentProject.path);
    if (currentProject.path !== ctx.root && activeFileRoot !== ctx.root) return;
    const previous = _projDocPath;
    const wasAffected = _explorerPathAffected(previous, oldPath, ctx.kind);
    let reopen = previous;
    if (action === 'rename' && wasAffected) reopen = _explorerRenamedActivePath(previous, oldPath, newPath, ctx.kind);
    if (action === 'delete' && wasAffected) reopen = null;
    if (action.startsWith('create') && kind === 'file') reopen = newPath;

    if (document.body.classList.contains('self-active')) await selfPopulateSidebar();
    else if (document.body.classList.contains('workspace-active')) await workspacePopulateSidebar();
    else await _refreshProjectSidebar();

    if (reopen && reopen !== previous) await openProjectDoc(reopen, {root: ctx.root});
    else if (action === 'delete' && wasAffected) {
      setLastProjectDoc(ctx.root, null);
      if (document.body.classList.contains('self-active')) selfShowWorkbench();
      else if (document.body.classList.contains('workspace-active')) workspaceShowOverview();
      else showProjectDashboard();
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
      const response = await fetch(`/api/project-entry/history?path=${encodeURIComponent(ctx.root)}&file=${encodeURIComponent(ctx.path)}&limit=100`);
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
          const response = await fetch(`/api/project-entry/history-diff?path=${encodeURIComponent(ctx.root)}&file=${encodeURIComponent(ctx.path)}&sha=${encodeURIComponent(sha)}`);
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
  // Each tree (self / per-project / shared-claude / cerebro) is a scope.
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
    document.getElementById('tabProject').classList.toggle('active', tab === 'project');
    // Update commit tab active states
    document.querySelectorAll('.commit-tab').forEach(el => el.classList.remove('active'));
    if (tab.startsWith('commit:')) {
      const sha = tab.split(':')[1];
      document.querySelectorAll('.commit-tab').forEach(el => {
        if (el.getAttribute('onclick')?.includes(sha)) el.classList.add('active');
      });
    }
    if (tab === 'project') {
      loadProjectView();
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
    if (currentDiffTab === 'project' || currentDiffTab.startsWith('commit:')) return;
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
    const tab = currentDiffTab === 'project' ? 'branch' : currentDiffTab;
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
      if (currentDiffTab === 'project') loadProjectView();
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
      if (currentDiffTab === 'project') loadProjectView();
      else loadDiff();
    } catch (err) {
      alert('Error: ' + err.message);
    }
  }

  // ─── Project tab ───
  let fileTree = null;
  let projectOpenFile = null;
  let projectEditMode = false;
  let _repoFileRoot = null;
  function _activeRepoFileRoot() { return _repoFileRoot || currentRepo; }
  let showDotFiles = false;
  const SIDEBAR_FILE_CONFIG_LEGACY_KEY = 'labSidebarFileConfig-v1';
  const SIDEBAR_FILE_CONFIG_KEY_PREFIX = 'labSidebarFileConfig-v2:';
  const SIDEBAR_FILE_CONFIG_MIGRATION_KEY = 'labSidebarFileConfig-v1-migrated';
  const SIDEBAR_RECENT_MAX_MINUTES = 4320;
  const SIDEBAR_WORKTREE_DEFAULT_COLOR = '#6e7681';
  const SIDEBAR_FILE_CONFIG_DEFAULTS = Object.freeze({
    showHidden: false,
    showRecent: true,
    recentMinutes: 1440,
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

  function _sidebarNormalizeWorktreeFolder(value, projectRoot = '') {
    const requested = String(value || '').trim();
    return requested.startsWith('~/')
      ? requested
      : _sidebarNormalizeFolderPath(requested, projectRoot);
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

  function _sidebarNormalizeFileConfig(stored) {
    const recentMinutes = Number(stored && stored.recentMinutes);
    return {
      showHidden: !!(stored && stored.showHidden === true),
      showRecent: !stored || stored.showRecent !== false,
      recentMinutes: Number.isFinite(recentMinutes) && recentMinutes > 0
        ? Math.min(recentMinutes, SIDEBAR_RECENT_MAX_MINUTES)
        : SIDEBAR_FILE_CONFIG_DEFAULTS.recentMinutes,
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
    const project = typeof currentProject !== 'undefined' ? currentProject : null;
    const projectPath = _sidebarNormalizeFolderPath(project && project.path);
    return projectPath ? encodeURIComponent(projectPath) : '';
  }

  function _sidebarFileConfigStorageKey(scopeKey) {
    return scopeKey ? SIDEBAR_FILE_CONFIG_KEY_PREFIX + scopeKey : '';
  }

  function _sidebarCanMigrateLegacyFileConfig() {
    const project = typeof currentProject !== 'undefined' ? currentProject : null;
    const name = String(project && project.name || '');
    return !!project && name !== '__self__' && name !== '__workspace__';
  }

  function _loadSidebarFileConfig(scopeKey = _sidebarFileConfigScopeKey()) {
    if (!scopeKey) return _sidebarDefaultFileConfig();
    try {
      const storageKey = _sidebarFileConfigStorageKey(scopeKey);
      let raw = localStorage.getItem(storageKey);
      // The old setting was browser-global. Preserve it once by assigning it
      // to the first project opened after this upgrade; every other project
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
  let showProjectDotFiles = _sidebarFileConfig.showHidden;

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
    showProjectDotFiles = _sidebarFileConfig.showHidden;
    _sidebarAvailableExtensions = new Set();
    _sidebarRecentDiagnosticsPending = null;
    _sidebarClearWorktreeDiscovery();
    return true;
  }

  function _sidebarWorktreeBaseRoot() {
    if (currentRepo) return currentRepo;
    if (document.body && document.body.classList.contains('self-active')) return SELF_REPO_PATH;
    if (currentProject && currentProject.path) return currentProject.path;
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

  function _sidebarProjectRoot(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    return selected ? selected.path : baseRoot;
  }

  function _sidebarProjectLabel(baseRoot) {
    const selected = _sidebarSelectedFolder(baseRoot);
    return selected ? selected.label : 'Root';
  }

  function _sidebarProjectColor(baseRoot) {
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
    if (currentProject && String(currentProject.path || '') === scopeRoot) {
      const registered = Array.isArray(currentProject.repos)
        ? currentProject.repos.find(row => row && row.path)
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
    const projectRoot = _sidebarProjectRoot(baseRoot);
    const worktreeFolder = _sidebarActiveWorktreeFolder(baseRoot);
    if (!worktreeFolder) {
      _sidebarClearWorktreeDiscovery();
      return [];
    }
    try {
      return await _sidebarDiscoverWorktrees(worktreeFolder, {baseRoot: projectRoot});
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
    const projectRoot = _sidebarProjectRoot(baseRoot);
    const selected = String((_sidebarFileConfig.selectedWorktrees || {})[projectRoot] || '');
    if (!selected) return null;
    return _sidebarWorktreeFolders.find(row => row.path === selected) || null;
  }

  function _sidebarScopedRoot(baseRoot) {
    const selected = _sidebarSelectedWorktree(baseRoot);
    return selected ? selected.path : _sidebarProjectRoot(baseRoot);
  }

  function _sidebarWorktreeColor(path) {
    return _sidebarValidColor((_sidebarFileConfig.worktreeColors || {})[path]);
  }

  function _sidebarWorktreePickerHtml(baseRoot) {
    const projectRoot = _sidebarProjectRoot(baseRoot);
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
    return `<div class="sidebar-worktree-picker" data-project-root="${escAttr(projectRoot)}"><button class="sidebar-repo-history" type="button" data-base-root="${escAttr(baseRoot)}" onclick="sidebarOpenRepositoryHistory(this)" title="Open Git history for ${escAttr(selectedLabel)}" aria-label="Open Git history for ${escAttr(selectedLabel)}">${_SIDEBAR_GITHUB_ICON}</button>${rootControl}<input type="color" aria-label="Worktree color" title="Color for ${escAttr(selected ? selected.name : 'the selected worktree')}" data-worktree-path="${escAttr(selectedPath)}" value="${escAttr(color)}" onchange="sidebarSetWorktreeColor(this)"${selected ? '' : ' disabled'} /></div>`;
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
    return `<div class="sidebar-file-scope-buttons" role="group" aria-label="Project folders">${scopes.map(scope => {
      const active = scope.path === selectedPath;
      return `<button type="button" class="sidebar-file-scope-button${active ? ' active' : ''}" data-base-root="${escAttr(baseRoot)}" data-folder-path="${escAttr(scope.path)}" onclick="sidebarSelectFolder(this)" aria-pressed="${active ? 'true' : 'false'}" title="${escAttr(scope.title)}" style="--sidebar-project-color:${escAttr(scope.color)}"><span class="sidebar-file-scope-dot"></span><span>${esc(scope.label)}</span></button>`;
    }).join('')}</div>`;
  }

  function _sidebarWorktreeScopeStartHtml(baseRoot) {
    const folder = _sidebarSelectedFolder(baseRoot);
    const selected = _sidebarSelectedWorktree(baseRoot);
    if (!folder && !selected) return '';
    const color = selected ? _sidebarWorktreeColor(selected.path) : _sidebarProjectColor(baseRoot);
    const worktreeAttr = selected ? ` data-worktree-path="${escAttr(selected.path)}"` : '';
    const label = selected ? `${_sidebarProjectLabel(baseRoot)} · ${selected.name}` : _sidebarProjectLabel(baseRoot);
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

  function _sidebarRecentFiles(files, nowSeconds = Date.now() / 1000) {
    if (!_sidebarFileConfig.showRecent) return [];
    const cutoff = nowSeconds - (_sidebarFileConfig.recentMinutes * 60);
    const allowed = new Set(_sidebarFileConfig.extensions || []);
    return (files || [])
      .filter(file => {
        if (!file || file.type === 'dir' || !Number.isFinite(Number(file.mtime))) return false;
        if (Number(file.mtime) < cutoff) return false;
        return _sidebarFileConfig.trackMode === 'all'
          || allowed.has(_sidebarFileExtension(file.path || file.name));
      })
      .sort((a, b) => Number(b.mtime) - Number(a.mtime)
        || String(a.path || a.name).localeCompare(String(b.path || b.name)));
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

  async function _sidebarFetchProjectFiles(projectPath) {
    const url = `/api/project-files?path=${encodeURIComponent(projectPath)}&include_dotfiles=${showProjectDotFiles}`;
    const response = await fetch(url);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      _sidebarRecentLog('error', 'recent files source fetch failed ' + JSON.stringify({
        root: projectPath,
        status: response.status,
        detail: body.detail || response.statusText || 'request failed',
      }), {
        action: 'sidebar.recent.fetch',
        event_type: 'sidebar.recent.fetch_failed',
        target: projectPath,
        status_code: response.status,
      });
      throw new Error(body.detail || response.statusText || 'Could not load project files');
    }
    const files = await response.json();
    if (!Array.isArray(files)) {
      _sidebarRecentLog('error', 'recent files source returned invalid payload ' + JSON.stringify({
        root: projectPath,
        payload_type: files === null ? 'null' : typeof files,
      }), {
        action: 'sidebar.recent.fetch',
        event_type: 'sidebar.recent.invalid_payload',
        target: projectPath,
      });
      throw new Error('Invalid project files response');
    }
    return files;
  }

  function _sidebarFreshnessLabel(minutes) {
    const value = Number(minutes);
    if (value < 60) return `${value}m`;
    if (value < 1440) return `${value / 60}h`;
    return `${value / 1440}d`;
  }

  function _sidebarFileConfigButtonHtml() {
    const summary = [];
    if (_sidebarFileConfig.showHidden) summary.push('hidden');
    if (_sidebarFileConfig.showRecent) {
      summary.push(`recent ${_sidebarFreshnessLabel(_sidebarFileConfig.recentMinutes)}`);
    }
    const folderCount = (_sidebarFileConfig.folderScopes || []).length;
    if (folderCount) summary.push(`${folderCount} folder${folderCount === 1 ? '' : 's'}`);
    if (_sidebarActiveWorktreeFolder(_sidebarWorktreeBaseRoot())) summary.push('worktrees');
    return `<div class="sidebar-file-config-row"><button type="button" class="sidebar-file-config-button" onclick="openSidebarFileConfig()" title="Configure hidden and recently updated files"><span aria-hidden="true">&#x2699;</span> File view <span class="sidebar-file-config-summary">${esc(summary.join(' · ') || 'default')}</span></button></div>`;
  }

  function _sidebarRecentTreeModel(files) {
    const compactNode = (node, parentPath) => {
      const model = {files: treeFiles(node), folders: []};
      treeFolderNames(node).forEach(folder => {
        const labelParts = [folder];
        let path = parentPath ? `${parentPath}/${folder}` : folder;
        let child = node[folder];

        // Match the compact-folder behavior used by editors: a run of
        // folders with no files and exactly one child is one visual row.
        // Stop at a real branch so siblings such as core/src and core/tests
        // remain immediately recognizable.
        while (treeFiles(child).length === 0) {
          const childFolders = treeFolderNames(child);
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
    const projectRoot = _sidebarProjectRoot(baseRoot);
    return openRepositoryHistory({
      root: selected ? (selected.repo || selected.path) : _sidebarWorktreeRepositoryRoot(projectRoot),
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
    if (!path || !currentProject || !currentProject.path) return;
    return openExplorerHistory({
      kind: 'file',
      path: String(path),
      root: root || currentProject.path,
      row: null,
      surface: 'project',
    });
  }
  window.openSidebarFileHistory = openSidebarFileHistory;

  function _sidebarRecentSectionHtml(files, activePath, root = '') {
    const recent = _sidebarRecentFiles(files);
    if (!recent.length) return '';
    let html = `<div class="sidebar-title">Recently updated <span class="sidebar-title-count">${recent.length}</span></div>`;
    const scopeRoot = root || (currentProject && currentProject.path ? currentProject.path : 'global');
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
        nodeHtml += `<a class="sidebar-file sidebar-file-recent${activeCls}${symlinkClass(file)}" data-filepath="${esc(path)}" data-entry-kind="file" data-entry-path="${escAttr(path)}" data-entry-root="${escAttr(scopeRoot)}"${symlinkTitle(file)} onclick="openProjectDoc('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}',{root:'${safeRoot}'})" title="Recently updated · ${escAttr(path)}"><span class="sidebar-fname">${symlinkMarker(file)}${fileIconHtml(base, file)}${esc(base)}</span>${_sidebarGitHistoryButtonHtml(path, scopeRoot)}</a>`;
      });
      return nodeHtml;
    };

    html += renderNode(tree);
    return html;
  }

  function _sidebarConfigFolderCardHtml(row, {root = false, baseRoot = ''} = {}) {
    const path = root ? baseRoot : String(row && row.path || '');
    const fallback = path.split('/').filter(Boolean).pop() || 'Project';
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
          <label>Name<input type="text" data-scope-label value="${escAttr(label)}" placeholder="Project name" /></label>
          <label class="sidebar-config-folder-path">Folder or subfolder<input type="text" data-scope-path value="${escAttr(path)}" placeholder="projects/my-project or /absolute/path" autocomplete="off" spellcheck="false" /></label>
        </div>`;
    const remove = root ? '' : '<button class="sidebar-config-folder-remove" type="button" onclick="sidebarFileConfigRemoveFolder(this)" aria-label="Remove project folder" title="Remove project folder">&times;</button>';
    return `<div class="sidebar-config-folder-card${root ? ' root' : ''}" data-scope-root="${root ? 'true' : 'false'}">
      <div class="sidebar-config-folder-card-head">${identity}${remove}</div>
      <div class="sidebar-config-folder-options">
        <label class="sidebar-config-folder-color">Color<input type="color" data-scope-color value="${escAttr(color)}" /></label>
        <label class="sidebar-config-folder-worktree">Worktree folder <span class="sidebar-config-worktree-input-row"><input type="text" data-scope-worktree value="${escAttr(worktreeFolder)}" placeholder="Optional path to worktrees" autocomplete="off" spellcheck="false" oninput="sidebarFileConfigWorktreeInput(this)" /><button type="button" onclick="sidebarFileConfigScanScope(this)">Scan</button></span><small>Optional. Paste the folder containing Git worktrees, or a direct-child worktree inside it.</small></label>
      </div>
      <div class="sidebar-config-worktree-status" data-scope-status role="status">${worktreeFolder ? 'Scan to preview worktrees.' : 'No worktree folder — this project uses only its main folder.'}</div>
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
        problem ||= 'Every project needs a folder path.';
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
    if (recent) recent.checked = _sidebarFileConfig.showRecent;
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
    const projectRoot = _sidebarProjectRoot(baseRoot);
    const activeCard = [...document.querySelectorAll('#sidebarConfigFolderScopes .sidebar-config-folder-card')]
      .find(card => _sidebarFolderCardPath(card, baseRoot) === projectRoot);
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
      status.textContent = 'No matching Git worktrees found for this project.';
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
        : 'No worktree folder — this project uses only its main folder.';
    }
  }

  async function sidebarFileConfigScanScope(button) {
    const card = button && button.closest('.sidebar-config-folder-card');
    const input = card && card.querySelector('[data-scope-worktree]');
    const status = card && card.querySelector('[data-scope-status]');
    const colors = card && card.querySelector('[data-scope-worktree-colors]');
    const baseRoot = _sidebarWorktreeBaseRoot();
    const projectRoot = _sidebarFolderCardPath(card, baseRoot);
    const folder = String(input && input.value || '').trim();
    if (status) {
      status.classList.remove('error');
      status.textContent = folder ? 'Scanning…' : 'No worktree folder — this project uses only its main folder.';
    }
    if (!folder) {
      if (colors) colors.innerHTML = '';
      return [];
    }
    if (!projectRoot) {
      if (status) {
        status.classList.add('error');
        status.textContent = 'Enter this project folder before scanning its worktrees.';
      }
      return null;
    }
    try {
      const requested = _sidebarNormalizeWorktreeFolder(folder, projectRoot);
      const repositoryRoot = _sidebarWorktreeRepositoryRoot(projectRoot);
      const response = await fetch(`/api/sidebar-worktrees?path=${encodeURIComponent(requested)}&repo=${encodeURIComponent(repositoryRoot)}&scope=${encodeURIComponent(projectRoot)}`);
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
    _projDocPath = null;
    _projDocRoot = null;
    projectOpenFile = null;
    diffCache = {uncommitted: null, branch: null};
    _lastProjectMtime = 0;
    _projectSidebarCache.delete(baseRoot);
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';
    await _refreshSidebarAfterFileConfig();
  }

  async function sidebarSelectWorktree(select) {
    const baseRoot = String(select && select.getAttribute('data-base-root') || '');
    if (!baseRoot) return;
    const projectRoot = _sidebarProjectRoot(baseRoot);
    const selected = String(select.value || '');
    _sidebarFileConfig.selectedWorktrees = {...(_sidebarFileConfig.selectedWorktrees || {})};
    if (selected) _sidebarFileConfig.selectedWorktrees[projectRoot] = selected;
    else delete _sidebarFileConfig.selectedWorktrees[projectRoot];
    _storeSidebarFileConfig();
    _projDocPath = null;
    _projDocRoot = null;
    projectOpenFile = null;
    diffCache = {uncommitted: null, branch: null};
    _lastProjectMtime = 0;
    _projectSidebarCache.delete(baseRoot);
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
  }

  async function _refreshSidebarAfterFileConfig() {
    if (document.body.classList.contains('self-active')) return selfPopulateSidebar();
    if (document.body.classList.contains('workspace-active')) return workspacePopulateSidebar();
    if (currentRepo) return loadProjectView();
    if (currentProject && currentProject.is_project) {
      _projectSidebarCache.delete(currentProject.path);
      return _refreshProjectSidebar({preserveScroll: true});
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
    const validFolderPaths = new Set(folderConfig.folderScopes.map(row => row.path));
    const selectedFolders = Object.fromEntries(Object.entries(_sidebarFileConfig.selectedFolders || {})
      .filter(([, path]) => validFolderPaths.has(path)));
    _sidebarFileConfig = {
      showHidden: !!(hidden && hidden.checked),
      showRecent: !!(recent && recent.checked),
      recentMinutes: Math.min(
        SIDEBAR_RECENT_MAX_MINUTES,
        Math.max(1, Number(freshness && freshness.value) || SIDEBAR_FILE_CONFIG_DEFAULTS.recentMinutes),
      ),
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
    showProjectDotFiles = _sidebarFileConfig.showHidden;
    _storeSidebarFileConfig();
    if (currentProject && currentProject.path) {
      const baseRoot = _sidebarWorktreeBaseRoot() || currentProject.path;
      _sidebarRecentDiagnosticsPending = {
        root: null,
        reason: 'file-sidebar-settings-save',
      };
    }
    closeSidebarFileConfig();
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

  function toggleDotFiles(checked) {
    showDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    showProjectDotFiles = checked;
    _storeSidebarFileConfig();
    loadProjectView();
  }

  function toggleProjectDotFiles(checked) {
    showProjectDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    _storeSidebarFileConfig();
    if (currentProject) _projectSidebarCache.delete(currentProject.path);
    showProjectInfo({preserveScroll: true});
  }

  async function loadProjectView() {
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
    sb.innerHTML = '<div class="sidebar-title">Project</div>' +
      _sidebarFileConfigButtonHtml() +
      _sidebarFileScopeButtonsHtml(baseRoot) +
      _sidebarWorktreePickerHtml(baseRoot) +
      symlinkLegendHtml() +
      _sidebarWorktreeScopeStartHtml(baseRoot) +
      '<div class="sidebar-create"><button onclick="openCreateModal()">+ New File</button></div>' +
      '<div class="sidebar-title">Files</div>' +
      '<ul class="tree-node">' + renderTreeNodes(filtered, changedFiles) + '</ul>' +
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
        const cls = projectOpenFile === node.path ? ' active' : '';
        return `<li>
          <div class="tree-file${cls}${symlinkClass(node)}" data-entry-kind="file" data-entry-path="${escAttr(node.path)}" data-entry-root="${escAttr(_activeRepoFileRoot() || '')}"${symlinkTitle(node)} onclick="openProjectFile('${node.path.replace(/'/g, "\\'")}')">
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

  async function openProjectFile(filepath) {
    if (!currentRepo) return;
    const fileRoot = _activeRepoFileRoot();
    projectOpenFile = filepath;
    projectEditMode = false;
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
        const res = await fetch(`/api/project-diff-file?path=${encodeURIComponent(fileRoot)}&file=${encodeURIComponent(filepath)}`);
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || res.statusText); }
        const data = await res.json();
        if (projectOpenFile !== filepath) return;
        renderStoredDiffDocument(filepath, data, content);
      } catch (err) {
        if (projectOpenFile === filepath) content.innerHTML = `<div class="file-viewer-empty">Error: ${esc(err.message || err)}</div>`;
      }
      return;
    }

    try {
      const res = await fetch(`/api/file?repo=${encodeURIComponent(fileRoot)}&path=${encodeURIComponent(filepath)}`);
      if (!res.ok) { const e = await res.json(); throw new Error(e.detail); }
      const data = await res.json();
      renderProjectFileView(filepath, data.content);
    } catch (err) {
      content.innerHTML = `<div class="file-viewer-empty">Error: ${err.message}</div>`;
    }
  }

  function renderProjectFileView(filepath, fileContent) {
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
        <button onclick="startProjectEdit('${fn}')">Edit</button>
      </div>
      <div class="file-viewer-body">
        <table class="view-table">${rows}</table>
      </div>`;

    // Store content for edit mode
    window._projectFileContent = fileContent;
  }

  function startProjectEdit(filepath) {
    projectEditMode = true;
    const content = document.getElementById('content');
    const fn = filepath.replace(/'/g, "\\'");
    content.innerHTML = `
      <div class="file-viewer-header">
        <span class="fv-path">${esc(filepath)}</span>
        <button class="btn-edit-active">Editing</button>
      </div>
      <div class="file-viewer-body">
        <textarea id="projectEditor" spellcheck="false">${esc(window._projectFileContent || '')}</textarea>
      </div>
      <div class="file-viewer-actions">
        <button class="btn-save" onclick="saveProjectFile('${fn}')">Save</button>
        <button class="btn-cancel" onclick="openProjectFile('${fn}')">Cancel</button>
      </div>`;
    // Tab support
    const ta = document.getElementById('projectEditor');
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

  async function saveProjectFile(filepath) {
    const ta = document.getElementById('projectEditor');
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
      window._projectFileContent = ta.value;
      openProjectFile(filepath);
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
  // owning workspace. Project paths, however, are absolute. In a cross-workspace
  // tab this root may differ from the shell's LAB_WORKSPACE_ROOT, so callers can
  // pass the owning catalog path. Never strip until containment is checked.
  function _workspaceRelativeNotebookPath(projectPath, filepath, owningWorkspaceRoot = WORKSPACE_ROOT) {
    const workspaceRoot = _normalizeAbsolutePath(owningWorkspaceRoot);
    const projectRoot = _normalizeAbsolutePath(projectPath);
    const file = String(filepath || '');
    if (!workspaceRoot) throw new Error('Notebook workspace root is unavailable');
    if (!projectRoot || !file || file.startsWith('/')) {
      throw new Error('Invalid notebook path');
    }
    if (file.split('/').some((part) => part === '..')) {
      throw new Error('Notebook path traversal is not allowed');
    }

    const combined = _normalizeAbsolutePath(projectRoot + '/' + file);
    const rootPrefix = workspaceRoot === '/' ? '/' : workspaceRoot + '/';
    if (!combined || !combined.startsWith(rootPrefix)) {
      throw new Error('Notebook is outside its owning workspace');
    }
    const relative = combined.slice(rootPrefix.length);
    if (!relative || relative.startsWith('/')
        || relative.split('/').some((part) => part === '..')) {
      throw new Error('Invalid workspace-relative notebook path');
    }
    return relative;
  }

  function _workspaceRelativeNotebookPathOrNull(projectPath, filepath, owningWorkspaceRoot = WORKSPACE_ROOT) {
    try { return _workspaceRelativeNotebookPath(projectPath, filepath, owningWorkspaceRoot); }
    catch (_) { return null; }
  }

  function _notebookWorkspaceContext(project = currentProject) {
    const workspaceId = typeof _projectWorkspaceId === 'function'
      ? _projectWorkspaceId(project) : null;
    const workspace = typeof _workspaceForProject === 'function'
      ? _workspaceForProject(project) : null;
    return {
      workspaceId: workspaceId || null,
      workspaceRoot: (workspace && workspace.path)
        || (project && project.workspace_path) || WORKSPACE_ROOT,
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

  function renderNotebookCell(cell, status) {
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
        bodyHtml = `<div class="nb-markdown">${marked.parse(cell.source)}</div>`;
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
      outputsHtml = `<div class="nb-outputs">${outs}</div>`;
    }

    return `<div class="nb-cell${statusCls}">
      <div class="nb-cell-header">
        <span class="nb-type">${cell.cell_type}</span>
        <span class="nb-exec">${execCount}</span>
        ${actorBadge}
        ${timingBadge}
        ${statusLabel}
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
    // wrote a placeholder while the Darwin call is in flight. Both get
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
      try { bodyHtml = `<div class="nb-markdown">${marked.parse(cell.source)}</div>`; }
      catch (e) { bodyHtml = `<div class="nb-source">${esc(cell.source)}</div>`; }
      return `<div class="nb-cell nb-cell-interactive" data-cell-index="${index}">
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
    //   nb-cell-running → server-side RUNNING (placeholder while Darwin
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
    const highlighted = _highlightCellSource(source);
    const execCountNum = (cell.execution_count != null) ? cell.execution_count : '';
    const unseen = !pending && outputsHtml && !_isCellSeen(relPath, cell.id || index, cell.execution_count);
    const unseenCls = unseen ? ' nb-cell-unseen' : '';
    const newBadge = unseen
      ? `<span class="nb-cell-new-badge" title="New outputs — click anywhere on the output to acknowledge">NEW</span>`
      : '';
    const serverBusyAttr = serverPending ? ' disabled' : '';
    const serverReadonlyAttr = serverPending ? ' readonly aria-busy="true"' : '';
    return `<div class="nb-cell nb-cell-interactive${pendingCls}${unseenCls}${actorCls}" data-cell-index="${idxAttr}"${cellIdAttr}${pendingAttr}${insertAtAttr}${liveSequenceAttr} data-exec-count="${execCountNum}">
      <div class="nb-cell-header">
        <span class="nb-type">code</span>
        <span class="nb-exec">${execCount}</span>
        ${actorBadge}
        ${timingBadge}
        ${newBadge}
        <div class="nb-cell-actions">
          <span class="nb-cell-busy" style="display:none">running…</span>
          <button class="nb-cell-copy-src" type="button" title="Copy cell source to clipboard">⧉ copy</button>
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

  function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved, workspaceId = null) {
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
      const wasRunning = wrap.classList.contains('nb-cell-running');
      wrap.classList.toggle('nb-cell-running', on);
      // Focus the header/code, never the old output. Centering the whole cell
      // while a tall chart is still mounted lands the viewport in that stale
      // chart and makes a live run look as if it jumped straight to the final
      // output.
      if (on && !wasRunning) {
        const focusTarget = wrap.querySelector('.nb-cell-header') || wrap;
        try { focusTarget.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (_) {}
      }
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
        if (workspaceId) body.workspace = workspaceId;
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
        openProjectDoc(filepath, { preserveScroll: true });
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
            ? { path: relPath, cell_id: cellId, ...(workspaceId ? {workspace: workspaceId} : {}) }
            : { path: relPath, cell_index: cellIndex, ...(workspaceId ? {workspace: workspaceId} : {}) }),
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
        openProjectDoc(filepath, { preserveScroll: true });
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
        // Don't trigger collapse when the user clicked the copy-output button.
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
    const status = (runtime && runtime.status) || 'legacy';
    const activePython = runtime && runtime.active && runtime.active.python;
    return `<dialog class="nb-runtime-dialog">
      <form method="dialog" class="nb-runtime-card">
        <div class="nb-runtime-title"><div><strong>Project Runtime</strong><span>Shared by people and agents</span></div><button value="cancel" class="nb-runtime-close" title="Close">✕</button></div>
        <p class="nb-runtime-help">Choose the exact Python environment for this project. Libraries that invoke CLI commands inherit the configured CLI paths inside the Jupyter kernel.</p>
        <div class="nb-runtime-grid">
          <label>Provider<select name="mode"><option value="local"${spec.mode === 'local' ? ' selected' : ''}>Local Jupyter</option><option value="darwin"${spec.mode === 'darwin' ? ' selected' : ''}>Darwin (legacy)</option></select></label>
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

  function bindNbRuntimePanel(container, relPath, filepath, workspaceId = null) {
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
        mode: dialog.querySelector('[name="mode"]').value,
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
        body: JSON.stringify({ path: relPath, spec, ...(workspaceId ? {workspace: workspaceId} : {}) }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || data));
      return data;
    }
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true; buildBtn.disabled = true;
      try {
        const data = await save();
        showLog(`Saved project runtime. Status: ${data.status}`, false);
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
          body: JSON.stringify({ path: relPath, ...(workspaceId ? {workspace: workspaceId} : {}) }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const detail = data.detail || {};
          throw new Error([detail.message || detail, detail.log || ''].filter(Boolean).join('\n\n'));
        }
        showLog((data.built && data.built.log) || 'Runtime is ready. Import and CLI checks passed inside Jupyter.', false);
        setTimeout(() => { dialog.close(); openProjectDoc(filepath, { preserveScroll: true }); }, 700);
      } catch (err) {
        showLog(err.message || String(err), true);
      } finally {
        saveBtn.disabled = false; buildBtn.disabled = false;
        buildBtn.textContent = 'Build & validate in Jupyter';
      }
    });
  }

  function bindNbInterruptKernel(container, relPath, workspaceId = null) {
    const btn = container.querySelector('.nb-interrupt-kernel');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const original = btn.textContent;
      btn.textContent = '■ Interrupting…';
      try {
        const res = await fetch('/api/nb/session/interrupt', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: relPath, ...(workspaceId ? {workspace: workspaceId} : {}) }),
        });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          throw new Error(data.detail || `interrupt failed (${res.status})`);
        }
        btn.textContent = '✓ Interrupted';
      } catch (err) {
        alert('Kernel interrupt failed: ' + (err.message || err));
        btn.textContent = original;
      } finally {
        setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1200);
      }
    });
  }

  async function bindNbRestartKernel(container, relPath, filepath, workspaceId = null) {
    const btn = container.querySelector('.nb-restart-kernel');
    if (!btn) return;
    btn.addEventListener('click', async () => {
      if (!confirm('Restart the kernel for this notebook? All variables will be wiped. Cells stay; you re-run them on the new kernel.')) return;
      btn.disabled = true;
      const originalText = btn.textContent;
      btn.textContent = '↻ Restarting…';
      try {
        const res = await fetch('/api/nb/session/restart', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: relPath, ...(workspaceId ? {workspace: workspaceId} : {}) }),
        });
        if (!res.ok) {
          const e = await res.json().catch(() => ({ detail: res.statusText }));
          throw new Error(e.detail || ('restart failed (' + res.status + ')'));
        }
        btn.textContent = '✓ Kernel restarted';
        setTimeout(() => { btn.textContent = originalText; btn.disabled = false; }, 1500);
      } catch (err) {
        alert('Kernel restart failed: ' + (err.message || err));
        btn.textContent = originalText;
        btn.disabled = false;
      }
    });
  }

  function bindNbAddCellButton(container, relPath, filepath, workspaceId = null) {
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
      bindNbCellInteractive(node, relPath, filepath, null, workspaceId);
      const ta = node.querySelector('.nb-cell-edit-area');
      if (ta) ta.focus();
    });
  }

  // Hover-revealed "+ insert cell" bars between every pair of cells. Click
  // inserts a pending cell at that position (data-insert-at), which on Run
  // POSTs `insert_at` so the new cell lands between existing cells instead
  // of being appended at the end.
  function bindNbCellInserters(container, relPath, filepath, workspaceId = null) {
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
        bindNbCellInteractive(node, relPath, filepath, null, workspaceId);
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
        sourceHtml = `<div class="nb-history-markdown${changedClass}">${marked.parse(cell.source || '')}</div>`;
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

  // Browsers never execute <script> tags injected via innerHTML; DAVI / Plotly
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
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading notebook...</div>';
    try {
      const res = await fetch(`/api/notebook?repo=${encodeURIComponent(_activeRepoFileRoot())}&path=${encodeURIComponent(filepath)}`);
      const cells = await res.json();
      await Promise.all([
        ensureMarked().catch(() => {}),
        ensureHighlight().catch(() => {}),
      ]);
      content.innerHTML = `<div class="file-viewer-header">
        <span class="fv-path">${esc(filepath)}</span>
      </div>
      <div class="nb-container">${cells.map(c => renderNotebookCell(c, null)).join('')}</div>`;
      activateNotebookScripts(content);
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

  // ─── Workspace projections for the project sidebar (migration step 5) ──
  // When workspace.json declares agents.projections / project.mounts, the
  // Meta section renders THOSE rows — each labeled with its true workspace
  // origin — instead of the legacy hardcoded "(shared)" entries. Files open
  // their workspace source inline; mounted directories jump to the
  // Workspace tab where the real source tree lives. 30s TTL so an edit to
  // workspace.json shows up without a reload.
  let _wsProjCache = null;  // {projections, mounts, supported, ts}
  async function loadWorkspaceProjections() {
    const now = Date.now();
    const workspaceId = typeof _termWorkspaceId === 'function' ? _termWorkspaceId() : null;
    if (_wsProjCache && _wsProjCache.workspace === workspaceId && (now - _wsProjCache.ts) < 30000) return _wsProjCache;
    let out = { projections: [], mounts: [], supported: null, workspace: workspaceId, ts: now };
    try {
      const suffix = workspaceId ? '?workspace=' + encodeURIComponent(workspaceId) : '';
      const r = await fetch('/api/workspace/config' + suffix);
      if (r.ok) {
        const cfg = await r.json();
        const doc = (cfg.valid && cfg.config) || {};
        const agents = doc.agents || {};
        const project = doc.project || {};
        out = {
          projections: Array.isArray(agents.projections) ? agents.projections : [],
          mounts: Array.isArray(project.mounts) ? project.mounts : [],
          supported: Array.isArray(agents.supported) ? agents.supported : null,
          workspace: workspaceId,
          ts: now,
        };
      }
    } catch {}
    _wsProjCache = out;
    return out;
  }

  function _wsProjectionMetaHtml(p) {
    if (!p) return '';
    const sup = p.supported;
    const enabled = (e) => e && typeof e === 'object'
      && (!e.when || !sup || sup.includes(e.when));
    const projections = p.projections.filter(enabled)
      .filter(e => typeof e.source === 'string' && e.source && typeof e.target === 'string' && e.target);
    const mounts = p.mounts.filter(enabled)
      .filter(e => typeof e.source === 'string' && e.source && typeof e.target === 'string' && e.target);
    if (!projections.length && !mounts.length) return '';
    let html = '';
    // The canonical source files themselves, one row each (deduped) — the
    // file agents actually read is one click away, same as before.
    const sources = [...new Set(projections.map(e => e.source))];
    for (const src of sources) {
      const base = src.split('/').pop();
      const safe = src.replace(/'/g, "\\'");
      html += `<a class="sidebar-file sidebar-file-meta" onclick="openSharedFile('${safe}')" title="${escAttr('workspace/' + src + ' — canonical source; projected into every project')}" style="opacity:.7"><span class="sidebar-fname">${fileIconHtml(base)}${selfEsc(base)}<span class="ws-origin">workspace</span></span></a>`;
    }
    for (const e of projections) {
      const base = e.target.split('/').pop();
      const safe = e.source.replace(/'/g, "\\'");
      const title = `workspace/${e.source} → ${e.target}` +
        (e.mode ? ` (${e.mode}${e.when ? ', ' + e.when + ' only' : ''})` : '');
      html += `<a class="sidebar-file sidebar-file-meta" onclick="openSharedFile('${safe}')" title="${escAttr(title)}" style="opacity:.7"><span class="sidebar-fname">${fileIconHtml(base)}${selfEsc(base)}<span class="ws-origin">&#8592; ${selfEsc(e.source)}</span></span></a>`;
    }
    for (const e of mounts) {
      const title = `workspace/${e.source} → ${e.target}` +
        (e.mode ? ` (${e.mode}${e.when ? ', ' + e.when + ' only' : ''})` : '') +
        ' — opens the source tree in the Workspace tab';
      html += `<div class="sidebar-folder sidebar-file-meta" onclick="goToWorkspace()" title="${escAttr(title)}" style="opacity:.7"><span class="folder-arrow">&#9654;</span>${selfEsc(e.target)}/<span class="ws-origin">&#8592; ${selfEsc(e.source)}</span></div>`;
    }
    return html;
  }

  // ─── Focus mode ─────────────────────────────────────────────────────────
  // Hides the topbar (Home / workspace picker / project tabs / gear) and the
  // project attrs bar so only the Overview strip and the content remain.
  // Entering from the button also requests browser fullscreen and keeps the
  // display awake. Keep Alive exposes that wake lock independently beside the
  // Focus control. Esc exits Focus; both preferences persist across reloads.
  const FOCUS_MODE_KEY = 'labFocusMode';
  const KEEP_ALIVE_KEY = 'labKeepAlive';
  const FOCUS_ZOOM_MIN = 0.5;
  const FOCUS_ZOOM_MAX = 3;
  const FOCUS_ZOOM_SENSITIVITY = 0.01;
  let _screenWakeLock = null;
  let _screenWakeLockRequest = null;
  let _focusOwnsFullscreen = false;
  let _focusZoom = 1;

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
    try { if (currentProject) renderRepoTabs(); } catch {}
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
    try { if (currentProject) renderRepoTabs(); } catch {}
  }
  function toggleKeepAlive() {
    applyKeepAlive(!document.body.classList.contains('keep-alive'));
  }
  window.toggleKeepAlive = toggleKeepAlive;

  try {
    if (localStorage.getItem(FOCUS_MODE_KEY) === '1') {
      document.body.classList.add('focus-mode');
    }
    if (localStorage.getItem(KEEP_ALIVE_KEY) === '1') {
      document.body.classList.add('keep-alive');
    }
    if (_shouldKeepDisplayAwake()) void _acquireScreenWakeLock();
  } catch {}
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible'
        && _shouldKeepDisplayAwake()) {
      void _acquireScreenWakeLock();
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
    if (!currentProject) {
      container.style.display = 'none';
      document.body.classList.remove('has-repo-tabs');
      return;
    }

    container.style.display = 'flex';
    document.body.classList.add('has-repo-tabs');

    let html = '';
    const isSelf = document.body.classList.contains('self-active');
    const isWorkspace = document.body.classList.contains('workspace-active');
    const proxyOpen = typeof _projDocPath === 'string' && _projDocPath.startsWith('__proxy__/');
    const notebookOpen = _contextSubView === 'notebooks'
      || (typeof _projDocPath === 'string' && _projDocPath.toLowerCase().endsWith('.ipynb'));
    const overviewActive = _contextSubView === 'overview' && !_projDocPath && !currentRepo && !proxyOpen;
    const codeSearchActive = _contextSubView === 'code-search';

    if (isSelf) {
      html += `<button class="repo-tab${overviewActive ? ' active' : ''}" onclick="selfShowWorkbench()" style="font-weight:600">&#x1F4CB; Overview</button>`;
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${codeSearchActive ? ' active' : ''}" onclick="showScopedCodeSearch()">&#x1F50D; Code Search</button>`;
      for (const ws of (workspaceCatalog || [])) {
        html += `<button class="repo-tab workspace-context-tab" style="--workspace-color:${escAttr(ws.color || '#8b949e')}" onclick="goToWorkspace('${String(ws.id).replace(/'/g, "\\'")}')"><span class="workspace-mark"></span>${esc(ws.name || ws.id)}</button>`;
      }
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${_contextSubView === 'admin' ? ' active' : ''}" onclick="selfShowAdmin()">&#x2699; Admin</button>`;
    } else if (isWorkspace) {
      html += `<button class="repo-tab${overviewActive ? ' active' : ''}" onclick="workspaceShowOverview()" style="font-weight:600">&#x1F4CB; Overview</button>`;
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${codeSearchActive ? ' active' : ''}" onclick="showScopedCodeSearch()">&#x1F50D; Code Search</button>`;
    } else if (currentProject.is_project) {
      html += `<button class="repo-tab${overviewActive ? ' active' : ''}" onclick="showProjectDashboard()" style="font-weight:600">&#x1F4CB; Overview</button>`;
      if (LAB_IS_ADMIN) html += `<button class="repo-tab${codeSearchActive ? ' active' : ''}" onclick="showScopedCodeSearch()">&#x1F50D; Code Search</button>`;
      html += `<button class="repo-tab${notebookOpen ? ' active' : ''}" onclick="openProjectNotebooks()" title="Lab Jupyter notebooks — no server configuration required">&#x25C9; Jupyter</button>`;
    }

    // One tab per declared server (project.json proxies) — clicking it opens
    // the same inline iframe view as the sidebar Servers entry. The list
    // comes from the sidebar payload cache; on a cold load it's empty until
    // _refreshProjectSidebar fetches project-info and re-calls us.
    if (!isSelf && !isWorkspace && currentProject.is_project) {
      const cached = _projectSidebarCache.get(currentProject.path);
      const proxies = (cached && Array.isArray(cached.proxies)) ? cached.proxies : [];
      proxies.forEach(p => {
        if (!p || !p.name) return;
        const name = String(p.name);
        const safeName = name.replace(/'/g, "\\'");
        const label = p.label || name;
        const active = _projDocPath === '__proxy__/' + name ? ' active' : '';
        html += `<button class="repo-tab${active}" onclick="openProjectProxy('${safeName}')">&#x1F310; ${esc(label)} <span style="color:#484f58;font-size:10px">:${esc(String(p.port || ''))}</span></button>`;
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
    html += `<button class="repo-tab focus-toggle" onclick="toggleFocusMode()" title="${focusOn ? (keepAliveOn ? 'Exit fullscreen focus (Keep Alive will remain on)' : 'Exit fullscreen focus and allow display sleep again (Esc)') : 'Enter fullscreen focus and keep the display awake'}">${focusOn ? '✖ Exit focus' : '⛶ Focus mode'}</button>`;

    container.innerHTML = html;
  }

  function showScopedCodeSearch() {
    if (!currentProject || !currentProject.path) return;
    _contextSubView = 'code-search';
    if (document.body.classList.contains('self-active')) {
      const url = new URL(window.location);
      url.searchParams.set('view', 'productivity');
      url.searchParams.set('subview', 'code-search');
      history.replaceState(history.state, '', url.pathname + url.search + url.hash);
    }
    currentRepo = null;
    _projDocPath = null;
    renderRepoTabs();
    const kind = document.body.classList.contains('self-active')
      ? 'framework'
      : document.body.classList.contains('workspace-active') ? 'workspace' : 'project';
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="context-placeholder">
        <div class="eyebrow">${esc(kind)} search</div>
        <h1>Code Search is in development</h1>
        <p>This tab will use AI to find and explain code only inside the path selected by the current tab.</p>
        <span class="context-path">${esc(currentProject.path)}</span>
      </div>`;
  }
  window.showScopedCodeSearch = showScopedCodeSearch;

  let _projDocPath = null;
  let _projDocRoot = null; // alternate file root selected by the worktree picker
  let _projDocContent = null;
  let _projDocEditing = false;
  let _projDocEditContainer = null; // container that holds the active edit textarea
  let _projComments = [];
  let _projDocArtifact = null;  // project.json.artifacts[] entry whose `file` matches the open doc
  // Doc-content cache for warm tab switches: key `${project.path}|${filepath}`
  // → {content, comments, artifact}. Lets openProjectDoc paint a remembered
  // file synchronously while the three /api/project-* fetches reconcile in
  // the background. Only used for the text/markdown/csv/json path inside
  // _renderDocInto — notebooks/HTML/images have their own renderers and
  // are excluded. Survives tab switches; reset on full page reload.
  const _projDocCache = new Map();
  function _projDocCacheKey(projectPath, filepath) {
    return (projectPath || '') + '|' + (filepath || '');
  }
  // Sidebar payload cache keyed by `currentProject.path`. Stores the
  // last-known `{files, pinned, references}` triple so warm switches
  // can re-render the file tree synchronously from memory instead of
  // waiting on /api/project-files + /api/project-info every time.
  // `_refreshProjectSidebar` reconciles against the server in the
  // background after a warm paint and writes through to this map.
  const _projectSidebarCache = new Map();
  // Same idea for the project server bar. Keyed by absolute project path.
  const _projectAttrsCache = new Map();

  // Per-project memory of the last file the user had open. Survives
  // tab switches and reloads; map keyed by absolute project path.
  const LAST_DOC_KEY = 'labLastDoc-v1';
  function _lastDocMap() {
    try { return JSON.parse(localStorage.getItem(LAST_DOC_KEY) || '{}') || {}; }
    catch { return {}; }
  }
  function setLastProjectDoc(projectPath, docPath) {
    if (!projectPath) return;
    const m = _lastDocMap();
    if (docPath) m[projectPath] = docPath; else delete m[projectPath];
    try { localStorage.setItem(LAST_DOC_KEY, JSON.stringify(m)); } catch {}
  }
  function getLastProjectDoc(projectPath) {
    return _lastDocMap()[projectPath] || null;
  }

  // Notebook selection is remembered separately from the last ordinary
  // project document. A user can move from a notebook to README.md and still
  // return to the same live kernel with one click on the built-in Jupyter tab.
  const LAST_NOTEBOOK_KEY = 'labLastNotebook-v1';
  function _lastNotebookMap() {
    try { return JSON.parse(localStorage.getItem(LAST_NOTEBOOK_KEY) || '{}') || {}; }
    catch { return {}; }
  }
  function setLastProjectNotebook(projectPath, notebookPath) {
    if (!projectPath || !notebookPath) return;
    const m = _lastNotebookMap();
    m[projectPath] = notebookPath;
    try { localStorage.setItem(LAST_NOTEBOOK_KEY, JSON.stringify(m)); } catch {}
  }
  function getLastProjectNotebook(projectPath) {
    return _lastNotebookMap()[projectPath] || null;
  }

  function _projectNotebookEntries(files) {
    return (Array.isArray(files) ? files : [])
      .filter(f => f && f.type !== 'dir' && typeof f.path === 'string'
        && f.path.toLowerCase().endsWith('.ipynb'))
      .sort((a, b) => Number(b.mtime || 0) - Number(a.mtime || 0)
        || a.path.localeCompare(b.path));
  }

  async function _loadProjectNotebookEntries(projectPath) {
    const cached = _projectSidebarCache.get(projectPath);
    if (cached && Array.isArray(cached.files)) return _projectNotebookEntries(cached.files);
    const response = await fetch(`/api/project-files?path=${encodeURIComponent(projectPath)}`);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Could not list notebooks (${response.status})`);
    }
    return _projectNotebookEntries(await response.json());
  }

  function _renderProjectNotebookLauncher(notebooks) {
    const content = document.getElementById('content');
    if (!content) return;
    const projectName = currentProject ? _projectDisplayName(currentProject) : 'this project';
    const projectPath = currentProject && currentProject.path ? currentProject.path : '';
    const cards = notebooks.map(entry => {
      const path = String(entry.path || '');
      const safePath = path.replace(/'/g, "\\'");
      const updated = entry.mtime
        ? `updated ${new Date(Number(entry.mtime) * 1000).toLocaleString()}`
        : 'not run yet';
      return `<button type="button" onclick="openProjectDoc('${safePath}')" style="display:flex;align-items:center;gap:14px;width:100%;text-align:left;background:var(--bg-secondary);color:var(--text-primary);border:1px solid var(--border);border-radius:8px;padding:14px 16px;cursor:pointer">
        <span style="font-size:22px;color:var(--accent)">&#x25C9;</span>
        <span style="min-width:0;flex:1"><strong style="display:block;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(path.split('/').pop() || path)}</strong><span style="display:block;color:var(--text-dim);font:11px ui-monospace,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:3px">${esc(path)}</span></span>
        <span style="color:var(--text-dim);font-size:11px;white-space:nowrap">${esc(updated)}</span>
      </button>`;
    }).join('');
    content.innerHTML = `<div style="padding:28px;max-width:900px">
      <div style="display:flex;align-items:center;gap:14px;margin-bottom:22px">
        <div style="flex:1"><h1 style="color:var(--text-primary);font-size:24px;margin:0 0 5px">Jupyter <span style="color:var(--text-dim);font-weight:400">· ${esc(projectName)}</span></h1><p style="color:var(--text-secondary);font-size:13px;margin:0">Notebooks are scoped to this project. Every .ipynb keeps its own kernel; people and agents share it by file path.</p>${projectPath ? `<code style="display:block;color:var(--text-dim);font-size:11px;margin-top:6px;overflow-wrap:anywhere">${esc(projectPath)}</code>` : ''}</div>
        <button type="button" onclick="openNewNotebookDialog()" style="background:var(--accent);color:#fff;border:0;border-radius:6px;padding:8px 13px;cursor:pointer">+ Notebook</button>
      </div>
      ${notebooks.length
        ? `<div style="display:flex;flex-direction:column;gap:9px">${cards}</div>`
        : `<div style="border:1px dashed var(--border);border-radius:8px;padding:36px;text-align:center;color:var(--text-dim)">No .ipynb files in <strong style="color:var(--text-secondary)">${esc(projectName)}</strong> yet.<div style="font-size:12px;margin-top:7px">A notebook created in another project appears in that project's Jupyter tab.</div><button type="button" onclick="openNewNotebookDialog()" style="margin-top:14px;background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:6px;padding:7px 12px;cursor:pointer">Create the first notebook here</button></div>`}
    </div>`;
  }

  async function openProjectNotebooks({showLauncher = false} = {}) {
    if (!currentProject || !currentProject.is_project) return;
    const projectPath = currentProject.path;
    if (!showLauncher && typeof _projDocPath === 'string'
        && _projDocPath.toLowerCase().endsWith('.ipynb')) {
      return openProjectDoc(_projDocPath);
    }
    _contextSubView = 'notebooks';
    currentRepo = null;
    currentRepoInProject = null;
    _repoFileRoot = null;
    _projDocPath = '__notebooks__';
    _projDocRoot = projectPath;
    renderRepoTabs();
    _sidebarApplyForView();
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="loading">Loading notebooks...</div>';
    try {
      const notebooks = await _loadProjectNotebookEntries(projectPath);
      if (!currentProject || currentProject.path !== projectPath || _projDocPath !== '__notebooks__') return;
      const remembered = getLastProjectNotebook(projectPath);
      const preferred = !showLauncher && remembered
        ? notebooks.find(entry => entry.path === remembered)
        : null;
      if (preferred) return openProjectDoc(preferred.path);
      if (!showLauncher && notebooks.length === 1) return openProjectDoc(notebooks[0].path);
      _renderProjectNotebookLauncher(notebooks);
    } catch (err) {
      if (content && currentProject && currentProject.path === projectPath
          && _projDocPath === '__notebooks__') {
        content.innerHTML = `<div class="no-repo"><p>Error: ${esc(err.message || err)}</p></div>`;
      }
    }
  }
  window.openProjectNotebooks = openProjectNotebooks;

  let _docModalEscHandler = null;

  async function openProjectDocModal(filepath, { editing = false, root = null } = {}) {
    if (!currentProject) return;
    _projDocRoot = root || currentProject.path;
    const modal = document.getElementById('docViewModal');
    const body = document.getElementById('docModalBody');
    const titleEl = document.getElementById('docModalTitle');
    titleEl.textContent = filepath;
    body.innerHTML = '<div class="loading" style="padding:24px">Loading…</div>';
    modal.classList.add('active');
    if (_docModalEscHandler) document.removeEventListener('keydown', _docModalEscHandler);
    _docModalEscHandler = (e) => { if (e.key === 'Escape') closeDocModal(); };
    document.addEventListener('keydown', _docModalEscHandler);
    _projDocEditing = editing;
    _projDocEditContainer = editing ? body : null;
    await _renderDocInto(filepath, body);
    if (!editing) _projDocEditing = false;
  }

  function closeDocModal() {
    if (_projDocEditing) {
      _projDocEditing = false;
      _projDocEditContainer = null;
    }
    const modal = document.getElementById('docViewModal');
    if (modal) modal.classList.remove('active');
    if (_docModalEscHandler) {
      document.removeEventListener('keydown', _docModalEscHandler);
      _docModalEscHandler = null;
    }
  }

  // Shared render helper: handles all file types and writes into `container`.
  // Sets the module-level _projDocContent / _projComments / _projDocArtifact globals
  // that renderProjectDoc reads. Does NOT touch navigation state (_projDocPath,
  // sidebar active highlights, setLastProjectDoc) — callers handle that.
  // Renders an HTML file in the project doc pane with a Rendered/Code
  // toggle. Mirrors cerebroRenderHtml; the pref is shared via
  // localStorage so opening the same file in Cerebro keeps the same view.
  async function _projectRenderHtml(container, filepath, absKey, mode) {
    // Race guard against the user navigating away mid-fetch — same
    // shape as the one in _renderDocInto.
    const _navProjectPath = (currentProject && currentProject.path) || null;
    const docRoot = _projDocRoot || _navProjectPath;
    const _stillActiveNav = () => (
      _projDocPath === filepath
      && currentProject
      && currentProject.path === _navProjectPath
      && (_projDocRoot || currentProject.path) === docRoot
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
      const src = `/api/project-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
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
        const r = await fetch(`/api/project-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`);
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
        _projectRenderHtml(container, filepath, absKey, next);
      });
    });
  }

  async function _renderDocInto(filepath, container, { preserveScroll = false } = {}) {
    // Capture the project that owned this render call so an async paint
    // landing AFTER the user has switched away to a different project
    // (or a different file in the same project) bails instead of
    // stomping the new view's content. _projDocPath is set
    // synchronously by openProjectDoc / selectRepo before this function
    // is called, so a mismatch here means a newer navigation has
    // already taken over `container` and we must not paint.
    const _navProjectPath = (currentProject && currentProject.path) || null;
    const docRoot = _projDocRoot || _navProjectPath;
    const _stillActiveNav = () => (
      _projDocPath === filepath
      && currentProject
      && currentProject.path === _navProjectPath
      && (_projDocRoot || currentProject.path) === docRoot
    );

    // Image files
    const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
    if (imageExts.some(ext => filepath.toLowerCase().endsWith(ext))) {
      if (!_stillActiveNav()) return;
      const src = `/api/project-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      container.innerHTML = `<div style="padding:24px;max-width:900px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:16px"><span style="font-size:12px;color:#484f58;font-family:monospace;flex:1">${esc(filepath)}</span></div><img src="${src}" style="max-width:100%;border-radius:4px"></div>`;
      return;
    }

    // PDF files: hand the raw bytes to the browser's built-in PDF viewer via
    // an iframe. /api/project-asset serves them as application/pdf with no
    // attachment disposition, so they display inline (zoom/page/print come
    // from the browser's own viewer chrome). Same anti-flicker guard as the
    // HTML viewer: the WS index-updated event re-runs this render on every
    // save under content/, and re-creating the iframe flashes + resets the
    // user's scroll/zoom — so leave a live iframe already pointed here alone.
    if (filepath.toLowerCase().endsWith('.pdf')) {
      if (!_stillActiveNav()) return;
      const src = `/api/project-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      const existing = container.querySelector('iframe.pdf-iframe');
      if (existing && existing.getAttribute('src') === src) return;
      container.innerHTML = `<div style="padding:24px"><div style="display:flex;align-items:center;gap:8px;margin-bottom:12px"><span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span><a href="${src}" target="_blank" rel="noopener" style="font-size:11px;color:var(--text-secondary)">open ↗</a></div><iframe class="pdf-iframe" src="${esc(src)}" title="${esc(filepath)}"></iframe></div>`;
      return;
    }

    // Video files: native <video> player streaming from /api/project-asset.
    // FileResponse supports HTTP Range requests, so seeking works without
    // downloading the whole file. Same anti-flicker guard as the PDF
    // iframe: watcher-triggered re-renders (project mtime poll, WS events)
    // must leave an already-mounted player alone — recreating the element
    // would restart playback mid-watch.
    const videoExts = ['.mp4', '.webm', '.mov', '.m4v'];
    if (videoExts.some(ext => filepath.toLowerCase().endsWith(ext))) {
      if (!_stillActiveNav()) return;
      const src = `/api/project-asset?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`;
      const existing = container.querySelector('video.project-video');
      if (existing && existing.getAttribute('src') === src) return;
      container.innerHTML = `<div style="padding:24px;max-width:1100px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px">
          <span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span>
          <a href="${esc(src)}" target="_blank" rel="noopener" style="font-size:11px;color:var(--text-secondary)">open ↗</a>
        </div>
        <video class="project-video" src="${esc(src)}" controls playsinline preload="metadata" style="width:100%;max-height:calc(100vh - 220px);background:#000;border-radius:6px;outline:none"></video>
      </div>`;
      return;
    }

    // HTML files: rendered iframe by default, with a "Code" toggle to
    // view source instead. Choice is sticky per file via localStorage.
    if (/\.(html|htm)$/i.test(filepath)) {
      const absKey = docRoot + '/' + filepath;
      const mode = getHtmlViewPref(absKey);
      _projectRenderHtml(container, filepath, absKey, mode);
      return;
    }

    // Saved unified patches use the same file headers, line gutters,
    // word-level highlights, and Unified/Split layouts as live Git changes.
    if (/\.(diff|patch)$/i.test(filepath)) {
      try {
        await ensureHighlight().catch(() => {});
        const response = await fetch(`/api/project-diff-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`);
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
        // Execution is workspace-scoped, but notebooks in the framework Home
        // or another repository root are still useful documents. Render those
        // through the generic repository notebook endpoint without Run/Delete
        // controls; only a notebook inside the active workspace gets a kernel.
        const notebookWorkspace = _notebookWorkspaceContext(currentProject);
        const notebookWorkspaceQuery = notebookWorkspace.workspaceId
          ? `&workspace=${encodeURIComponent(notebookWorkspace.workspaceId)}` : '';
        const relPath = docRoot === currentProject.path
          ? _workspaceRelativeNotebookPathOrNull(
              currentProject.path, filepath, notebookWorkspace.workspaceRoot,
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
          const readOnlyHeader = `<div class="nb-notebook-header"><span class="nb-notebook-path">${esc(filepath)}</span><span class="nb-kernel-badge">read-only notebook</span><span class="nb-notebook-updated">Move or copy into a workspace project to execute</span></div>`;
          container.innerHTML = `<div style="padding:24px">${readOnlyHeader}<div class="nb-container">${readOnlyCells.map(c => renderNotebookCell(c, null)).join('')}</div></div>`;
          activateNotebookScripts(container);
          return;
        }

        // A brand-new notebook 404s on /api/nb; treat that as "empty, ready to
        // receive its first cell" rather than an error.
        const [nbRes, sessRes, runtimeRes] = await Promise.all([
          fetch(`/api/nb?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`),
          fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`),
          fetch(`/api/nb/runtime?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`),
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
        const provider = sessionInfo.provider || 'darwin';
        const runtime = runtimeRes.ok ? await runtimeRes.json() : { status: 'unavailable', spec: null };
        // Fetch replay state after the durable notebook response. The live API
        // cross-checks each run against its on-disk marker, which makes this
        // pair a consistent view even during the final-cell replacement.
        const liveRes = await fetch(
          `/api/nb/live?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`,
        );
        const liveInfo = liveRes.ok ? await liveRes.json() : { executions: [] };
        if ((liveInfo.executions || []).length === 0
            && (nb.cells || []).some(cell => cell?.metadata?.lab_pending === true)) {
          // The file may have completed between the first /nb response and the
          // /live cross-check. Refetch once so that race cannot leave a newly
          // opened view showing a stale spinner with no live run behind it.
          const latestNbRes = await fetch(
            `/api/nb?path=${encodeURIComponent(relPath)}${notebookWorkspaceQuery}`,
            { cache: 'no-store' },
          );
          if (latestNbRes.ok) nb = await latestNbRes.json();
        }
        const notebookLiveKey = _nbLiveKey(notebookWorkspace.workspaceId, relPath);
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
        const kernelLabel = provider === 'local' ? 'Project Jupyter kernel' : 'Remote Darwin kernel';
        const sessionBadge = session
          ? `<span title="Dedicated kernel session pinned to this .ipynb file path; another notebook gets another kernel" class="nb-kernel-badge">${kernelLabel} · ${esc(session)}</span>`
          : '';
        const runtimeBadge = `<button class="nb-runtime-open nb-runtime-status-${esc(runtime.status || 'legacy')}" type="button" title="Configure this project's Python, libraries, CLI paths and environment">⚙ Runtime: ${esc(runtime.status || 'legacy')}</button>`;
        const restartBtnHtml = session
          ? `<button class="nb-restart-kernel" type="button" title="Restart kernel (wipes variables, like Jupyter's Restart Kernel)">↻ Restart kernel</button>`
          : '';
        const interruptBtnHtml = provider === 'local'
          ? `<button class="nb-interrupt-kernel" type="button" title="Interrupt the currently running cell">■ Interrupt</button>`
          : '';
        const notebookListBtnHtml = `<button class="nb-notebook-list" type="button" onclick="openProjectNotebooks({showLauncher:true})" title="Show every notebook in this project">☷ All notebooks</button>`;
        const header = `<div class="nb-notebook-header"><span class="nb-notebook-path">${esc(filepath)}</span>${notebookListBtnHtml}${runtimeBadge}${sessionBadge}${interruptBtnHtml}${restartBtnHtml}<span class="nb-notebook-updated">${updatedLabel}</span></div>`;
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
        // navigated to a different file (or project) while we were
        // fetching, do NOT stomp the new view's content with this
        // notebook's HTML.
        if (!_stillActiveNav()) return;
        container.innerHTML = `<div style="padding:24px">${header}${renderNbRuntimePanel(runtime, relPath)}<div class="nb-container">${cellsHostHtml}</div>${addBtnHtml}</div>`;
        activateNotebookScripts(container);
        _ensureNbElapsedTicker();
        // Bind every interactive cell + inserters + the trailing add-cell
        // button + restart.
        container.querySelectorAll('.nb-cell-interactive').forEach((wrap) => {
          bindNbCellInteractive(
            wrap, relPath, filepath, null, notebookWorkspace.workspaceId,
          );
        });
        bindNbCellInserters(container, relPath, filepath, notebookWorkspace.workspaceId);
        bindNbAddCellButton(container, relPath, filepath, notebookWorkspace.workspaceId);
        bindNbRestartKernel(container, relPath, filepath, notebookWorkspace.workspaceId);
        bindNbInterruptKernel(container, relPath, notebookWorkspace.workspaceId);
        bindNbRuntimePanel(container, relPath, filepath, notebookWorkspace.workspaceId);
        // Auto-scroll the currently-running cell into view. The
        // server-side placeholder lands here as .nb-cell-pending with
        // its [*] gutter; bring it to the user's focus so they can see
        // what's executing even when the run was kicked off from a
        // terminal / curl rather than the in-UI Run button.
        const runningCell = container.querySelector('.nb-cell-interactive.nb-cell-running');
        if (runningCell) {
          const focusTarget = runningCell.querySelector('.nb-cell-header') || runningCell;
          focusTarget.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      } catch (err) {
        if (!_stillActiveNav()) return;
        container.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
      }
      return;
    }

    // All other files: fetch content + comments + artifact info, then renderProjectDoc
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
      const cacheKey = _projDocCacheKey(docRoot, filepath);
      const cached = _projDocCache.get(cacheKey);
      if (cached) {
        _projDocContent = cached.content;
        _projComments = cached.comments;
        _projDocArtifact = cached.artifact;
        if (!_stillActiveNav()) return;
        renderProjectDoc(filepath, container);
      }
      const [fileRes, commentsRes, infoRes] = await Promise.all([
        fetch(`/api/project-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`),
        fetch(`/api/project-comments?path=${encodeURIComponent(docRoot)}`),
        fetch(`/api/project-info?path=${encodeURIComponent(docRoot)}`),
      ]);
      if (!fileRes.ok) { const e = await fileRes.json(); throw new Error(e.detail); }
      const data = await fileRes.json();
      const newComments = (await commentsRes.json()).filter(c => c.file === filepath);
      const info = infoRes.ok ? await infoRes.json() : {};
      const artifacts = Array.isArray(info.artifacts) ? info.artifacts : [];
      const newArtifact = artifacts.find(a => a && a.file === filepath) || null;
      _projDocCache.set(cacheKey, {content: data.content, comments: newComments, artifact: newArtifact});
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
      _projDocContent = data.content;
      _projComments = newComments;
      _projDocArtifact = newArtifact;
      renderProjectDoc(filepath, container);
    } catch (err) {
      if (!_stillActiveNav()) return;
      container.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
    }
  }

  async function openProjectDoc(filepath, {preserveScroll = false, root = null} = {}) {
    if (!currentProject) return;
    // Pseudo-paths starting with `__proxy__/` are not real files — they
    // refer to a declared local-dev-server proxy. Route to the iframe
    // renderer; everything else (active highlight, last-opened memory)
    // is handled inside openProjectProxy.
    if (typeof filepath === 'string' && filepath.startsWith('__proxy__/')) {
      const name = filepath.slice('__proxy__/'.length);
      return openProjectProxy(name);
    }
    const docRoot = root || (preserveScroll && _projDocRoot) || currentProject.path;
    _projDocRoot = docRoot;
    _contextSubView = 'document';
    _projDocPath = filepath;
    if (filepath.toLowerCase().endsWith('.ipynb')) {
      setLastProjectNotebook(currentProject.path, filepath);
    }
    renderRepoTabs();
    _projDocEditing = false;
    setLastProjectDoc(docRoot, filepath);
    // Coming back from a server view (which collapses the sidebar by
    // default) — restore this project's own sidebar preference.
    _sidebarApplyForView();
    const content = document.getElementById('content');
    const prevScroll = preserveScroll ? content.scrollTop : 0;
    // Skip the "Loading..." flash when we have a cached copy of this
    // doc — _renderDocInto's text branch will paint synchronously from
    // the cache below. For cache misses (or non-text files we don't
    // cache: notebooks/HTML/images) we still show the spinner.
    if (!preserveScroll) {
      const cacheKey = _projDocCacheKey(docRoot, filepath);
      if (!_projDocCache.has(cacheKey)) {
        content.innerHTML = '<div class="loading">Loading...</div>';
      }
    }

    // Highlight active in sidebar. Match on data-filepath (exact path) so the
    // mark lands on a single entry even when multiple files share a basename.
    // The sidebar rebuilders (_refreshProjectSidebar / selfPopulateSidebar)
    // also bake .active into the HTML they emit, so this is just for the
    // immediate click — we don't have to wait for the next rebuild to repaint.
    document.querySelectorAll('.sidebar-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll(`.sidebar-file[data-filepath="${CSS.escape(filepath)}"]`).forEach(el => el.classList.add('active'));

    // preserveScroll early-return: skip re-render when content/comments/artifact unchanged
    if (preserveScroll) {
      // Capture the project/file at entry so an async paint landing
      // after the user has navigated to a different file bails instead
      // of stomping the new view.
      const _navProjectPath = currentProject.path;
      const _stillActiveNav = () => (
        _projDocPath === filepath && currentProject && currentProject.path === _navProjectPath
        && _projDocRoot === docRoot
      );
      // Notebooks, images, video, and HTML iframes have no meaningful _projDocContent
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
          fetch(`/api/project-file?path=${encodeURIComponent(docRoot)}&file=${encodeURIComponent(filepath)}`),
          fetch(`/api/project-comments?path=${encodeURIComponent(docRoot)}`),
          fetch(`/api/project-info?path=${encodeURIComponent(docRoot)}`),
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
        _projDocCache.set(_projDocCacheKey(docRoot, filepath),
          {content: data.content, comments: newComments, artifact: newArtifact});
        if (data.content === _projDocContent
            && JSON.stringify(newComments) === JSON.stringify(_projComments)
            && JSON.stringify(newArtifact) === JSON.stringify(_projDocArtifact)) {
          return;
        }
        if (!_stillActiveNav()) return;
        _projDocContent = data.content;
        _projComments = newComments;
        _projDocArtifact = newArtifact;
        renderProjectDoc(filepath, content);
        content.scrollTop = prevScroll;
      } catch (err) {
        if (!_stillActiveNav()) return;
        content.innerHTML = `<div class="no-repo"><p>Error: ${err.message}</p></div>`;
      }
      return;
    }

    await _renderDocInto(filepath, content);
  }

  // ─── Project proxies (per-project reverse-proxy to a local dev server) ───
  // Backed by /api/proxy/<project>/<name>/<path> + /ws/proxy/... in
  // routes/proxy.py. Declared in servers.json (legacy project.json proxies
  // remain readable when the standalone file does not exist):
  //   {"servers": [{"name": "frontend", "host": "localhost", "port": 3000, "path": "/"}]}
  // The frontend treats each proxy as a pseudo-file so all the sidebar
  // active-highlighting, "last opened" persistence, and warm-switch
  // caching work without special-casing. The synthetic doc path is
  // `__proxy__/<name>` (chosen so it cannot collide with a real file
  // path since `__proxy__` starts with `__` which is reserved).
  function _proxyFromCachedSidebar(name) {
    if (!currentProject || !currentProject.is_project) return null;
    const cached = _projectSidebarCache.get(currentProject.path);
    if (!cached || !Array.isArray(cached.proxies)) return null;
    return cached.proxies.find(p => p && p.name === name) || null;
  }

  function _proxyMountPath(projectId, name, workspaceId = null) {
    if (workspaceId) {
      return `/api/workspace-proxy/${encodeURIComponent(workspaceId)}/${encodeURIComponent(projectId)}/${encodeURIComponent(name)}/`;
    }
    return `/api/proxy/${encodeURIComponent(projectId)}/${encodeURIComponent(name)}/`;
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
    const projectId = currentProject && currentProject.name;
    if (!projectId || !name) return null;
    // Direct mode: iframe straight to the upstream origin. Faster + no
    // path rewriting needed, but the browser must be able to reach
    // the upstream host:port directly (so won't work over an SSH
    // port-forward where only the lab port is exposed).
    if (p && p.mode === 'direct') return _proxyDirectUrl(p);
    const path = (p && p.path) ? String(p.path) : '/';
    const initial = path.replace(/^\/+/, '');
    return _proxyMountPath(projectId, name, _projectWorkspaceId(currentProject)) + initial;
  }

  // Inline iframe + controls bar. The controls let the user reload the
  // inner app, copy the proxied URL, pop it out into a new tab (so it
  // lives alongside other browser tabs), or expand into a borderless
  // fullscreen view that hides the rest of the lab UI chrome.
  async function openProjectProxy(name) {
    if (!currentProject || !currentProject.is_project) return;
    if (!name) return;
    // The iframe hosts a live, stateful app — never rebuild it when this
    // proxy is already the active view (file-watcher refreshes, sidebar
    // re-clicks, and tab revisits all funnel here and used to reload the
    // inner app, losing its state). The toolbar "Reload" button is the
    // explicit way to restart it.
    const existingWrap = document.getElementById('proxyWrap');
    if (existingWrap && existingWrap.dataset.proxy === name && document.getElementById('proxyIframe')) {
      _projDocPath = '__proxy__/' + name;
      renderRepoTabs();
      _sidebarApplyForView();
      return;
    }
    const p = _proxyFromCachedSidebar(name);
    const proxyPath = '__proxy__/' + name;
    _projDocPath = proxyPath;
    _projDocEditing = false;
    setLastProjectDoc(currentProject.path, proxyPath);
    // Server views default to a collapsed files sidebar so the embedded
    // app gets the full left + center width (per-view remembered state —
    // the Files edge handle still brings it back).
    _sidebarApplyForView();
    // The server view replaces whatever was in #content — if a repo diff
    // view was open, drop the repo selection and its diff tabs so the top
    // bar highlights this server's tab instead.
    currentRepo = null;
    currentRepoInProject = null;
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
          <button onclick="reloadProjectProxy('${safeName}')" title="Reload" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x21BB; Reload</button>
          <button onclick="openProjectProxyTab('${safeName}')" title="Open in new browser tab" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">Pop out &#x2197;</button>
          <button onclick="copyProjectProxyInstallCmd('${safeName}', this)" title="Copy osacompile command to create a Chrome standalone-window app for this URL" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x1F4E6; Install</button>
          <button onclick="copyProjectProxyUninstallCmd('${safeName}', this)" title="Copy command to remove the installed Chrome app from $HOME/Applications" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x1F5D1; Uninstall</button>
          <button onclick="toggleProjectProxyFullscreen()" id="proxyFullscreenBtn" title="Expand to fill the viewport (Esc to exit)" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer">&#x26F6; Fullscreen</button>
        </div>
        <iframe id="proxyIframe" src="${esc(url)}" style="flex:1;width:100%;border:0;background:#fff" onload="applyIframeDarkMode(this)"></iframe>
      </div>
    `;
  }

  function reloadProjectProxy(name) {
    const iframe = document.getElementById('proxyIframe');
    if (!iframe) return openProjectProxy(name);
    // Force a full reload (drops the HMR client too) instead of just
    // re-pointing the src — bypasses cached errored states.
    try { iframe.contentWindow.location.reload(); }
    catch { iframe.src = iframe.src; }
  }

  function openProjectProxyTab(name) {
    const p = _proxyFromCachedSidebar(name);
    // Pop out via the same-origin /api/proxy mount so the new tab stays
    // on the lab origin (shared cookies, reachable wherever the lab is
    // reachable). Falls back to the direct upstream URL only if we
    // can't build a proxy mount (no current project id).
    const url = _proxyInitialUrl(p, name) || _proxyDirectUrl(p);
    if (url) window.open(url, '_blank', 'noopener');
  }

  function _projectProxyAppName(name) {
    return String(name || '').replace(/[^A-Za-z0-9_-]/g, '');
  }

  function _copyProjectProxyCommand(cmd, btn) {
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

  function copyProjectProxyInstallCmd(name, btn) {
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
    const safeName = _projectProxyAppName(name);
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
    _copyProjectProxyCommand(cmd, btn);
  }

  function copyProjectProxyUninstallCmd(name, btn) {
    const safeName = _projectProxyAppName(name);
    if (!safeName) return;
    const cmd = `rm -rf "$HOME/Applications/${safeName}.app"`;
    _copyProjectProxyCommand(cmd, btn);
  }

  // Fullscreen: hide the sidebar, term panel, attrs/repo/diff strips so
  // the iframe fills the viewport. Esc exits. Same effect as the user's
  // browser fullscreen but keeps the lab origin (cookies, lab UI WS).
  let _proxyEscHandler = null;
  function toggleProjectProxyFullscreen() {
    const wrap = document.getElementById('proxyWrap');
    if (!wrap) return;
    const on = document.body.classList.toggle('proxy-fullscreen');
    const btn = document.getElementById('proxyFullscreenBtn');
    if (btn) btn.innerHTML = on ? '&#x26F6; Exit fullscreen' : '&#x26F6; Fullscreen';
    if (on) {
      _proxyEscHandler = (ev) => {
        if (ev.key === 'Escape') toggleProjectProxyFullscreen();
      };
      document.addEventListener('keydown', _proxyEscHandler);
    } else if (_proxyEscHandler) {
      document.removeEventListener('keydown', _proxyEscHandler);
      _proxyEscHandler = null;
    }
  }

  // Sidebar "blue dot" entry point — open the notebook AND scroll the first
  // unread cell into view. Defaults to the same openProjectDoc path so the
  // file lands the same way the user would by clicking the row, then waits
  // one paint to make sure the cell HTML is in the DOM before scrolling.
  // Used as the dot's onclick (with event.stopPropagation() at the call site
  // so the surrounding row click doesn't double-fire).
  async function openProjectDocAndJumpToUnseen(filepath, root = null) {
    await openProjectDoc(filepath, root ? {root} : {});
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const target = document.querySelector('#content .nb-cell-unseen');
        if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});
      });
    });
  }

  function toggleCommentsPanel(btn) {
    const collapsed = localStorage.getItem('projDocCommentsCollapsed') === '0' ? '1' : '0';
    localStorage.setItem('projDocCommentsCollapsed', collapsed);
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

  function renderProjectDoc(filepath, container) {
    if (!container) container = document.getElementById('content');
    const fn = filepath.replace(/'/g, "\\'");
    const commentsCollapsed = localStorage.getItem('projDocCommentsCollapsed') !== '0';

    // Two-column: doc left, comments right
    let html = `<div style="display:flex;gap:0;position:relative">`;

    // Doc column
    html += `<div class="project-content" style="padding:24px;flex:1;min-width:0">`;
    // Header with edit/save buttons
    html += `<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px">`;
    html += `<span style="font-size:12px;color:#484f58;font-family:monospace;flex:1">${esc(filepath)}</span>`;
    if (!_projDocEditing) {
      html += `<button onclick="copyForGDocs(event)" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">&#x1F4CB; Copy</button>`;
      html += `<button onclick="startProjectDocEdit()" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Edit</button>`;
      html += `<button onclick="linkProjectDocArtifact('${fn}')" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer" title="Attach the online URL (Google Doc, etc.) that mirrors this file">&#x1F517; Link</button>`;
      const toggleColor = (!commentsCollapsed && _projComments.length > 0) ? '#388bfd' : '#8b949e';
      const toggleBorder = (!commentsCollapsed && _projComments.length > 0) ? '#388bfd' : '#30363d';
      const toggleTitle = commentsCollapsed ? 'Show comments' : 'Hide comments';
      const commentCount = _projComments.length > 0 ? ` (${_projComments.length})` : '';
      html += `<button id="commentsToggleBtn" onclick="toggleCommentsPanel(this)" style="background:#21262d;color:${toggleColor};border:1px solid ${toggleBorder};padding:4px 10px;border-radius:4px;font-size:12px;cursor:pointer" title="${toggleTitle}">&#x1F4AC;${commentCount}</button>`;
    } else {
      html += `<button onclick="saveProjectDoc('${fn}')" style="background:#238636;color:#fff;border:1px solid #238636;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Save</button>`;
      html += `<button onclick="cancelProjectDocEdit('${fn}')" style="background:#21262d;color:#8b949e;border:1px solid #30363d;padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">Cancel</button>`;
    }
    html += `</div>`;

    // "Published at" banner — surfaces the project.json.artifacts[] entry
    // whose `file` field matches this doc. Reminds the user that this
    // local file has a canonical online version (GDoc, Confluence, etc.)
    // so edits can be mirrored there.
    if (_projDocArtifact && _projDocArtifact.url) {
      const label = _projDocArtifact.title || _projDocArtifact.type || 'online version';
      html += `<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;margin-bottom:16px;background:#0d1b2a;border:1px solid #1f3a5f;border-radius:6px;font-size:13px">`;
      html += `<span style="opacity:.7">&#x1F4CE; Published at</span>`;
      html += `<a href="${esc(_projDocArtifact.url)}" target="_blank" rel="noopener" style="color:#58a6ff;text-decoration:none;word-break:break-all;flex:1">${esc(label)}</a>`;
      html += `<button onclick="linkProjectDocArtifact('${fn}')" style="background:transparent;color:#8b949e;border:1px solid #30363d;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer" title="Replace">Edit</button>`;
      html += `<button onclick="unlinkProjectDocArtifact(${_projDocArtifact.id})" style="background:transparent;color:#8b949e;border:1px solid #30363d;padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer" title="Remove link">&#x2716;</button>`;
      html += `</div>`;
    }

    if (_projDocEditing) {
      html += `<textarea id="projDocEditor" spellcheck="false" style="width:100%;min-height:500px;background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:16px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:15px;line-height:1.6;resize:vertical;outline:none;tab-size:4">${esc(_projDocContent)}</textarea>`;
    } else {
      let rendered = _projDocContent;
      if (filepath.endsWith('.md')) {
        try {
          const renderer = new marked.Renderer();
          renderer.image = function(href, title, text) {
            if (href && !href.startsWith('http') && !href.startsWith('data:') && currentProject) {
              const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
              const resolvedHref = _resolveRelPath(dir, href);
              href = `/api/project-asset?path=${encodeURIComponent(_projDocRoot || currentProject.path)}&file=${encodeURIComponent(resolvedHref)}&t=${_lastProjectMtime || Date.now()}`;
            }
            return `<img src="${href}" alt="${text || ''}"${title ? ` title="${title}"` : ''} style="max-width:100%;border-radius:4px;margin:8px 0">`;
          };
          rendered = marked.parse(_projDocContent, { renderer });
          // Rewrite relative src in iframes/embeds to use project-asset API
          rendered = rendered.replace(/<iframe([^>]*) src="([^"]+)"([^>]*)>/g, (match, pre, src, post) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            const newSrc = `/api/project-asset?path=${encodeURIComponent(_projDocRoot || currentProject.path)}&file=${encodeURIComponent(resolved)}`;
            return `<iframe${pre} src="${newSrc}"${post} onload="applyIframeDarkMode(this)">`;
          });
          // Also rewrite other relative src (img etc) not already handled
          rendered = rendered.replace(/ src="([^"]+)"/g, (match, src) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            return ` src="/api/project-asset?path=${encodeURIComponent(_projDocRoot || currentProject.path)}&file=${encodeURIComponent(resolved)}"`;
          });
        } catch(e) {
          rendered = `<pre>${esc(_projDocContent)}</pre>`;
        }
      } else if (filepath.endsWith('.json')) {
        try {
          const formatted = JSON.stringify(JSON.parse(_projDocContent), null, 2);
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto">${hlLine(formatted, 'json')}</pre>`;
        } catch(e) {
          rendered = `<pre>${esc(_projDocContent)}</pre>`;
        }
      } else {
        const lang = filenameLang(filepath);
        if (lang) {
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto;line-height:1.5">${hlLine(_projDocContent, lang)}</pre>`;
        } else {
          rendered = `<pre style="background:var(--bg-secondary);padding:16px;border-radius:8px;border:1px solid var(--border);overflow-x:auto">${esc(_projDocContent)}</pre>`;
        }
      }
      // Inline highlighting happens after innerHTML via highlightComments()
      // below. A plain string replace on the rendered HTML fails whenever a
      // selection crosses inline tags (e.g. "a **bold** word" renders as
      // `a <strong>bold</strong> word` — no substring match), so we walk
      // live text nodes instead and wrap a Range, which tolerates tags.
      // Inject copy buttons next to h2/h3 headers
      if (filepath.endsWith('.md')) {
        rendered = rendered.replace(/(<h([23])[^>]*>)(.*?)(<\/h[23]>)/g, (match, openTag, level, text, closeTag) => {
          const plainText = text.replace(/<[^>]+>/g, '').trim();
          const safeText = plainText.replace(/'/g, "\\'").replace(/"/g, '&quot;');
          return `${openTag}<span style="display:flex;align-items:center;gap:8px">${text}<button onclick="copySectionByHeading('${safeText}', ${level}, this)" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);padding:2px 8px;border-radius:4px;font-size:11px;cursor:pointer;flex-shrink:0;opacity:0.5" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0.5">Copy</button></span>${closeTag}`;
        });
      }
      html += `<div id="projDocBody" class="nb-markdown">${rendered}</div>`;
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
    if (_projComments.length > 0) {
      _projComments.forEach(c => {
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
    if (!_projDocEditing) {
      const docBody = container.querySelector('#projDocBody');
      if (docBody) {
        _projComments.forEach(c => { if (c.text) highlightCommentInNode(docBody, c.text, c.id); });
      }
    }

    if (_projDocEditing) {
      const ta = container.querySelector('#projDocEditor');
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
      const docBody = container.querySelector('#projDocBody');
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
    if (localStorage.getItem('projDocCommentsCollapsed') !== '0') {
      localStorage.setItem('projDocCommentsCollapsed', '0');
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
    if (!currentProject) return;
    try {
      await fetch('/api/project-comments', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _projDocRoot || currentProject.path, file: filepath, text: _pendingCommentText, comment }),
      });
      _pendingCommentText = '';
      _pendingCommentMark = null;  // the upcoming re-render rebuilds the DOM from scratch
      openProjectDoc(filepath);
    } catch (err) { alert('Error: ' + err.message); }
  }

  function startProjectDocEdit() {
    if (!_projDocPath) return;
    openProjectDocModal(_projDocPath, { editing: true, root: _projDocRoot || currentProject.path });
  }

  function cancelProjectDocEdit(filepath) {
    const editCtr = _projDocEditContainer;
    _projDocEditing = false;
    _projDocEditContainer = null;
    if (editCtr) renderProjectDoc(filepath, editCtr);
  }

  async function saveProjectDoc(filepath) {
    const editCtr = _projDocEditContainer;
    const ta = editCtr ? editCtr.querySelector('#projDocEditor') : document.getElementById('projDocEditor');
    if (!ta || !currentProject) return;
    try {
      const res = await fetch('/api/project-file', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _projDocRoot || currentProject.path, file: filepath, content: ta.value }),
      });
      if (!res.ok) { const e = await res.json(); alert(e.detail || 'Error saving'); return; }
      _projDocContent = ta.value;
      _projDocEditing = false;
      _projDocEditContainer = null;
      // Re-render modal in read mode with saved content, then refresh inline pane.
      if (editCtr) renderProjectDoc(filepath, editCtr);
      const content = document.getElementById('content');
      if (content) _renderDocInto(filepath, content);
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function resolveComment(commentId) {
    if (!currentProject) return;
    try {
      await fetch('/api/project-comments', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: _projDocRoot || currentProject.path, comment_id: commentId }),
      });
      openProjectDoc(_projDocPath);
    } catch (err) { alert('Error: ' + err.message); }
  }

  let _completeActionId = null;

  function completeAction(actionId) {
    if (!currentProject) return;
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
    if (!currentProject || !_completeActionId) return;
    const input = document.getElementById('actionArtifactsInput');
    const artifacts = input.value.split('\n').map(s => s.trim()).filter(Boolean);
    try {
      await fetch('/api/project-action-complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentProject.path, action_id: _completeActionId, artifacts }),
      });
      _completeActionId = null;
      document.getElementById('actionCompleteBox').style.display = 'none';
      showProjectInfo();
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function copyForGDocs(e) {
    // Copy rendered content as rich text (with inline images) for pasting into Google Docs
    const content = document.getElementById('content');
    if (!content) return;

    const btn = e ? (e.target.closest ? e.target.closest('button') : null) : null;
    if (btn) { btn.innerHTML = '&#x23F3; Copying...'; btn.style.color = '#d29922'; }

    // Temporarily force light mode for copying
    const wasDark = !document.body.classList.contains('light-mode');
    if (wasDark) document.body.classList.add('light-mode');

    // Create offscreen container with the content
    const container = document.createElement('div');
    container.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';

    // Clone and clean up interactive elements
    const clone = content.cloneNode(true);
    clone.querySelectorAll('button, textarea, input, .view-toggle, #commentInputBox, #commentsMargin').forEach(el => el.remove());

    // Convert images to inline base64 so they paste into GDocs
    const imgs = clone.querySelectorAll('img');
    await Promise.all(Array.from(imgs).map(async (img) => {
      try {
        const resp = await fetch(img.src);
        const blob = await resp.blob();
        const dataUrl = await new Promise(resolve => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.readAsDataURL(blob);
        });
        img.src = dataUrl;
      } catch(err) {}
    }));

    // Set explicit styles for GDocs compatibility (it needs inline styles)
    clone.style.fontFamily = 'Arial, sans-serif';
    // Flatten headings to a single plain-text node. renderProjectDoc wraps
    // h2/h3 contents in a <span style="display:flex"> to host an inline
    // "Copy" button; the button is removed above, but leaving the span
    // means the body-text rule below assigns it font-size:11pt. Google
    // Docs respects that inner span size and shrinks the heading. With
    // no descendants, Docs maps the tag cleanly to its native Heading
    // style (size 16 + no bold for H2, etc.) — which is what the user
    // expects from a gdocs paste.
    clone.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => {
      el.textContent = el.textContent.trim();
      el.removeAttribute('style');
      el.style.fontFamily = 'Arial, sans-serif';
    });
    // Body-text rules skip anything that sits inside a heading — redundant
    // with the flattening above, but keeps us safe if a heading ever does
    // carry preserved inline formatting in a future code path.
    clone.querySelectorAll('p, li, span, div, td, th, summary, details').forEach(el => {
      if (el.closest('h1, h2, h3, h4, h5, h6')) return;
      el.style.fontFamily = 'Arial, sans-serif';
      el.style.fontSize = '11pt';
      el.style.lineHeight = '1.15';
      el.style.color = '#000';
    });
    clone.querySelectorAll('ul, ol').forEach(el => { el.style.fontFamily = 'Arial, sans-serif'; el.style.paddingLeft = '24pt'; });
    clone.querySelectorAll('code').forEach(el => el.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;padding:1pt 3pt;color:#000;');
    clone.querySelectorAll('pre').forEach(el => el.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;padding:8pt;margin:6pt 0;color:#000;');
    clone.querySelectorAll('a').forEach(el => { el.style.color = '#1155cc'; el.style.fontFamily = 'Arial, sans-serif'; });
    clone.querySelectorAll('img').forEach(el => el.style.cssText = 'max-width:100%;height:auto;margin:8pt 0;');
    // Map every dark-theme text shade to pure black so the paste looks
    // like native Google Docs text instead of a washed-out gray. Anything
    // that was a lighter muted color in the UI (#8b949e, #484f58) still
    // reads fine as black in GDocs and matches the user's light-mode
    // reading experience.
    clone.querySelectorAll('*').forEach(el => {
      if (el.style.color && /#(e6edf3|8b949e|484f58|d29922)/i.test(el.style.color)) el.style.color = '#000';
      if (el.style.background && (el.style.background.includes('#161b22') || el.style.background.includes('#0d1117'))) el.style.background = '#ffffff';
    });

    container.appendChild(clone);
    document.body.appendChild(container);

    // Copy as rich HTML via Clipboard API (preserves images)
    try {
      const html = container.innerHTML;
      const blob = new Blob([html], { type: 'text/html' });
      await navigator.clipboard.write([new ClipboardItem({ 'text/html': blob })]);
    } catch(err) {
      // Fallback to execCommand
      const range = document.createRange();
      range.selectNodeContents(container);
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      document.execCommand('copy');
      sel.removeAllRanges();
    }
    document.body.removeChild(container);

    // Restore dark mode if it was active
    if (wasDark) document.body.classList.remove('light-mode');

    // Visual feedback
    if (btn) {
      btn.innerHTML = '&#x2714; Copied';
      btn.style.color = '#3fb950';
      setTimeout(() => { btn.innerHTML = '&#x1F4CB; Copy'; btn.style.color = ''; }, 1500);
    }
  }

  async function copySectionByHeading(headingText, level, btn) {
    // Extract section from raw markdown: from the heading line to the next heading of same or higher level
    if (!_projDocContent) return;
    const lines = _projDocContent.split('\n');
    const hPrefix = '#'.repeat(parseInt(level)) + ' ';
    let startIdx = -1;
    // Find the heading line
    for (let i = 0; i < lines.length; i++) {
      const stripped = lines[i].replace(/^#+\s+/, '').trim();
      if (stripped === headingText && lines[i].trimStart().startsWith(hPrefix)) {
        startIdx = i;
        break;
      }
    }
    if (startIdx === -1) return;
    // Find the end: next heading of same or higher level
    let endIdx = lines.length;
    for (let i = startIdx + 1; i < lines.length; i++) {
      const match = lines[i].match(/^(#{1,6})\s/);
      if (match && match[1].length <= parseInt(level)) {
        endIdx = i;
        break;
      }
    }
    const section = lines.slice(startIdx, endIdx).join('\n').trim();

    // Copy as rich text (rendered) for Google Docs pasting
    await ensureMarked().catch(() => {});
    const rendered = window.marked ? marked.parse(section) : `<pre>${esc(section)}</pre>`;
    const container = document.createElement('div');
    container.innerHTML = rendered;
    container.style.cssText = 'font-family:Arial,sans-serif;color:#000000;background:#ffffff;';
    // Same rule as copyForGDocs: flatten headings + skip their descendants
    // when applying body-text styles, so GDocs maps the tag to its native
    // Heading style (size 16, no bold for H2, etc.) instead of a custom
    // Normal-text-with-overrides paragraph.
    container.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(el => {
      el.textContent = el.textContent.trim();
      el.removeAttribute('style');
      el.style.fontFamily = 'Arial, sans-serif';
    });
    container.querySelectorAll('p, li, span, div, td, th').forEach(el => {
      if (el.closest('h1, h2, h3, h4, h5, h6')) return;
      el.style.fontFamily = 'Arial, sans-serif';
      el.style.fontSize = '11pt';
      el.style.lineHeight = '1.15';
      el.style.color = '#000';
    });
    container.querySelectorAll('code').forEach(el => el.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;padding:1pt 3pt;');
    container.querySelectorAll('pre').forEach(el => el.style.cssText = 'font-family:Courier New,monospace;font-size:10pt;background:#f0f0f0;padding:8pt;margin:6pt 0;');
    container.querySelectorAll('img').forEach(el => el.style.cssText = 'max-width:100%;height:auto;margin:8pt 0;');

    // Resolve relative image paths and convert to base64 for GDocs
    container.querySelectorAll('img').forEach(img => {
      const src = img.getAttribute('src');
      if (src && !src.startsWith('http') && !src.startsWith('data:') && !src.startsWith('/api/') && currentProject) {
        const dir = (_projDocPath && _projDocPath.includes('/')) ? _projDocPath.substring(0, _projDocPath.lastIndexOf('/')) : '';
        const resolved = _resolveRelPath(dir, src);
        img.src = `/api/project-asset?path=${encodeURIComponent(_projDocRoot || currentProject.path)}&file=${encodeURIComponent(resolved)}`;
      }
    });
    const imgs = container.querySelectorAll('img');
    await Promise.all(Array.from(imgs).map(async (img) => {
      try {
        const resp = await fetch(img.src);
        const blob = await resp.blob();
        const dataUrl = await new Promise(resolve => {
          const reader = new FileReader();
          reader.onloadend = () => resolve(reader.result);
          reader.readAsDataURL(blob);
        });
        img.src = dataUrl;
      } catch(err) {}
    }));

    container.style.position = 'fixed';
    container.style.left = '-9999px';
    document.body.appendChild(container);
    const range = document.createRange();
    range.selectNodeContents(container);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('copy');
    sel.removeAllRanges();
    document.body.removeChild(container);

    if (btn) {
      const orig = btn.textContent;
      btn.textContent = 'Copied';
      btn.style.color = '#3fb950';
      btn.style.opacity = '1';
      setTimeout(() => { btn.textContent = orig; btn.style.color = ''; btn.style.opacity = ''; }, 1500);
    }
  }

  // Attach (or replace) the online URL for the current doc. Writes into
  // project.json.artifacts[]. Same storage the `lab artifact add --file`
  // CLI touches, so either entry point is fine. Detects the artifact type
  // from the URL host for convenience.
  async function linkProjectDocArtifact(filepath) {
    if (!currentProject) return;
    const existing = _projDocArtifact && _projDocArtifact.url ? _projDocArtifact.url : '';
    const url = prompt('Online URL for ' + filepath + ' (Google Doc / Confluence / etc.)', existing);
    if (url === null) return;
    const clean = url.trim();
    if (!clean) return;
    const title = prompt('Title (optional)', (_projDocArtifact && _projDocArtifact.title) || filepath.split('/').pop()) || '';
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
      const infoRes = await fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`);
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
      await fetch(`/api/project-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentProject.path, data: info }),
      });
      openProjectDoc(filepath, { preserveScroll: true });
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function unlinkProjectDocArtifact(artifactId) {
    if (!currentProject || !artifactId) return;
    if (!confirm('Remove the online-version link from this doc?')) return;
    try {
      const infoRes = await fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`);
      const info = await infoRes.json();
      const arts = Array.isArray(info.artifacts) ? info.artifacts.filter(a => a && a.id !== artifactId) : [];
      info.artifacts = arts;
      await fetch(`/api/project-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentProject.path, data: info }),
      });
      openProjectDoc(_projDocPath, { preserveScroll: true });
    } catch (err) { alert('Error: ' + err.message); }
  }

  async function togglePin(filename) {
    if (!currentProject) return;
    try {
      const infoRes = await fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`);
      const info = await infoRes.json();
      let pinned = Array.isArray(info.pinned) ? [...info.pinned] : [];
      const idx = pinned.indexOf(filename);
      if (idx >= 0) {
        pinned.splice(idx, 1);
      } else {
        pinned.push(filename);
      }
      info.pinned = pinned;
      await fetch(`/api/project-info`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: currentProject.path, data: info }),
      });
      showProjectInfo();
    } catch(e) {}
  }

  function showProjectDashboard() {
    _contextSubView = 'overview';
    currentRepo = null;
    currentRepoInProject = null;
    _repoFileRoot = null;
    // Clear the doc path BEFORE rendering tabs — the Overview tab's active
    // state (and the sidebar view suffix) both read it. User explicitly
    // chose Dashboard, so also drop the remembered doc for this project.
    if (currentProject) setLastProjectDoc(currentProject.path, null);
    _projDocPath = null;
    _projDocRoot = null;
    renderRepoTabs();
    // Restore the project's own sidebar preference (a server view may
    // have collapsed it).
    _sidebarApplyForView();
    // Hide diff tabs when on dashboard
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    showProjectInfo();
  }

  function selectProjectRepo(repoPath) {
    _contextSubView = 'repository';
    currentRepoInProject = currentProject.repos.find(r => r.path === repoPath);
    currentRepo = repoPath;
    _repoFileRoot = null;
    // The diff view replaces any open doc/server view — clear the doc path
    // so the server tab un-highlights and the sidebar preference resets.
    _projDocPath = null;
    _projDocRoot = null;
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
  // opened (openProjectDoc) we stamp its current mtime; any subsequent
  // mtime advance means there are unseen outputs → amber dot.
  function _nbLastViewedKey(path) {
    return 'nbLastViewed:' + (currentProject ? currentProject.path : '') + '|' + path;
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
  // Per-file status from GET /api/git-status?repo=<project path> (short-TTL
  // cached server-side). Applied by MUTATING row classes/badges in place —
  // never by rebuilding the tree — so open folders, scroll position, and
  // hover state all survive a repaint.
  const _gitStatusByPath = new Map();  // project path -> {files, ignored, ts}
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
    // gitignored — plus a right-edge dot badge. Project-scoped folders only
    // (the shared `.claude/`, `.agents/`, `code/` meta trees live outside
    // the project and keep their plain styling).
    sidebar.querySelectorAll('.sidebar-folder[data-tree-scope^="project:"]').forEach(row => {
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
    if (!currentProject || !currentProject.is_project || !currentProject.path) return;
    const basePath = currentProject.path;
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
      if (currentProject && currentProject.path === basePath && _sidebarScopedRoot(basePath) === path) {
        _sidebarApplyGitStatus(entry);
      }
    } catch (e) {
      // Network hiccup — decorations just go stale until the next tick.
    } finally {
      _gitStatusInFlight = false;
    }
  }

  // Re-renders just the project file sidebar from scratch. Pulled out
  // of showProjectInfo so the mtime poller can call it independently
  // when a doc is open (otherwise newly added files don't appear in the
  // sidebar until the user navigates away and back).
  async function _refreshProjectSidebar({preserveScroll = false, _data = null} = {}) {
    if (!currentProject || !currentProject.is_project) return;
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) return;
    const prevSidebarScroll = preserveScroll ? sidebar.scrollTop : 0;
    const projectPath = currentProject.path;
    await _sidebarEnsureWorktrees(projectPath);
    const fileRoot = _sidebarScopedRoot(projectPath);
    if (_data && _data.fileRoot !== fileRoot) _data = null;

    // Warm switch: when no `_data` override is passed but the cache has
    // a payload for this project, paint instantly from the cache and
    // then reconcile against the server in the background. The
    // recursive call with `_data` set skips the fetches entirely so
    // the second paint only re-runs the render body (no network).
    if (!_data) {
      const cachedPayload = _projectSidebarCache.get(projectPath);
      if (cachedPayload && cachedPayload.fileRoot !== fileRoot) _projectSidebarCache.delete(projectPath);
      if (cachedPayload && cachedPayload.fileRoot === fileRoot) {
        // Synchronous warm paint — recursive call returns a Promise but
        // because `_data` short-circuits both fetches, all the render
        // work happens in the synchronous prefix.
        _refreshProjectSidebar({preserveScroll, _data: cachedPayload});
        // Background reconcile.
        Promise.resolve().then(async () => {
          try {
            const files = await _sidebarFetchProjectFiles(fileRoot);
            let pinned = [], references = [], proxies = [];
            try {
              const infoRes = await fetch(`/api/project-info?path=${encodeURIComponent(projectPath)}`);
              if (infoRes.ok) {
                const info = await infoRes.json();
                if (Array.isArray(info.pinned)) pinned = info.pinned;
                if (Array.isArray(info.references)) references = info.references;
                if (Array.isArray(info.proxies)) proxies = info.proxies;
              }
            } catch {}
            const fresh = {files, pinned, references, proxies, fileRoot};
            if (!currentProject || currentProject.path !== projectPath
                || _sidebarScopedRoot(projectPath) !== fileRoot) return;
            const prev = _projectSidebarCache.get(projectPath);
            _projectSidebarCache.set(projectPath, fresh);
            // Re-render only if (a) the data actually changed and (b)
            // the user is still on this project.
            if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
            _refreshProjectSidebar({preserveScroll: true, _data: fresh});
          } catch (e) {
            console.error('[_refreshProjectSidebar] reconcile failed:', e && e.stack || e);
          }
        });
        return;
      }
    }

    try {
      let files, pinnedNames, references, proxies;
      if (_data) {
        // Render from pre-loaded payload — cache hit or reconcile path.
        files = _data.files;
        pinnedNames = _data.pinned || [];
        references = _data.references || [];
        proxies = _data.proxies || [];
      } else {
        // Cold path: fetch fresh + write to cache.
        files = await _sidebarFetchProjectFiles(fileRoot);
        pinnedNames = [];
        references = [];
        proxies = [];
        try {
          const infoRes = await fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`);
          if (infoRes.ok) {
            const info = await infoRes.json();
            if (Array.isArray(info.pinned)) pinnedNames = info.pinned;
            if (Array.isArray(info.references)) references = info.references;
            if (Array.isArray(info.proxies)) proxies = info.proxies;
          }
        } catch(e) {}
        _projectSidebarCache.set(projectPath, {files, pinned: pinnedNames, references, proxies, fileRoot});
      }
      _rememberNotebookFolders(fileRoot, files);
      const fileEntries = (files || []).filter(f => f && f.type !== 'dir');
      const dirEntries = (files || []).filter(f => f && f.type === 'dir');
      const pinnedSet = new Set(pinnedNames);
      const filesByName = new Map(fileEntries.map(f => [f.name, f]));
      const worktreeSelected = fileRoot !== projectPath;
      const pinnedFiles = worktreeSelected ? [] : pinnedNames.filter(n => fileEntries.some(f => f.name === n));
      // Pinned rows are shortcuts, not a move operation. Keep every pinned
      // file in the normal folder tree as well so its original context never
      // disappears when the shortcut is created.
      const otherFiles = fileEntries;
      _sidebarRememberAvailableExtensions(fileEntries);
      _sidebarMaybeLogRecentDiagnostics(fileEntries, fileRoot);

      // "Meta" files are demoted to a bottom section so the sidebar reads as
      // a working list of docs first, plumbing second. Still visible; just
      // out of the way of daily navigation.
      const META_FILES = new Set(['project.json', 'servers.json', 'tasks.json', 'comments.json', 'CLAUDE.md']);
      // Folders that should open automatically — docs is where 95% of the
      // reading lives, so showing it collapsed by default hides everything.
      const AUTO_OPEN_FOLDERS = new Set(['docs', 'notebooks', 'links']);

      const metaFiles = worktreeSelected ? [] : otherFiles.filter(f => !f.path.includes('/') && META_FILES.has(f.name));
      const mainFiles = worktreeSelected ? otherFiles : otherFiles.filter(f => !(f.path === f.name && META_FILES.has(f.name)));

      // Active-file highlighting is baked into the rendered HTML (data-filepath
      // + .active class) so periodic sidebar rebuilds — from the mtime poller
      // and the index-updated WS event — preserve the red selection bar
      // instead of dropping it and waiting for openProjectDoc to re-add it,
      // which made the selection blink.
      const activePath = _projDocRoot === fileRoot ? (_projDocPath || null) : null;
      const dashActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${dashActive}" data-dashboard="1" onclick="showProjectDashboard()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">&#x1F4CB; Dashboard</span></a>`;
      sbHtml += _sidebarFileConfigButtonHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(projectPath);
      sbHtml += _sidebarWorktreePickerHtml(projectPath);
      sbHtml += symlinkLegendHtml();
      if (pinnedFiles.length) sbHtml += `<div class="sidebar-title">Pinned <span class="sidebar-title-count">${pinnedFiles.length}</span></div>`;
      pinnedFiles.forEach(name => {
        const f = filesByName.get(name) || {name, path: name};
        const safeName = name.replace(/'/g, "\\'");
        const label = name.replace(/\.md$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const activeCls = activePath === name ? ' active' : '';
        sbHtml += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(name)}" data-entry-kind="file" data-entry-path="${escAttr(name)}"${symlinkTitle(f)} onclick="openProjectDoc('${safeName}')" ondblclick="event.stopPropagation();openProjectDocModal('${safeName}')" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">${symlinkMarker(f)}&#x1F4CC; ${label}</span><span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${safeName}')" title="Unpin">&#x2716;</button></span></a>`;
      });
      // Servers — proxied local dev servers declared in servers.json (or
      // legacy project.json proxies). Each entry opens
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
          sbHtml += `<a class="sidebar-file${activeCls}" data-filepath="${esc(proxyPath)}" onclick="openProjectProxy('${safeName}')" ondblclick="event.stopPropagation();openProjectProxyTab('${safeName}')" title="${esc(title)}"><span class="sidebar-fname">&#x1F310; ${esc(label)}<span style="color:var(--text-dim);font-size:10px;margin-left:6px">:${esc(String(port))}</span></span></a>`;
        });
      }
      // Tree scope key for the persistent folder-open state. Declared
      // OUTSIDE the `mainFiles.length > 0` block because the
      // external-references and shared `.claude/` blocks below also call
      // `_treeIsOpen(_projTreeScope, …)`. A project with no mainFiles but
      // some references (or just the shared CLAUDE.md row) would otherwise
      // hit `ReferenceError: _projTreeScope is not defined` and blow out
      // the whole sidebar via the catch handler.
      const _projTreeScope = 'project:' + (currentProject && currentProject.name ? currentProject.name : '') + ':' + fileRoot;
      sbHtml += _sidebarWorktreeScopeStartHtml(projectPath);
      sbHtml += _sidebarRecentSectionHtml(fileEntries, activePath, fileRoot);
      sbHtml += _sidebarFilesTitle(fileRoot);
      if (mainFiles.length > 0 || dirEntries.length > 0) {
        const tree = buildSidebarTree([...dirEntries, ...mainFiles]);
        function renderTree(node, depth, parentPath) {
          let html = '';
          // Render folders first
          const folders = treeFolderNames(node);
          folders.forEach(folder => {
            const fid = 'folder-' + Math.random().toString(36).substr(2, 6);
            const fullPath = parentPath ? `${parentPath}/${folder}` : folder;
            const d = treeFolderEntry(node, folder, fullPath);
            const autoOpen = depth === 0 && AUTO_OPEN_FOLDERS.has(folder);
            const open = _treeIsOpen(_projTreeScope, fullPath, autoOpen);
            const arrowCls = open ? ' open' : '';
            const childrenCls = open ? ' open' : '';
            html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(_projTreeScope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}" data-entry-kind="folder" data-entry-path="${escAttr(fullPath)}" data-entry-root="${escAttr(fileRoot)}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">\u25B6</span>${symlinkMarker(d)}${esc(folder)}/</div>`;
            html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
            html += renderTree(node[folder], depth + 1, fullPath);
            html += '</div>';
          });
          // Then files
          treeFiles(node).forEach(f => {
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
              dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openProjectDocAndJumpToUnseen('${safePath}','${safeRoot}')"></span>`;
            }
            const activeCls = activePath === f.path ? ' active' : '';
            const isPinned = pinnedSet.has(f.name);
            const pinHtml = worktreeSelected ? '' : `<span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${f.name.replace(/'/g, "\\'")}')" title="${isPinned ? 'Unpin' : 'Pin to top'}">${isPinned ? '&#x2716;' : '&#x1F4CC;'}</button></span>`;
            html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}" data-entry-kind="file" data-entry-path="${escAttr(f.path)}" data-entry-root="${escAttr(fileRoot)}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}',{root:'${safeRoot}'})"><span class="sidebar-fname">${dotHtml}${icon}${fname}</span>${pinHtml}</a>`;
          });
          return html;
        }
        sbHtml += renderTree(tree, 0, '');
      }
      sbHtml += _sidebarWorktreeScopeEndHtml(projectPath);

      // Virtual ``external-references/`` folder — URLs from
      // project.json.references[]. They open in a new tab (not in the
      // doc pane) since they're real external links. The folder is
      // auto-expanded like docs/ so curated reading lives in plain sight.
      if (references.length > 0) {
        const extId = 'folder-ext-' + Math.random().toString(36).substr(2, 6);
        const _extOpen = _treeIsOpen(_projTreeScope, 'external-references', true);
        const _extArrow = _extOpen ? ' open' : '';
        const _extChildren = _extOpen ? ' open' : '';
        sbHtml += `<div class="sidebar-folder" data-tree-scope="${escAttr(_projTreeScope)}" data-tree-path="external-references" data-tree-target="${extId}" onclick="_treeToggleFolder(this)"><span class="folder-arrow${_extArrow}">▶</span>external-references/</div>`;
        sbHtml += `<div class="sidebar-folder-children${_extChildren}" id="${extId}">`;
        references.forEach(r => {
          const safeUrl = (r.url || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
          const title = r.title || r.url || '(untitled)';
          const safeTitle = String(title).replace(/</g, '&lt;').replace(/>/g, '&gt;');
          sbHtml += `<a class="sidebar-file" href="${safeUrl}" target="_blank" rel="noopener" title="${safeTitle}&#10;${r.url || ''}"><span class="sidebar-fname">\u{1F517} ${safeTitle}</span></a>`;
        });
        sbHtml += '</div>';
      }

      // Plumbing — project.json, servers.json, tasks.json, CLAUDE.md, plus a deep-link
      // to the shared `.claude/` that lives at the content root (one
      // level up from every project). Bottom of the list, muted styling,
      // still one click away.
      const hasMetaSection = metaFiles.length > 0;
      if (hasMetaSection) {
        sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
        metaFiles.forEach(f => {
          const safePath = f.path.replace(/'/g, "\\'");
          const fname = f.name;
          const icon = fileIconHtml(fname, f);
          const activeCls = activePath === f.path ? ' active' : '';
          sbHtml += `<a class="sidebar-file sidebar-file-meta${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}" data-entry-kind="file" data-entry-path="${escAttr(f.path)}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}')" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}')" style="opacity:.55"><span class="sidebar-fname">${icon}${fname}</span></a>`;
        });
      } else {
        sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
      }
      // Workspace-declared projections take precedence (migration step 5):
      // each row shows its true origin instead of the vague "(shared)".
      // Workspaces without workspace.json projections keep the legacy rows.
      const wsProjHtml = _wsProjectionMetaHtml(await loadWorkspaceProjections());
      let sharedClaudeFid = null;
      let sharedCodeFid = null;
      if (wsProjHtml) {
        sbHtml += wsProjHtml;
      } else {
      // Shared projects/CLAUDE.md — auto-loaded for every project
      // via Claude Code's CLAUDE.md walk-up. Renders inline in the doc pane.
      sbHtml += `<a class="sidebar-file sidebar-file-meta" onclick="openSharedFile('projects/CLAUDE.md')" title="projects/CLAUDE.md — shared boilerplate applied to every project under projects/" style="opacity:.7"><span class="sidebar-fname">${fileIconHtml('CLAUDE.md')}CLAUDE.md (shared)</span></a>`;
      // Canonical cross-tool instructions at the monorepo root. CLAUDE.md is a
      // symlink to this; Codex / Copilot read AGENTS.md directly.
      sbHtml += `<a class="sidebar-file sidebar-file-meta" onclick="openSharedFile('AGENTS.md')" title="AGENTS.md — canonical shared instructions at the monorepo root (CLAUDE.md symlinks to it)" style="opacity:.7"><span class="sidebar-fname">${fileIconHtml('AGENTS.md')}AGENTS.md (shared)</span></a>`;
      // Shared `.claude/` from the monorepo root, rendered as an
      // expandable folder. Children fetched from /api/cerebro/tree; each
      // file opens inline via openSharedFile. Placeholder rendered first;
      // populated by the async fetch below so the rest of the sidebar
      // doesn't wait on it.
      sharedClaudeFid = 'sf-claude-' + Math.random().toString(36).substr(2, 6);
      const _shClOpen = _treeIsOpen('shared-claude', '.claude', false);
      const _shClArrow = _shClOpen ? ' open' : '';
      const _shClChildren = _shClOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-claude" data-tree-path=".claude" data-tree-target="${sharedClaudeFid}" onclick="_treeToggleFolder(this)" title=".claude/ — shared skills, agents, hooks, settings (monorepo root)" style="opacity:.7"><span class="folder-arrow${_shClArrow}">▶</span>.claude/ (shared)</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shClChildren}" id="${sharedClaudeFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;
      // Shared `.agents/` (config, memory, cross-tool skills) from the monorepo
      // root — same expandable/async pattern as `.claude/`.
      const sharedAgentsFid = 'sf-agents-' + Math.random().toString(36).substr(2, 6);
      const _shAgOpen = _treeIsOpen('shared-agents', '.agents', false);
      const _shAgArrow = _shAgOpen ? ' open' : '';
      const _shAgChildren = _shAgOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-agents" data-tree-path=".agents" data-tree-target="${sharedAgentsFid}" onclick="_treeToggleFolder(this)" title=".agents/ — shared config, memory & skills (cross-tool: Claude / Codex / Copilot)" style="opacity:.7"><span class="folder-arrow${_shAgArrow}">▶</span>.agents/ (shared)</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shAgChildren}" id="${sharedAgentsFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;
      // `content/code/` — source for code-* skills. Same shared/async
      // pattern as `.claude/`.
      sharedCodeFid = 'sf-code-' + Math.random().toString(36).substr(2, 6);
      const _shCdOpen = _treeIsOpen('shared-code', 'code', false);
      const _shCdArrow = _shCdOpen ? ' open' : '';
      const _shCdChildren = _shCdOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-code" data-tree-path="code" data-tree-target="${sharedCodeFid}" onclick="_treeToggleFolder(this)" title="content/code/ — source for code-* skills" style="opacity:.7"><span class="folder-arrow${_shCdArrow}">▶</span>code/ (shared)</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shCdChildren}" id="${sharedCodeFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;
      }
      sidebar.innerHTML = sbHtml;
      if (preserveScroll) sidebar.scrollTop = prevSidebarScroll;
      // Server tabs on the top bar are derived from the same proxies list
      // rendered above — re-sync so they appear/update as soon as the list
      // is known (cold load fetch or background reconcile).
      renderRepoTabs();
      // Populate both `.claude/` and `code/` placeholders from one
      // /api/cerebro/tree fetch (legacy rows only).
      if (sharedClaudeFid) _populateSharedMetaPlaceholders(sharedClaudeFid, sharedCodeFid);
      // Git decorations: the rebuild wiped the row classes — repaint from
      // cache synchronously, then fetch fresh in the background if stale.
      _sidebarGitStatusRefresh();
    } catch(e) {
      // Surface the underlying failure so it lands in the browser console
      // AND the server-side client-errors log (window.onerror -> /api/log).
      // Without this the catch silently degrades the sidebar to a bare
      // "Project" title and we lose the actual reason every time.
      console.error('[_refreshProjectSidebar] failed:', e && e.stack || e);
      // Only wipe the sidebar if it's empty — otherwise we'd nuke the
      // previously-rendered file tree the user is still looking at, which
      // is strictly worse than leaving the old list visible while we log
      // the underlying error.
      if (!sidebar.children.length) {
        sidebar.innerHTML = '<div class="sidebar-title">Project</div>';
      }
    }
  }

  function paintProjectShell() {
    if (!currentProject || !currentProject.is_project) return;
    const content = document.getElementById('content');
    if (!content) return;
    const repos = Array.isArray(currentProject.repos) ? currentProject.repos : [];
    const desc = currentProject.description || 'Project dashboard';
    content.innerHTML = `
      <div style="padding:24px;max-width:900px">
        <div style="margin-bottom:28px">
          <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">
            <h1 style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(_projectDisplayName(currentProject))}</h1>
            ${currentProject.status ? `<span style="color:var(--accent);font-size:13px;font-weight:600;background:rgba(88,166,255,.12);padding:2px 10px;border-radius:12px">${esc(currentProject.status)}</span>` : ''}
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

  function _setProjectDisplayName(projectPath, displayName) {
    const update = project => {
      if (project && project.path === projectPath) project.display_name = displayName;
    };
    (projectsList || []).forEach(update);
    (projTabsAll || []).forEach(update);
    (workspaceCatalog || []).forEach(workspace => {
      (workspace.project_rows || []).forEach(update);
    });
    update(currentProject);
  }

  async function projectSaveDisplayName(event) {
    if (event) event.preventDefault();
    if (!currentProject || !currentProject.is_project) return false;
    const input = document.getElementById('projectDisplayName');
    const status = document.getElementById('projectDisplayNameStatus');
    const projectId = currentProject.name;
    const projectPath = currentProject.path;
    const workspaceId = _projectWorkspaceId(currentProject);
    const displayName = String(input && input.value || '').trim() || projectId;
    if (status) status.textContent = 'Saving…';
    try {
      const suffix = workspaceId ? '?workspace=' + encodeURIComponent(workspaceId) : '';
      const r = await fetch('/api/projects/' + encodeURIComponent(projectId) + '/field' + suffix, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field: 'name', value: displayName}),
      });
      const updated = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(updated.detail || 'Could not save the project name');
      const savedName = String(updated.name || projectId);
      _setProjectDisplayName(projectPath, savedName);
      if (input) input.value = savedName;
      if (currentProject && currentProject.path === projectPath) {
        const heading = document.querySelector('[data-project-display-title]');
        if (heading) heading.textContent = savedName;
        document.title = savedName;
      }
      projTabsRender();
      if (status) status.textContent = 'Saved';
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.projectSaveDisplayName = projectSaveDisplayName;

  async function showProjectInfo({preserveScroll = false, keepShell = false} = {}) {
    if (!currentProject || !currentProject.is_project) return;
    const projectPath = currentProject.path;
    const content = document.getElementById('content');
    const prevContentScroll = preserveScroll ? content.scrollTop : 0;
    if (!preserveScroll && !keepShell) content.innerHTML = '<div class="loading">Loading project dashboard...</div>';
    await _refreshProjectSidebar({preserveScroll});

    try {
      const [infoRes, actionsRes, onepagerRes, artifactsRes, alertsRes] = await Promise.all([
        fetch(`/api/project-info?path=${encodeURIComponent(projectPath)}`),
        fetch(`/api/project-actions?path=${encodeURIComponent(projectPath)}`),
        fetch(`/api/project-onepager?path=${encodeURIComponent(projectPath)}`),
        fetch(`/api/project-artifacts?path=${encodeURIComponent(projectPath)}`),
        fetch(`/api/project-alerts?path=${encodeURIComponent(projectPath)}`),
      ]);

      const info = await infoRes.json();
      const actions = await actionsRes.json();
      const onepager = await onepagerRes.json();
      const artifacts = await artifactsRes.json();
      const alerts = await alertsRes.json();
      if (!currentProject || currentProject.path !== projectPath) return;

      // project-info is the authoritative project.json read. Reconcile its
      // display name into every tab cache so a stale catalog response cannot
      // leave the active tab showing the folder id after Overview has updated.
      const projectDisplayName = String(info.name || info.id || currentProject.name);
      _setProjectDisplayName(projectPath, projectDisplayName);
      document.title = projectDisplayName;
      projTabsRender();

      // Status color
      const statusColor = info.status === 'active' ? '#3fb950' : info.status === 'paused' ? '#d29922' : '#8b949e';

      let html = '<div style="padding:24px;max-width:900px">';

      // Header with prominent TLDR.
      html += `<div style="margin-bottom:28px">`;
      html += `<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">`;
      html += `<h1 data-project-display-title style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(info.name || info.id)}</h1>`;
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

      // The visible name is independent from the stable folder/project id.
      // Saving goes through `lab project set`, never a direct project.json write.
      html += `<form onsubmit="return projectSaveDisplayName(event)" style="display:flex;align-items:end;gap:10px;flex-wrap:wrap;border:1px solid var(--border);border-radius:8px;padding:12px 14px;background:var(--bg-secondary);margin:-12px 0 24px">`;
      html += `<label style="display:flex;flex-direction:column;gap:4px;color:var(--text-secondary);font-size:11px;min-width:220px;flex:1">Name shown in tabs<input id="projectDisplayName" type="text" value="${escAttr(info.name || info.id)}" maxlength="80" placeholder="${escAttr(info.id)}" style="background:var(--bg-tertiary);color:var(--text-primary);border:1px solid var(--border);border-radius:4px;padding:6px 8px"></label>`;
      html += `<button type="submit" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);border-radius:4px;padding:6px 10px;cursor:pointer">Save name</button>`;
      html += `<span id="projectDisplayNameStatus" style="color:var(--text-dim);font-size:11px;min-width:42px"></span>`;
      html += `<span style="width:100%;color:var(--text-dim);font-size:11px">Folder / project id stays <code>${esc(info.id)}</code>.</span>`;
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
      html += `<h3 style="color:#e6edf3;margin-bottom:12px;font-size:14px">Repositories <span style="color:#484f58;font-weight:400">${currentProject.repos.length}</span></h3>`;
      currentProject.repos.forEach(r => {
        html += `<div style="padding:6px 8px;margin-bottom:4px;border:1px solid #30363d;border-radius:6px;cursor:pointer;font-size:13px" onmouseover="this.style.background='#21262d'" onmouseout="this.style.background=''" onclick="selectProjectRepo('${r.path}')">`;
        html += `<div style="color:#58a6ff;font-family:monospace">${esc(r.name)}</div>`;
        html += `<div style="color:#484f58;font-size:11px">${esc(r.branch)}</div>`;
        html += `</div>`;
      });
      if (currentProject.repos.length === 0) {
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
      // Race guard: showProjectInfo fires several async fetches and only
      // writes to `content` at the end. If the user clicked a repo tab
      // mid-flight, selectProjectRepo + loadDiff already painted the diff.
      // Also bail if `_projDocPath` is set — selectRepo now fires
      // showProjectInfo and openProjectDoc in parallel, and the doc paint
      // owns `content` whenever a remembered doc was found.
      if (currentRepo || _projDocPath) return;
      content.innerHTML = html;
      if (preserveScroll) content.scrollTop = prevContentScroll;

    } catch (err) {
      if (currentRepo) return;
      content.innerHTML = `<div class="no-repo"><p>Error loading project dashboard: ${err.message}</p></div>`;
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
  let _workspaceAgentPolicy = null; // {supported: string[], default: string}
  let _setDraft = null;      // {defaultAgent, model, theme} while the modal is open
  let _setProjDraft = null;  // {agent, model} override for the active project

  async function loadWorkspaceAgentPolicy({force = false} = {}) {
    const workspaceId = _termWorkspaceId();
    if (_workspaceAgentPolicy && _workspaceAgentPolicy.workspace === workspaceId && !force) return _workspaceAgentPolicy;
    try {
      const suffix = workspaceId ? '?workspace=' + encodeURIComponent(workspaceId) : '';
      const r = await fetch('/api/workspace/agents' + suffix);
      if (r.ok) {
        const policy = await r.json();
        const supported = Array.isArray(policy.supported)
          ? policy.supported.filter(a => Object.prototype.hasOwnProperty.call(AGENT_LABELS, a))
          : [];
        if (supported.length) {
          _workspaceAgentPolicy = {
            workspace: workspaceId,
            supported,
            default: supported.includes(policy.default) ? policy.default : supported[0],
          };
          return _workspaceAgentPolicy;
        }
      }
    } catch {}
    return {supported: Object.keys(AGENT_LABELS), default: _settings.defaultAgent || 'claude'};
  }

  function supportedAgentIds() {
    return (_workspaceAgentPolicy && _workspaceAgentPolicy.supported) || Object.keys(AGENT_LABELS);
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

  // Dirty flags: the drafts CLAMP stored values that are workspace-disabled
  // (for display), so saving must only write back fields the user actually
  // touched — otherwise saving a theme tweak would silently rewrite the
  // default agent or clear a project override.
  let _setAgentTouched = false;
  let _setProjTouched = false;

  async function openSettings() {
    const policy = await loadWorkspaceAgentPolicy();
    _setAgentTouched = false;
    _setProjTouched = false;
    _setDraft = {
      defaultAgent: policy.supported.includes(_settings.defaultAgent)
        ? _settings.defaultAgent
        : policy.default,
      model: _settings.model || null,
      theme: document.body.classList.contains('light-mode') ? 'light' : 'dark',
      autopilot: { ...(_settings.autopilot || {}) },
    };
    _renderSettingsGlobal();

    // Per-project override (only when a real project tab is active).
    const sec = document.getElementById('setProjectSection');
    _setProjDraft = null;
    const currentPid = (typeof currentProject !== 'undefined' && currentProject) ? currentProject.name : null;
    const pid = currentPid && !currentPid.startsWith('__') ? currentPid : null;
    if (pid) {
      document.getElementById('setProjectName').textContent = pid;
      sec.style.display = 'flex';
      const pAgent = document.getElementById('setProjectAgent');
      const pModel = document.getElementById('setProjectModel');
      pAgent.innerHTML = '<option value="">Inherit workspace default</option>'
        + policy.supported.map(a => `<option value="${a}">${AGENT_LABELS[a]}</option>`).join('');
      pAgent.value = '';
      _fillModelSelect(pModel, _setDraft.defaultAgent, '');
      try {
        const r = await fetch('/api/projects/' + encodeURIComponent(pid));
        if (r.ok) {
          const proj = await r.json();
          _setProjDraft = {
            agent: policy.supported.includes(proj.agent) ? proj.agent : '',
            model: proj.model || '',
          };
          pAgent.value = _setProjDraft.agent || '';
          _fillModelSelect(pModel, _setProjDraft.agent || _setDraft.defaultAgent, _setProjDraft.model);
        }
      } catch {}
      pAgent.onchange = (e) => {
        _setProjDraft = _setProjDraft || { agent: '', model: '' };
        _setProjDraft.agent = e.target.value;
        _setProjTouched = true;
        _fillModelSelect(pModel, e.target.value || _setDraft.defaultAgent, _setProjDraft.model);
      };
      pModel.onchange = (e) => {
        _setProjDraft = _setProjDraft || { agent: '', model: '' };
        _setProjDraft.model = e.target.value;
        _setProjTouched = true;
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
      // draft may hold a display-only clamp of a workspace-disabled value.
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

      const pid = (typeof currentProject !== 'undefined' && currentProject) ? currentProject.name : null;
      if (_setProjDraft && _setProjTouched && pid) {
        const pr = await fetch('/api/projects/' + encodeURIComponent(pid) + '/agent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent: _setProjDraft.agent || null,
            model: _setProjDraft.model || null,
          }),
        });
        if (!pr.ok) throw new Error((await pr.json().catch(() => ({}))).detail || 'project override failed');
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
    hint.textContent = 'syncing…';
    try {
      const r = await fetch('/api/agents/sync', { method: 'POST' });
      const data = await r.json();
      const n = (data.actions || []).length;
      hint.textContent = n ? `done — ${n} change(s).` : 'already in sync.';
    } catch (e) {
      hint.textContent = 'sync failed: ' + (e.message || e);
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
  const urlProject = new URLSearchParams(location.search).get('project');
  // When ?ui_check=1, skip all persistent timers + WS so Chrome's --dump-dom
  // can reach network idle and exit promptly. See scripts/check-ui.sh.
  const UI_CHECK = new URLSearchParams(location.search).get('ui_check') === '1';

  // Project tab-strip state. MUST be declared before projTabsRefresh() is
  // called below, or `let` TDZ throws "Cannot access X before initialization".
  let projTabsHot = [];           // [{project_id, workspace}] with live sessions
  let projTabsAll = [];           // projects from every registered workspace
  let projTabsRefreshTimer = null;
  let projTabsOrder = [];        // user-chosen order (from /api/ui/tab-order)
  let projTabsDragPid = null;    // pid currently being dragged
  let _contextSubView = 'overview';
  const OPEN_WORKSPACES_KEY = 'labOpenWorkspaces-v1';

  function _openWorkspaceIds() {
    try {
      const value = JSON.parse(localStorage.getItem(OPEN_WORKSPACES_KEY) || '[]');
      return Array.isArray(value) ? value.filter(v => typeof v === 'string') : [];
    } catch { return []; }
  }

  function _setWorkspaceTabOpen(workspaceId, open) {
    const ids = new Set(_openWorkspaceIds());
    if (open) ids.add(workspaceId); else ids.delete(workspaceId);
    try { localStorage.setItem(OPEN_WORKSPACES_KEY, JSON.stringify(Array.from(ids))); } catch {}
  }

  function _workspaceById(workspaceId) {
    return (workspaceCatalog || []).find(ws => ws && ws.id === workspaceId) || null;
  }

  function _projectWorkspaceId(project) {
    if (!project) return null;
    if (project.workspace_id) return project.workspace_id;
    if (project.workspace) return project.workspace;
    const known = [...(projectsList || []), ...(projTabsAll || [])]
      .find(candidate => candidate && candidate.path === project.path);
    if (known && (known.workspace_id || known.workspace)) {
      return known.workspace_id || known.workspace;
    }
    const normalizedPath = String(project.path || '').replace(/\/+$/, '');
    const owner = (workspaceCatalog || []).find(ws => {
      const root = String(ws && ws.path || '').replace(/\/+$/, '');
      return root && (normalizedPath === root || normalizedPath.startsWith(root + '/'));
    });
    return owner ? owner.id : null;
  }

  function _workspaceForProject(project) {
    if (!project) return null;
    const workspaceId = _projectWorkspaceId(project);
    return _workspaceById(workspaceId) || {
      id: workspaceId || '',
      name: project.workspace_name || workspaceId || '',
      color: project.workspace_color || '#8b949e',
      path: project.workspace_path || '',
    };
  }

  function _termWorkspaceId() {
    if (document.body.classList.contains('self-active')) return null;
    return _projectWorkspaceId(currentProject);
  }

  function _workspaceQuery(workspaceId = _termWorkspaceId()) {
    return workspaceId ? '&workspace=' + encodeURIComponent(workspaceId) : '';
  }

  function _termSessionsKey(projectId, workspaceId = _termWorkspaceId()) {
    return String(workspaceId || 'framework') + '::' + String(projectId || '');
  }

  // Which tab (if any) looks blocked because a recent fetch for it hit
  // fsguard's 503 (stalled workspace volume). error-report.js can't know
  // which project a given fetch belongs to, so it just dispatches the
  // event and we mark whatever project tab is currently active -- good
  // enough to answer "is my SSD read stuck?" without precise attribution.
  // Cleared as soon as any later fetch succeeds.
  let tabBlocked = { pid: null, detail: null };
  window.addEventListener('lab:resource-unavailable', (ev) => {
    const pid = (currentProject && currentProject.is_project) ? currentProject.name : null;
    if (!pid) return;
    tabBlocked = { pid, detail: (ev.detail && ev.detail.message) || 'resource is not available' };
    if (typeof projTabsRender === 'function') projTabsRender();
  });
  window.addEventListener('lab:resource-available', () => {
    if (!tabBlocked.pid) return;
    tabBlocked = { pid: null, detail: null };
    if (typeof projTabsRender === 'function') projTabsRender();
  });

  // Project tabs the user has opened. The durable bit still lives in each
  // project's own project.json, while workspace-home tabs live in browser
  // state because they are navigation chrome rather than workspace data.
  function projTabsOpenIds() {
    return (projTabsAll || []).filter(p => p && p.tab_open).map(p => p.path);
  }
  async function projTabsSetOpen(projectPath, open) {
    if (!projectPath) return;
    try {
      const infoRes = await fetch('/api/project-info?path=' + encodeURIComponent(projectPath));
      if (!infoRes.ok) throw new Error('project not found');
      const info = await infoRes.json();
      info.tab_open = !!open;
      await fetch('/api/project-info', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: projectPath, data: info}),
      });
    } catch (e) { /* best-effort; next refresh will pick up the truth */ }
    const p = (projTabsAll || []).find(x => x && x.path === projectPath);
    if (p) p.tab_open = !!open;
  }
  // Knowledge-view state. Same hoisting rule — initCerebro uses these.
  const CEREBRO_PROJECT_ID = '__cerebro__';
  let cerebroTreeData = [];
  let _cerebroTreePromise = null;
  let _cerebroTreeFetchedAt = 0;
  const CEREBRO_TREE_TTL_MS = 15000;
  let cerebroActivePath = null;
  // Hydrate from localStorage so folded/unfolded state survives reloads.
  // Persisted in lockstep on every toggle below.
  const cerebroExpanded = _treeLoadOpenSet('cerebro');  // dir paths currently open

  // Productivity self-view: the monorepo itself (commits + uncommitted + tasks).
  // Pseudo-project like Cerebro; no folder under knowledge/projects/.
  const SELF_PROJECT_ID = '__self__';
  const SELF_REPO_PATH = window.LAB_MONOREPO_ROOT || '';  // populated by index.html
  const WORKSPACE_ROOT = window.LAB_WORKSPACE_ROOT || '';  // active workspace; may differ from framework root

  // Workspace view: one management surface per registered workspace. The
  // selected workspace id travels in the URL and requests; no global switch.
  const WORKSPACE_PROJECT_ID = '__workspace__';
  let _workspaceCurrent = null;  // last `current` row painted by initWorkspaceView

  // Per-project session pill cache (warm-switch fast path). Declared up
  // here — alongside the other pseudo-project consts — instead of with
  // the rest of the terminal-panel state lower in the script, because
  // initCerebro/initSelf now read it synchronously before their first
  // await. The terminal state block at ~line 5780 still hosts the rest
  // of the related globals; this is the one that needs to win the TDZ.
  const _termSessionsCache = new Map(); // projectId -> sessions[]

  // localStorage key prefix for per-view terminal-visibility. Same
  // hoisting rule as the consts above — the visibility helpers are
  // called from termOpenForSelf/Cerebro during the initial URL
  // dispatch (`?view=…`), which runs before the helper definitions
  // further down the script. Without this hoist the helpers hit a
  // TDZ on `_TERM_VIS_KEY_PREFIX`.
  const _TERM_VIS_KEY_PREFIX = 'labTermShown:';
  const _TERM_SESSION_ORIENTATION_KEY = 'labTermSessionOrientation';
  const _TERM_SESSION_DETAIL_KEY = 'labTermSessionDetail';
  const _TERM_GROUPS_KEY = 'labTermGroups-v1';
  const _TERM_RECENT_MINUTES_KEY = 'labTermRecentMinutes';
  const _TERM_RECENT_COLOR_KEY = 'labTermRecentColor';
  const _TERM_RECENT_ACTIVITY_KEY = 'labTermRecentActivity-v1';
  const _TERM_RECENT_MINUTE_OPTIONS = [15, 30, 60, 180, 360, 720, 1440];
  const _TERM_GROUP_COLORS = ['#58a6ff', '#a371f7', '#3fb950', '#d29922', '#f85149', '#db61a2', '#39c5cf', '#8b949e'];
  let termSessionOrientation = 'vertical';
  let termSessionDetail = 'compact';
  let termRecentMinutes = 60;
  let termRecentColor = '#3fb950';
  let termRecentActivity = {};
  try {
    if (localStorage.getItem(_TERM_SESSION_ORIENTATION_KEY) === 'horizontal') {
      termSessionOrientation = 'horizontal';
    }
    if (localStorage.getItem(_TERM_SESSION_DETAIL_KEY) === 'full') {
      termSessionDetail = 'full';
    }
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

  function _termRecentScopeKey(projectId = _termActiveProjectId(), workspaceId = _termWorkspaceId()) {
    return _termSessionsKey(projectId, workspaceId);
  }

  function _termMarkRecent(projectId, sessionName, workspaceId = _termWorkspaceId(), usedAt = Date.now()) {
    if (!projectId || !sessionName) return;
    const session = (termSessions || []).find(item => item && item.name === sessionName);
    const logical = session && session.logical_name;
    if (!logical) return;
    const scope = _termRecentScopeKey(projectId, workspaceId);
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

  let _termRecentSettingsOutside = null;
  function termCloseRecentSettings() {
    const el = document.getElementById('termRecentSettings');
    if (el) el.classList.remove('open');
    if (_termRecentSettingsOutside) {
      document.removeEventListener('click', _termRecentSettingsOutside);
      _termRecentSettingsOutside = null;
    }
  }

  function termToggleRecentSettings(ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('termRecentSettings');
    if (!el) return;
    const opening = !el.classList.contains('open');
    termCloseRecentSettings();
    if (!opening) return;
    document.getElementById('termNewPicker')?.classList.remove('open');
    _termApplyRecentSettings();
    el.classList.add('open');
    _termRecentSettingsOutside = (event) => {
      if (!el.contains(event.target) && event.target.id !== 'termRecentSettingsBtn') {
        termCloseRecentSettings();
      }
    };
    setTimeout(() => {
      if (_termRecentSettingsOutside) document.addEventListener('click', _termRecentSettingsOutside);
      const select = document.getElementById('termRecentMinutes');
      if (select) select.focus();
    }, 0);
  }

  function _termApplySessionView(refit = true) {
    const panel = document.getElementById('termPanel');
    const sessionList = document.getElementById('termSessionList');
    const orientationBtn = document.getElementById('termOrientationBtn');
    const detailBtn = document.getElementById('termDetailBtn');
    const horizontal = termSessionOrientation === 'horizontal';
    const full = termSessionDetail === 'full';
    if (panel) {
      panel.classList.toggle('term-sessions-horizontal', horizontal);
      panel.classList.toggle('term-sessions-full', full);
    }
    if (sessionList) sessionList.setAttribute('aria-orientation', horizontal ? 'horizontal' : 'vertical');
    if (orientationBtn) {
      const text = horizontal ? 'Use vertical session rail' : 'Use horizontal session tabs';
      orientationBtn.textContent = horizontal ? '↕' : '↔';
      orientationBtn.title = text;
      orientationBtn.setAttribute('aria-label', text);
      orientationBtn.setAttribute('aria-pressed', horizontal ? 'true' : 'false');
    }
    if (detailBtn) {
      const text = full ? 'Use compact session icons' : 'Show full session names and agents';
      detailBtn.textContent = full ? '◉' : 'Aa';
      detailBtn.title = text;
      detailBtn.setAttribute('aria-label', text);
      detailBtn.setAttribute('aria-pressed', full ? 'true' : 'false');
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
    termSessionOrientation = termSessionOrientation === 'horizontal' ? 'vertical' : 'horizontal';
    try { localStorage.setItem(_TERM_SESSION_ORIENTATION_KEY, termSessionOrientation); } catch {}
    _termApplySessionView();
  }

  function termToggleSessionDetail() {
    termSessionDetail = termSessionDetail === 'full' ? 'compact' : 'full';
    try { localStorage.setItem(_TERM_SESSION_DETAIL_KEY, termSessionDetail); } catch {}
    _termApplySessionView();
  }

  // Apply before the initial route dispatch so direct project/pseudo-project
  // loads never flash the default switcher shape. Refit is intentionally off:
  // terminal state is declared later and no xterm exists yet.
  _termApplySessionView(false);
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
  const _dashServersPending = new Set();  // project_ids with an in-flight action
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

  afterPageQuiet(loadRepos);
  if (!UI_CHECK) afterPageQuiet(() => setInterval(loadRepos, 8000), 1000);
  if (!UI_CHECK) afterPageQuiet(() => setInterval(refreshDiff, 5000), 1000);
  // Project tab strip: initial render + periodic refresh.
  afterPageQuiet(workspaceRefresh, 250);
  afterPageQuiet(projTabsRefresh);
  if (!UI_CHECK) afterPageQuiet(projTabsStartPolling, 1000);

  // Cerebro view: when URL carries ?view=cerebro, we bypass the
  // project/repo init path entirely and render the mdview-style browser.
  const initialParams = new URLSearchParams(location.search);
  const urlView = initialParams.get('view');
  const urlCerebroPath = initialParams.get('path') || '';
  if (urlView === 'cerebro') {
    initCerebro(urlCerebroPath);
  } else if (urlView === 'productivity') {
    initSelf();
    if (initialParams.get('subview') === 'admin') selfShowAdmin();
    else if (initialParams.get('subview') === 'code-search') showScopedCodeSearch();
  } else if (urlView === 'workspace') {
    initWorkspaceView(initialParams.get('workspace') || currentWorkspaceId);
  } else if (urlView === 'code-search') {
    // Retired standalone route: keep old bookmarks useful by landing on the
    // framework-scoped Code Search subtab.
    initSelf();
    showScopedCodeSearch();
  } else if (urlView === 'logs') {
    initSelf();
    selfShowAdmin();
  }

  // Auto-refresh project view when any file in the project folder changes (mtime check)
  let _lastProjectMtime = 0;
  let _projMtimeMissPath = null; // project path the miss counter applies to
  let _projMtimeMisses = 0;      // consecutive "directory missing" responses
  let _projMtimeTick = 0;
  let _projMtimeInFlight = false;
  let _projMtimeFailures = 0;
  let _projMtimeRetryAt = 0;
  if (!UI_CHECK) setInterval(async () => {
    // A hidden tab can't show the refresh anyway, and the next visible
    // tick (≤1s away) catches up — don't let backgrounded windows keep
    // hitting the server (browser timer throttling made them poll ~1/min
    // forever, including tabs whose project no longer existed).
    if (document.hidden) return;
    if (!currentProject || !currentProject.is_project) return;
    if (currentRepo) return;
    if (_projDocEditing) return;
    const projectPath = currentProject.path;
    const fileRoot = typeof _sidebarScopedRoot === 'function' ? _sidebarScopedRoot(projectPath) : projectPath;
    if (_projMtimeMissPath !== fileRoot) {
      _projMtimeMissPath = fileRoot;
      _projMtimeMisses = 0;
      _projMtimeFailures = 0;
      _projMtimeRetryAt = 0;
      _lastProjectMtime = 0;
    }
    // Never stack recursive filesystem walks. Previously the one-second
    // interval launched another request while the prior request was still
    // waiting on the 10-second filesystem guard. One timeout could therefore
    // leave dozens of queued requests, producing the 503 cascade seen in the
    // logs even after the original scan had already failed.
    if (_projMtimeInFlight || Date.now() < _projMtimeRetryAt) return;
    _projMtimeTick += 1;
    // Project dir gone (deleted / volume unplugged): after a few misses,
    // probe only once a minute so it self-heals if the volume comes back.
    if (_projMtimeMisses >= 3 && _projMtimeTick % 60 !== 0) return;
    _projMtimeInFlight = true;
    try {
      const res = await fetch(`/api/project-mtime?path=${encodeURIComponent(fileRoot)}`);
      if (!res.ok) throw new Error(`project mtime request failed (${res.status})`);
      const { mtime } = await res.json();
      // A request for a tab we just navigated away from must not overwrite
      // the new project's baseline or retry state.
      if (!currentProject || currentProject.path !== projectPath
          || (typeof _sidebarScopedRoot === 'function' && _sidebarScopedRoot(projectPath) !== fileRoot)) return;
      _projMtimeFailures = 0;
      _projMtimeRetryAt = 0;
      if (mtime == null) { _projMtimeMisses += 1; return; }
      _projMtimeMisses = 0;
      if (_lastProjectMtime && mtime > _lastProjectMtime) {
        const isSelf = document.body.classList.contains('self-active');
        const isWorkspaceView = document.body.classList.contains('workspace-active');
        if (_projDocPath) {
          // Refresh the doc AND the sidebar — files added/removed in
          // the project (e.g. a new HTML under tmp/) need to appear in
          // the sidebar without forcing the user to navigate away. The
          // self/workspace views use their own sidebar renderers (no
          // project.json, no pinned/meta sections, no shared CLAUDE.md
          // / .claude shortcuts); calling _refreshProjectSidebar here
          // would stomp them with the project layout.
          openProjectDoc(_projDocPath, {preserveScroll: true});
          if (isSelf) selfPopulateSidebar();
          else if (isWorkspaceView) workspacePopulateSidebar();
          else _refreshProjectSidebar({preserveScroll: true});
        } else if (isSelf) {
          // Self view, no doc open → just refresh the sidebar so new
          // files appear without a full page reload.
          selfPopulateSidebar();
        } else if (isWorkspaceView) {
          workspacePopulateSidebar();
        } else {
          showProjectInfo({preserveScroll: true});
        }
      }
      _lastProjectMtime = mtime;
    } catch(e) {
      if (currentProject && currentProject.path === projectPath) {
        _projMtimeFailures += 1;
        const backoffMs = Math.min(60_000, 1_000 * (2 ** _projMtimeFailures));
        _projMtimeRetryAt = Date.now() + backoffMs;
      }
    } finally {
      _projMtimeInFlight = false;
    }
  }, 1000);

  // Sidebar git decorations poll. Separate from the 1s mtime poll above —
  // commits/checkouts only touch `.git/`, which the mtime walk skips — and
  // deliberately slower: the server caches `git status` for ~4s, so a 6s
  // cadence here means at most one subprocess per tick across all clients.
  if (!UI_CHECK) setInterval(() => {
    if (document.hidden) return;
    if (!currentProject || !currentProject.is_project) return;
    if (currentRepo) return;
    _sidebarGitStatusRefresh();
  }, 6000);

  // ─── Terminal panel (tmux + PTY bridge) ───
  // Visible whenever a project is active; scoped to that project. xterm.js
  // and addons are vendored and lazy-loaded before the first attach. State
  // is declared before the init dispatch for the same TDZ reason the home
  // state is.

  let termXterm = null;         // xterm.js Terminal instance (active session)
  let termFitAddon = null;      // addon that sizes xterm to its container (active)
  let termWS = null;            // active WebSocket to /ws/term/<name>
  let termContainer = null;     // per-session <div> inside #termBody (active session)
  let termCurrentSession = null; // tmux session name currently attached
  let termCurrentProjectId = null; // project/pseudo-project owning the active session
  let termSessions = [];        // last known list from /api/term/sessions
  let termUserDetached = false; // distinguishes user-initiated close from dropped WS
  let termRefreshTimer = null;  // periodic poll of /api/term/sessions
  let termReconnectTimer = null; // capped-backoff auto-reconnect loop
  let _termWheelListenerAdded = false; // wheel listener added once to termBody
  let _termPasteListenerAdded = false; // image paste listener added once to termBody
  let _termWheelAccum = 0;            // accumulated deltaY for scroll throttling
  let termAttachRequestSeq = 0;       // latest requested attach; prevents out-of-order switches
  // Per-session xterm+WS cache so SESSION-PILL switches (within the same
  // project, no navigation) don't wipe in-progress input.
  //
  // Project-tab clicks now navigate in-page, so this cache survives across
  // project switches. That makes the project id part of the identity: a
  // delayed attach from project A must never be allowed to display while
  // project B is active, even if both have a "claude" logical session.
  const _termCache = new Map(); // "projectId::name" -> {projectId, name, xterm, fitAddon, ws, container, parkedAt}
  // `_termSessionsCache` (projectId -> sessions[]) is the warm-switch
  // fast-path cache: it's declared at the top of the script (next to
  // CEREBRO_PROJECT_ID / SELF_PROJECT_ID) so initCerebro/initSelf can
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

  // Per-project "last selected" memory so leaving and returning to a project
  // (full page reload) restores whichever session pill the user had active
  // instead of snapping back to the canonical "claude" pill.
  //
  // Keyed by logical_name (not tmux name) because the logical name is the
  // project-relative identity and is stable across server/tmux restarts.
  // Stored as a single JSON map {projectId: logicalName}.
  const TERM_LAST_KEY = 'labTermLastSession';
  function _termActiveProjectId() {
    if (document.body.classList.contains('cerebro-active')) return CEREBRO_PROJECT_ID;
    if (document.body.classList.contains('self-active')) return SELF_PROJECT_ID;
    if (currentProject && currentProject.is_project) return currentProject.name;
    return null;
  }
  async function termAutoSpawnEnabled(projectId, workspaceId = _termWorkspaceId()) {
    if (!projectId) return true;
    try {
      const r = await fetch('/api/ui/term-autospawn?project_id=' + encodeURIComponent(projectId) + _workspaceQuery(workspaceId));
      if (!r.ok) return true;
      const body = await r.json();
      return body.enabled !== false;
    } catch {
      return true;
    }
  }
  async function termSetAutoSpawnEnabled(projectId, enabled, workspaceId = _termWorkspaceId()) {
    if (!projectId) return;
    try {
      await fetch('/api/ui/term-autospawn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({project_id: projectId, enabled: !!enabled, workspace: workspaceId}),
      });
    } catch {}
  }
  function _termRememberLast(projectId, logicalName) {
    if (!projectId || !logicalName) return;
    try {
      const raw = localStorage.getItem(TERM_LAST_KEY);
      const map = raw ? JSON.parse(raw) : {};
      if (map[projectId] === logicalName) return;
      map[projectId] = logicalName;
      localStorage.setItem(TERM_LAST_KEY, JSON.stringify(map));
    } catch {}
  }
  function _termRecallLast(projectId) {
    if (!projectId) return null;
    try {
      const raw = localStorage.getItem(TERM_LAST_KEY);
      if (!raw) return null;
      const map = JSON.parse(raw);
      return map[projectId] || null;
    } catch { return null; }
  }
  function _termPickRestoreName(projectId) {
    // Pick which session to attach when (re-)opening the panel: prefer the
    // user's last selection, fall back to canonical "claude", else first.
    if (!termSessions || termSessions.length === 0) return null;
    const lastLogical = _termRecallLast(projectId);
    if (lastLogical) {
      const hit = termSessions.find(s => s.logical_name === lastLogical);
      if (hit) return hit.name;
    }
    const claude = termSessions.find(s => s.logical_name === 'claude');
    return (claude || termSessions[0]).name;
  }
  function _termCacheKey(projectId, name) {
    return String(projectId || '') + '::' + String(name || '');
  }
  function _termCachedPaneIsFresh(cached) {
    if (!(cached && cached.ws && cached.ws.readyState === WebSocket.OPEN)) return false;
    if (cached.parkedAt && Date.now() - cached.parkedAt > TERM_FAST_PARK_MS) return false;
    return true;
  }
  function _termIsScopeActive(projectId) {
    return !!projectId && _termActiveProjectId() === projectId;
  }
  function _termSessionMeta(name) {
    return (termSessions || []).find(s => s && s.name === name) || null;
  }
  function _termSessionBelongsTo(projectId, name) {
    const meta = _termSessionMeta(name);
    return !!meta && (!meta.project_id || meta.project_id === projectId);
  }
  function _termCanAttach(projectId, name) {
    return _termIsScopeActive(projectId) && _termSessionBelongsTo(projectId, name);
  }
  function _termAttachRequestIsCurrent(seq, projectId, name) {
    return seq === termAttachRequestSeq && _termCanAttach(projectId, name);
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
      if (!termCurrentSession || !termCurrentProjectId) return;
      try { xterm && xterm.focus && xterm.focus(); } catch {}
    }, 0);
  }

  // ─── Project tabs (Chrome-style) ───
  // State declarations are hoisted to the init block above (same TDZ reason
  // as the home view). Functions here; state is in the hoisted block so
  // projTabsRefresh() can be called during init without tripping the
  // temporal dead zone on `projTabsHot` / `projTabsRefreshTimer`.

  async function projTabsRefresh() {
    try {
      const [sessionsRes, all] = await Promise.all([
        fetch('/api/term/sessions'),
        fetchRepos(),
      ]);
      const sessionRows = sessionsRes.ok ? await sessionsRes.json() : [];
      projTabsHot = (Array.isArray(sessionRows) ? sessionRows : [])
        .filter(row => row && row.project_id && !String(row.project_id).startsWith('__'))
        .map(row => ({project_id: row.project_id, workspace: row.workspace || ''}));
      projTabsAll = (Array.isArray(all) ? all : []).filter(p => p.is_project);
    } catch { /* leave stale state; next tick will retry */ }
    projTabsRender();
  }

  function projTabsRender() {
    const el = document.getElementById('projectTabs');
    if (!el) return;
    const selfActive = document.body.classList.contains('self-active');
    const workspaceActive = document.body.classList.contains('workspace-active');
    const activeProjectPath = document.body.classList.contains('project-active') && currentProject
      ? currentProject.path : null;
    const activeWorkspaceId = workspaceActive && _workspaceCurrent
      ? _workspaceCurrent.id : null;

    const workspaceIds = new Set(_openWorkspaceIds());
    if (activeWorkspaceId) workspaceIds.add(activeWorkspaceId);
    const currentProjectWorkspace = _projectWorkspaceId(currentProject);
    if (currentProjectWorkspace) workspaceIds.add(currentProjectWorkspace);

    const projectTabs = [];
    const seenPaths = new Set();
    const addProject = (project, hot = false) => {
      if (!project || !project.path || seenPaths.has(project.path)) return;
      seenPaths.add(project.path);
      projectTabs.push({project, hot});
    };
    for (const hot of projTabsHot || []) {
      addProject((projTabsAll || []).find(project =>
        project.name === hot.project_id && (!hot.workspace || project.workspace === hot.workspace)
      ), true);
    }
    if (activeProjectPath) addProject((projTabsAll || []).find(project => project.path === activeProjectPath));
    for (const path of projTabsOpenIds()) addProject((projTabsAll || []).find(project => project.path === path));

    const workspaceTabs = Array.from(workspaceIds)
      .map(_workspaceById)
      .filter(Boolean)
      .sort((a, b) => String(a.name || a.id).localeCompare(String(b.name || b.id)));

    let html = LAB_IS_ADMIN ? `
      <div class="proj-tab self-tab${selfActive ? ' active' : ''}" data-kind="productivity" data-key="${SELF_PROJECT_ID}" role="tab" title="Framework home">
        <span class="label">&#x1F3E0; Home</span>
      </div>` : '';
    html += workspaceTabs.map(ws => {
      const active = activeWorkspaceId === ws.id ? ' active' : '';
      const color = projTabsEsc(ws.color || '#8b949e');
      return `
        <div class="proj-tab workspace-tab workspace-owned${active}" style="--workspace-color:${color}" data-kind="workspace" data-key="${projTabsEsc(ws.id)}" role="tab" title="Workspace · ${projTabsEsc(ws.path || '')}">
          <span class="workspace-mark"></span>
          <span class="label">${projTabsEsc(ws.name || ws.id)}</span>
          <button class="x" title="Close workspace tab" data-x="${projTabsEsc(ws.id)}">&times;</button>
        </div>`;
    }).join('');
    html += projectTabs.map(({project, hot}) => {
      const ws = _workspaceForProject(project);
      const active = activeProjectPath === project.path ? ' active' : '';
      const color = projTabsEsc((ws && ws.color) || '#8b949e');
      const blocked = tabBlocked.pid === project.name ? ' blocked' : '';
      return `
        <div class="proj-tab workspace-owned${active}${blocked}" style="--workspace-color:${color}" data-kind="project" data-key="${projTabsEsc(project.path)}" data-pid="${projTabsEsc(project.name)}" data-workspace="${projTabsEsc(project.workspace || '')}" role="tab" title="${projTabsEsc((ws && (ws.name || ws.id)) || '')} · ${projTabsEsc(project.path)}">
          <span class="workspace-mark"></span>
          <span class="label">${projTabsEsc(_projectDisplayName(project))}</span>
          <button class="x" title="Close project tab and its terminal sessions" data-x="${projTabsEsc(project.path)}">&times;</button>
        </div>`;
    }).join('');
    el.innerHTML = html;

    el.querySelectorAll('.proj-tab').forEach(node => {
      node.addEventListener('click', (e) => {
        if (e.target.closest('.x')) return;  // X handled separately
        const kind = node.getAttribute('data-kind');
        const key = node.getAttribute('data-key');
        if (kind === 'productivity') { goToProductivity(); return; }
        if (kind === 'workspace') { goToWorkspace(key); return; }
        if (kind === 'project' && key) goToProject(key);
      });
    });
    el.querySelectorAll('.proj-tab .x').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const tab = btn.closest('.proj-tab');
        projTabsClose({
          key: btn.getAttribute('data-x'),
          kind: tab && tab.getAttribute('data-kind'),
          projectId: tab && tab.getAttribute('data-pid'),
          workspace: tab && tab.getAttribute('data-workspace'),
        });
      });
    });
  }

  function projTabsWireDnD(container) {
    container.querySelectorAll('.proj-tab').forEach(tab => {
      tab.addEventListener('dragstart', (e) => {
        projTabsDragPid = tab.getAttribute('data-pid');
        tab.classList.add('dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', projTabsDragPid);
        }
      });
      tab.addEventListener('dragend', () => {
        tab.classList.remove('dragging');
        container.querySelectorAll('.proj-tab.drop-before, .proj-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        projTabsDragPid = null;
      });
      tab.addEventListener('dragover', (e) => {
        if (!projTabsDragPid) return;
        e.preventDefault();  // allow drop
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        container.querySelectorAll('.proj-tab.drop-before, .proj-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        const rect = tab.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        tab.classList.add(before ? 'drop-before' : 'drop-after');
      });
      tab.addEventListener('drop', async (e) => {
        e.preventDefault();
        const src = projTabsDragPid;
        const dst = tab.getAttribute('data-pid');
        container.querySelectorAll('.proj-tab.drop-before, .proj-tab.drop-after')
          .forEach(t => t.classList.remove('drop-before', 'drop-after'));
        if (!src || !dst || src === dst) return;
        const rect = tab.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        await projTabsReorder(src, dst, before);
      });
    });
  }

  async function projTabsReorder(srcPid, dstPid, placeBefore) {
    // Compute the NEW order from the current DOM (authoritative — respects
    // the saved-order + append-new logic that projTabsRender runs).
    const current = Array.from(document.querySelectorAll('#projectTabs .proj-tab'))
      .map(n => n.getAttribute('data-pid'));
    const srcIdx = current.indexOf(srcPid);
    if (srcIdx === -1) return;
    current.splice(srcIdx, 1);
    let dstIdx = current.indexOf(dstPid);
    if (dstIdx === -1) dstIdx = current.length;
    if (!placeBefore) dstIdx += 1;
    current.splice(dstIdx, 0, srcPid);

    projTabsOrder = current;
    projTabsRender();
    // Persist server-side so the order survives reloads + other browsers.
    try {
      await fetch('/api/ui/tab-order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({order: current}),
      });
    } catch (e) { /* best-effort; local state already updated */ }
  }

  function projTabsEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  async function projTabsClose({key, kind, projectId, workspace}) {
    if (!key || kind === 'productivity') return;
    if (kind === 'workspace') {
      _setWorkspaceTabOpen(key, false);
      const wasActive = document.body.classList.contains('workspace-active')
        && _workspaceCurrent && _workspaceCurrent.id === key;
      if (wasActive) goToProductivity(); else projTabsRender();
      return;
    }
    if (kind !== 'project' || !projectId) return;
    if (!confirm(`Close "${projectId}"? This also closes its terminal sessions; saved agent conversations can resume when reopened.`)) return;
    try {
      const suffix = workspace ? '?workspace=' + encodeURIComponent(workspace) : '';
      await fetch('/api/term/sessions/project/' + encodeURIComponent(projectId) + suffix, {method: 'DELETE'});
    } catch (e) { /* best effort */ }
    await projTabsSetOpen(key, false);
    const wasActive = currentProject && currentProject.path === key;
    await projTabsRefresh();
    if (wasActive) goToProductivity();
  }

  function projTabsTogglePicker(ev) {
    if (ev) ev.stopPropagation();
    const picker = document.getElementById('projTabsPicker');
    if (!picker) return;
    const opening = !picker.classList.contains('open');
    picker.classList.toggle('open', opening);
    if (opening) {
      projTabsRenderPicker();
      const off = (e) => {
        if (!picker.contains(e.target) && e.target.id !== 'projTabsPlusBtn') {
          picker.classList.remove('open');
          document.removeEventListener('click', off);
        }
      };
      setTimeout(() => document.addEventListener('click', off), 0);
    }
  }

  function projTabsRenderPicker() {
    const picker = document.getElementById('projTabsPicker');
    if (!picker) return;
    const openWorkspaces = new Set(_openWorkspaceIds());
    const openProjects = new Set(projTabsOpenIds());
    const workspaceRows = (workspaceCatalog || [])
      .filter(ws => !openWorkspaces.has(ws.id))
      .map(ws => `
        <div class="row" data-workspace="${projTabsEsc(ws.id)}">
          <span class="workspace-mark" style="--workspace-color:${projTabsEsc(ws.color || '#8b949e')}"></span>
          <span>${projTabsEsc(ws.name || ws.id)}</span>
          <span class="meta">workspace</span>
        </div>`).join('');
    const candidates = (projTabsAll || []).filter(project => !openProjects.has(project.path));
    if (!workspaceRows && candidates.length === 0) {
      picker.innerHTML = '<div class="empty">Everything is already open.</div>';
      return;
    }
    picker.innerHTML = workspaceRows + candidates.map(project => `
      <div class="row" data-path="${projTabsEsc(project.path)}">
        <span class="workspace-mark" style="--workspace-color:${projTabsEsc(project.workspace_color || '#8b949e')}"></span>
        <span>${projTabsEsc(_projectDisplayName(project))}</span>
        <span class="meta">${projTabsEsc(project.workspace_name || project.workspace || '')}</span>
      </div>`).join('');
    picker.querySelectorAll('.row').forEach(row => {
      row.addEventListener('click', () => {
        picker.classList.remove('open');
        const workspaceId = row.getAttribute('data-workspace');
        if (workspaceId) { goToWorkspace(workspaceId); return; }
        const path = row.getAttribute('data-path');
        if (path) goToProject(path);
      });
    });
  }

  function projTabsStartPolling() {
    if (projTabsRefreshTimer) return;
    projTabsRefreshTimer = setInterval(projTabsRefresh, 5000);
  }

  async function termOpenForProject(projectId) {
    // Show the panel and restore every session this project had.
    //
    // "Restore every session" means: compare live tmux sessions against the
    // saved list in project.json, and respawn any saved entry whose logical
    // name isn't currently live. For claude entries this POST path re-uses
    // the saved claude_session_id via --resume. This is the key to
    // ``claude-2`` (and friends) coming back after a tab-close → reopen.
    //
    // Per-user opt-out of both auto-respawn and first-time auto-spawn via
    // ``localStorage.labTermAutoSpawn = "0"``. Explicitly closing the last
    // terminal also disables only the first-time auto-spawn for this project
    // so a reload does not recreate a terminal the user just removed.
    if (!projectId) { termClose(); return; }
    if (!_termIsScopeActive(projectId)) return;
    document.body.classList.add('term-open');
    // Restore the user's last-known collapse state for this view
    // (default = visible for projects).
    _termApplyRememberedVisibility();

    // Warm switch: this project has been opened earlier in the browser
    // session, so we have its pill list in memory. Paint it instantly
    // and attach the cached session — no network wait, no respawn
    // detour. Background-refresh reconciles via termRefreshSessions
    // and the periodic poller; if a Claude died meanwhile its pill
    // shows up `dead` (click to retry). Avoids the multi-second
    // "resuming N session(s)…" wait that fired on every tab click.
    const sessionCacheKey = typeof _termSessionsKey === 'function'
      ? _termSessionsKey(projectId) : projectId;
    const isWarmSwitch = _termSessionsCache.has(sessionCacheKey);
    if (isWarmSwitch) {
      termSessions = _termSessionsCache.get(sessionCacheKey) || [];
      termRenderSessionList();
      if (termSessions.length > 0) {
        const pick = _termPickRestoreName(projectId);
        if (pick && _termHasOpenCachedPane(projectId, pick)) {
          termAttach(pick, projectId);
          termRefreshSessions(projectId);  // background reconcile, no await
        } else {
          console.info('[term] warm cache stale; reconciling before attach', projectId, pick);
          _termClientLog('info', 'terminal warm cache stale; reconciling before attach', {
            event_type: 'term.restore.stale_cache',
            target: projectId,
          });
          await _termRestoreSessionsForProject(projectId);
        }
      } else {
        termDetach();
        termShowEmpty();
        termSetStatus('idle', 'no session — click + New');
        termRefreshSessions(projectId);  // background reconcile, no await
      }
      termStartPeriodicRefresh();
      return;
    }

    // Cold open (first visit to this project this browser session). Full
    // restore path: pull saved sessions out of project.json and respawn
    // any that aren't live in tmux. This is the path that surfaces saved
    // Claude conversations after a browser reload.
    await _termRestoreSessionsForProject(projectId);
    // Keep the dropdown + current attachment honest when sessions change out
    // from under us (manual `tmux kill-session`, server restart, etc.).
    termStartPeriodicRefresh();
  }

  function _termHasOpenCachedPane(projectId, name) {
    if (typeof _termCache === 'undefined' || typeof _termCacheKey !== 'function') return false;
    const cached = _termCache.get(_termCacheKey(projectId, name));
    return _termCachedPaneIsFresh(cached);
  }

  async function _termTryWarmOpen(projectId) {
    const sessionCacheKey = typeof _termSessionsKey === 'function'
      ? _termSessionsKey(projectId) : projectId;
    if (!_termSessionsCache.has(sessionCacheKey)) return false;
    termSessions = _termSessionsCache.get(sessionCacheKey) || [];
    termRenderSessionList();
    if (termSessions.length > 0) {
      const pick = _termPickRestoreName(projectId);
      if (pick && _termHasOpenCachedPane(projectId, pick)) {
        termAttach(pick, projectId);
        _termRefreshSessionsForProjectId(projectId);  // background reconcile
      } else {
        console.info('[term] warm cache stale; reconciling before attach', projectId, pick);
        _termClientLog('info', 'terminal warm cache stale; reconciling before attach', {
          event_type: 'term.restore.stale_cache',
          target: projectId,
        });
        await _termRestoreSessionsForProject(projectId);
      }
    } else {
      termDetach();
      termShowEmpty();
      termSetStatus('idle', 'no session — click + New');
      _termRefreshSessionsForProjectId(projectId);  // background reconcile
    }
    return true;
  }

  async function _termRefreshSessionsForProjectId(projectId) {
    // Returns true when the sessions fetch succeeded (server reachable);
    // callers use this to tell "session confirmed gone" apart from
    // "couldn't ask".
    if (projectId === '__cerebro__' || projectId === '__self__' || projectId === '__logs__') {
      return await termRefreshSessionsByProjectId(projectId);
    }
    return await termRefreshSessions(projectId);
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

  async function _termRestoreSessionsForProject(projectId) {
    const workspaceId = typeof _termWorkspaceId === 'function' ? _termWorkspaceId() : null;
    const workspaceQuery = typeof _workspaceQuery === 'function' ? _workspaceQuery(workspaceId) : '';
    await _termRefreshSessionsForProjectId(projectId);
    if (!_termIsScopeActive(projectId)) return;

    let saved = [];
    try {
      const r = await fetch('/api/term/sessions/saved?project_id=' + encodeURIComponent(projectId) + workspaceQuery);
      if (r.ok) saved = await r.json();
    } catch (e) {
      _termClientLog('warning', 'terminal saved-session fetch failed', {
        event_type: 'term.restore.saved_fetch_failed',
        target: projectId,
      });
    }
    if (!_termIsScopeActive(projectId)) return;

    const liveLogicalNames = new Set(termSessions.map(s => s.logical_name).filter(Boolean));
    const toRestore = saved.filter(s => s && s.name && !liveLogicalNames.has(s.name));
    const globalAutoSpawn = localStorage.getItem('labTermAutoSpawn') !== '0';
    const projectAutoSpawn = globalAutoSpawn && await termAutoSpawnEnabled(projectId, workspaceId);
    if (!_termIsScopeActive(projectId)) return;

    if (toRestore.length > 0 && globalAutoSpawn) {
      termSetStatus('idle', `resuming ${toRestore.length} session(s)…`);
      _termClientLog('info', 'terminal restoring saved sessions', {
        event_type: 'term.restore.saved',
        target: projectId,
      });
      await Promise.all(toRestore.map(s => fetch('/api/term/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: projectId,
          workspace: workspaceId,
          kind: s.kind || 'claude',
          agent: s.agent,
          name: s.name,
          // No explicit `auto`: the workspace's per-agent autopilot
          // setting decides (an explicit value here would override it).
        }),
      }).catch(() => null)));
      await _termRefreshSessionsForProjectId(projectId);
      if (!_termIsScopeActive(projectId)) return;
    }

    if (termSessions.length > 0) {
      const pick = _termPickRestoreName(projectId);
      if (pick) termAttach(pick, projectId);
      return;
    }

    termDetach();
    termShowEmpty();
    if (projectAutoSpawn) {
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
      // Framework views win over a stale currentProject from the previous
      // tab. Otherwise, use the loaded project or workspace id.
      let pid = null;
      if (document.body.classList.contains('cerebro-active')) pid = CEREBRO_PROJECT_ID;
      else if (document.body.classList.contains('self-active')) pid = SELF_PROJECT_ID;
      else if (currentProject && currentProject.is_project) pid = currentProject.name;
      if (!pid) return;
      const prev = termCurrentSession;
      const prevPid = termCurrentProjectId;
      const ok = await _termRefreshSessionsForProjectId(pid);
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
    const pid = _termActiveProjectId();
    if (!pid) return;
    // User asked to retry — clear any dead/backoff state so termAttach
    // will make a fresh attempt instead of bouncing off _termMarkDead.
    termDeadSessions.clear();
    for (const k of Object.keys(termReconnectAttempts)) delete termReconnectAttempts[k];
    for (const k of Object.keys(_termAutoRestoreAt)) delete _termAutoRestoreAt[k];
    await _termRefreshSessionsForProjectId(pid);
    if (!_termIsScopeActive(pid)) return;
    if (termSessions.length > 0) termAttach(termSessions[0].name, pid);
    else await _termRestoreSessionsForProject(pid);
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
  // is namespaced by the active project, workspace, or framework view.
  // (`_TERM_VIS_KEY_PREFIX` is declared higher up to avoid a TDZ when
  // these helpers run during the initial `?view=…` URL dispatch.)
  function _termVisibilityKey() {
    if (document.body.classList.contains('cerebro-active')) return _TERM_VIS_KEY_PREFIX + 'cerebro';
    if (document.body.classList.contains('self-active')) return _TERM_VIS_KEY_PREFIX + 'self';
    if (document.body.classList.contains('workspace-active')) return _TERM_VIS_KEY_PREFIX + 'workspace';
    if (currentProject && currentProject.is_project) return _TERM_VIS_KEY_PREFIX + 'project:' + currentProject.name;
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
    // view init (project / self / cerebro) lands here, so this is the one
    // place that restores the sidebar's per-view collapse state + width.
    _sidebarApplyForView();
  }

  // ─── Files-sidebar collapse + per-view width ───
  // Same UX as the terminal toggle, mirrored on the left edge. Both the
  // collapsed flag and the dragged width are namespaced by view (project
  // id / self / cerebro), so hiding or resizing the sidebar in one project
  // never leaks into another. The un-suffixed legacy key `labSidebarPct`
  // remains as the boot-time default for views without their own entry.
  // (The two key-prefix consts are hoisted next to _TERM_VIS_KEY_PREFIX —
  // same initial-dispatch TDZ rule.)
  function _sidebarViewSuffix() {
    if (document.body.classList.contains('cerebro-active')) return 'cerebro';
    if (document.body.classList.contains('self-active')) return 'self';
    if (document.body.classList.contains('workspace-active')) return 'workspace';
    if (currentProject && currentProject.is_project) {
      // Server (proxy) views get their own namespace so they can default
      // to a collapsed sidebar — the embedded app wants the full left +
      // center width — without touching the project's normal preference.
      if (typeof _projDocPath === 'string' && _projDocPath.startsWith('__proxy__/')) {
        return 'proxy:' + currentProject.name + ':' + _projDocPath.slice('__proxy__/'.length);
      }
      return 'project:' + currentProject.name;
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
    // saved under the active view's key ONLY (per-project by request) —
    // the legacy global key is read as a fallback default but never
    // written anymore, so resizing project A can't restyle project B.
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

  async function termRefreshSessions(projectId) {
    projectId = projectId || (currentProject && currentProject.is_project ? currentProject.name : null);
    if (!projectId) return;
    const workspaceId = _termWorkspaceId();
    const sessionCacheKey = _termSessionsKey(projectId, workspaceId);
    let fresh = [];
    let ok = false;
    try {
      const r = await fetch('/api/term/sessions?project_id=' + encodeURIComponent(projectId) + _workspaceQuery(workspaceId));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(sessionCacheKey, fresh);
    // Stale-response guard. termOpenForProject's warm-switch path fires
    // this refresh without awaiting, so by the time the response lands
    // the user may already be on a different tab. Cache the result but
    // don't touch globals or repaint — the active view's own refresh
    // will handle its own pills.
    if (projectId !== _termActiveProjectId() || workspaceId !== _termWorkspaceId()) return ok;
    // On a failed fetch (server restarting, network blip) fall back to the
    // last successful list for this project instead of wiping the pills —
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

  let _termDragLogical = null;    // logical_name of pill being dragged
  let _termReorderPending = false; // suspends periodic refresh right after a reorder
  let _termGroupMenuOutside = null;

  function _termGroupScopeKey() {
    return _termSessionsKey(_termActiveProjectId(), _termWorkspaceId());
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
    return {groups, order, membership};
  }

  function _termReadGroupState() {
    try {
      const all = JSON.parse(localStorage.getItem(_TERM_GROUPS_KEY) || '{}');
      return _termNormalizeGroupState(all && all[_termGroupScopeKey()]);
    } catch { return {groups: [], order: [], membership: {}}; }
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

  function termCreateDivider(sessionName = termCurrentSession) {
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
    order.splice(activeIndex >= 0 ? activeIndex : order.length, 0, `g:${id}`);
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
    menu.innerHTML = html;
    menu.hidden = false;
    menu.querySelectorAll('[data-action]').forEach(button => {
      button.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        onAction(button.getAttribute('data-action'), button);
      });
    });
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

  function _termSessionDisplay(s) {
    return (s && (s.label || s.logical_name || s.name)) || '';
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

  function _termSessionTitle(s, statusTitle) {
    const parts = [];
    const display = _termSessionDisplay(s);
    if (display) parts.push(display);
    if (s && s.summary) parts.push(s.summary);
    if (s && s.name) parts.push(s.name);
    if (statusTitle) parts.push(statusTitle);
    parts.push('Double-click to rename');
    return parts.join('\n');
  }

  async function termRenameSession(name) {
    const session = _termSessionMeta(name);
    if (!session) return;
    const projectId = _termActiveProjectId();
    const workspaceId = _termWorkspaceId();
    const logical = session.logical_name || '';
    if (!projectId || !logical) return;
    const current = session.label || logical;
    const nextRaw = prompt('Rename terminal tab', current);
    if (nextRaw === null) return;
    const next = nextRaw.trim();
    try {
      const r = await fetch('/api/term/sessions/metadata', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: projectId,
          workspace: workspaceId,
          name: logical,
          label: next || null,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || r.statusText || 'rename failed');
      if (projectId !== _termActiveProjectId() || workspaceId !== _termWorkspaceId()) return;
      const updated = body.session || {};
      termSessions = (termSessions || []).map(s =>
        s.name === name ? {...s, label: updated.label || null, summary: updated.summary || s.summary} : s
      );
      _termSessionsCache.set(_termSessionsKey(projectId, workspaceId), termSessions);
      termRenderSessionList();
      _termClientLog('info', 'terminal tab renamed', {
        event_type: 'term.session.rename',
        target: projectId,
      });
    } catch (e) {
      console.warn('[term] rename failed', e);
      termSetStatus('err', 'rename failed');
      _termClientLog('warning', 'terminal tab rename failed: ' + (e && e.message || e), {
        event_type: 'term.session.rename_failed',
        target: projectId,
      });
    }
  }

  function termRenameCurrent() {
    if (termCurrentSession) termRenameSession(termCurrentSession);
  }

  function _termRenderActiveSessionHeader() {
    const el = document.getElementById('termActiveSession');
    if (!el) return;
    const session = (termSessions || []).find(s =>
      s.name === termCurrentSession && _termActiveProjectId() === termCurrentProjectId
    );
    if (!session) {
      el.innerHTML = '';
      el.removeAttribute('title');
      el.className = 'term-active-session';
      return;
    }
    const display = _termSessionDisplay(session);
    const visual = _termSessionVisual(session);
    el.className = `term-active-session on ${visual.kind}`;
    el.title = _termSessionTitle(session, '');
    el.innerHTML = `<span aria-hidden="true">${visual.icon}</span><span class="name">${termSessEsc(display)}</span><span class="agent">${termSessEsc(visual.badge)}</span>`;
  }

  function _termSessionPillHtml(s, index) {
    const display = _termSessionDisplay(s);
    // Compact/full visibility is CSS-controlled so switching detail never
    // rebuilds or reconnects a terminal. The active header always carries
    // the complete identity, even in compact mode.
    const visual = _termSessionVisual(s);
    const active = (s.name === termCurrentSession && _termActiveProjectId() === termCurrentProjectId) ? ' active' : '';
    const recentMeta = _termSessionRecentMeta(s);
    const recent = recentMeta ? ' recent' : '';
    const logical = s.logical_name || '';
    const dead = termDeadSessions.has(s.name) ? ' dead' : '';
    const statusTitle = dead ? 'Session unreachable — click to retry' : '';
    const recentTitle = recentMeta ? `Recently active — ${recentMeta.label} · window ${_termRecentWindowLabel()}` : '';
    const ariaLabel = `${display} · ${visual.badge}`;
    return `<span class="sess ${visual.kind}${active}${recent}${dead}" role="tab" aria-label="${termSessEsc(ariaLabel)}" aria-selected="${active ? 'true' : 'false'}" tabindex="${active ? '0' : '-1'}" draggable="true" data-order-token="${termSessEsc(`s:${logical}`)}" data-name="${termSessEsc(s.name)}" data-logical="${termSessEsc(logical)}" title="${termSessEsc(_termSessionTitle(s, [statusTitle, recentTitle].filter(Boolean).join(' · ')))}">
      <span class="sess-icon" aria-hidden="true">${visual.icon}</span>
      <span class="sess-order" aria-hidden="true">${index + 1}</span>
      <span class="sess-label${s.label ? ' custom' : ''}">${termSessEsc(display)}</span>
      <span class="k">${termSessEsc(visual.badge)}</span>
    </span>`;
  }

  function termRenderSessionList() {
    const el = document.getElementById('termSessionList');
    if (!el) return;
    _termRenderActiveSessionHeader();
    if (!termSessions || termSessions.length === 0) {
      el.innerHTML = '';
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
        <div class="term-divider-tabs">${rows.map(row => _termSessionPillHtml(row.session, row.index)).join('')}</div>
      </div>`;
      currentDivider = null;
      currentRows = [];
    };
    order.forEach(token => {
      if (token.startsWith('g:')) {
        flushDivider();
        currentDivider = groupsById.get(token.slice(2)) || null;
        return;
      }
      const row = sessionsByLogical.get(token.slice(2));
      if (!row) return;
      if (currentDivider) currentRows.push(row);
      else html += _termSessionPillHtml(row.session, row.index);
    });
    flushDivider();
    el.innerHTML = html;
    el.querySelectorAll('.sess').forEach(node => {
      node.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        termRenameSession(node.getAttribute('data-name'));
      });
      node.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        node.click();
      });
      node.addEventListener('click', () => {
        const name = node.getAttribute('data-name');
        if (!name) return;
        // Clicking a dead pill is an explicit retry: clear the block and
        // let termAttach try again. Refresh first so we don't hand it a
        // name tmux has already reaped.
        if (termDeadSessions.has(name)) {
          _termClearDead(name);
          delete _termAutoRestoreAt[name];  // explicit click resets the crash-loop guard
          const pid = _termActiveProjectId();
          (async () => {
            let refreshOk = false;
            if (pid) {
              try { refreshOk = !!(await _termRefreshSessionsForProjectId(pid)); } catch {}
            }
            if (termSessions.some(s => s.name === name)) termAttach(name, pid);
            else if (refreshOk && pid) _termSessionGone(name, pid);
            else termShowRecovery();
          })();
          return;
        }
        if (name !== termCurrentSession || _termActiveProjectId() !== termCurrentProjectId) {
          termAttach(name, _termActiveProjectId());
        }
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

  function termWireSessionDnD(container) {
    container.querySelectorAll('[data-order-token]').forEach(item => {
      item.addEventListener('dragstart', (e) => {
        _termDragLogical = item.getAttribute('data-order-token');
        item.classList.add('dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', _termDragLogical || '');
        }
      });
      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        container.querySelectorAll('[data-order-token].drop-before, [data-order-token].drop-after')
          .forEach(node => node.classList.remove('drop-before', 'drop-after'));
        _termDragLogical = null;
      });
      item.addEventListener('dragover', (e) => {
        const destination = item.getAttribute('data-order-token');
        if (!_termDragLogical || _termDragLogical === destination) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        container.querySelectorAll('[data-order-token].drop-before, [data-order-token].drop-after')
          .forEach(node => node.classList.remove('drop-before', 'drop-after'));
        const rect = item.getBoundingClientRect();
        const before = termSessionOrientation === 'horizontal'
          ? (e.clientX - rect.left) < rect.width / 2
          : (e.clientY - rect.top) < rect.height / 2;
        item.classList.add(before ? 'drop-before' : 'drop-after');
      });
      item.addEventListener('drop', async (e) => {
        e.preventDefault();
        const src = _termDragLogical;
        const dst = item.getAttribute('data-order-token');
        container.querySelectorAll('[data-order-token].drop-before, [data-order-token].drop-after')
          .forEach(node => node.classList.remove('drop-before', 'drop-after'));
        if (!src || !dst || src === dst) return;
        const rect = item.getBoundingClientRect();
        const before = termSessionOrientation === 'horizontal'
          ? (e.clientX - rect.left) < rect.width / 2
          : (e.clientY - rect.top) < rect.height / 2;
        await termReorderItems(src, dst, before);
      });
    });
  }

  async function termReorderItems(srcToken, dstToken, placeBefore) {
    const groupState = _termReadGroupState();
    const current = _termReconcileGroupOrder(groupState);
    const si = current.indexOf(srcToken);
    if (si === -1) return;
    current.splice(si, 1);
    let di = current.indexOf(dstToken);
    if (di === -1) di = current.length;
    if (!placeBefore) di += 1;
    current.splice(di, 0, srcToken);
    groupState.order = current;
    groupState.membership = {};
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

    // Persist server-side. Same project-id resolution used elsewhere.
    let projectId = null;
    if (document.body.classList.contains('cerebro-active')) projectId = CEREBRO_PROJECT_ID;
    else if (document.body.classList.contains('self-active')) projectId = SELF_PROJECT_ID;
    else if (currentProject && currentProject.is_project) projectId = currentProject.name;
    if (!projectId) return;
    // Suspend the periodic refresh while the POST is in flight: otherwise a
    // 5s-tick GET can race the POST and re-paint the old order, making the
    // reorder appear to "snap back".
    _termReorderPending = true;
    try {
      await fetch('/api/term/sessions/order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({project_id: projectId, workspace: _termWorkspaceId(), order: sessionOrder}),
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
    // Resolve workspace policy before revealing the menu so a disabled agent
    // never flashes as a clickable choice during the network round-trip.
    await termRefreshAgentAvail(el);
    el.classList.add('open');
    // One-shot outside-click listener to dismiss.
    const off = (e) => {
      if (!el.contains(e.target) && e.target.id !== 'termNewBtn') {
        el.classList.remove('open');
        document.removeEventListener('click', off);
      }
    };
    setTimeout(() => document.addEventListener('click', off), 0);
  }

  // Workspace policy removes disabled agents from every + New menu. Enabled
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
        loadWorkspaceAgentPolicy(),
      ]);
      _agentAvail = avail;
      policy = loadedPolicy;
    } catch { return; }
    const supported = new Set(policy.supported || []);
    picker.querySelectorAll('button[data-agent]').forEach(btn => {
      const a = btn.dataset.agent;
      btn.hidden = !supported.has(a);
      const ok = _agentAvail[a] !== false;
      btn.disabled = !ok;
      btn.style.opacity = ok ? '' : '0.45';
      const base = btn.textContent.replace(/ — not installed$/, '');
      btn.textContent = ok ? base : base + ' — not installed';
    });
  }

  function termCreateNew(kind, agent) {
    document.getElementById('termNewPicker')?.classList.remove('open');
    // Explicit + New: always spawn a fresh session (new name + new UUID).
    termSpawnSession(kind, { startFresh: true, agent });
  }

  async function termSpawnSession(kind, { startFresh = false, agent = null } = {}) {
    // Resolve the project id the new session belongs to. Framework views can
    // coexist with a stale currentProject from the previous tab, so check them first.
    let projectId = null;
    if (document.body.classList.contains('cerebro-active')) {
      projectId = CEREBRO_PROJECT_ID;
    } else if (document.body.classList.contains('self-active')) {
      projectId = SELF_PROJECT_ID;
    } else if (currentProject && currentProject.is_project) {
      projectId = currentProject.name;
    }
    if (!projectId) return;
    const workspaceId = _termWorkspaceId();

    termSetStatus('idle', kind === 'claude' ? `creating ${agent || 'claude'}…` : 'creating terminal…');
    try {
      const r = await fetch('/api/term/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: projectId,
          workspace: workspaceId,
          kind,
          agent,  // null → server resolves project override / global default
          start_fresh: startFresh,
          // No explicit `auto`: the workspace's per-agent autopilot
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
      await termSetAutoSpawnEnabled(projectId, true, workspaceId);
      if (projectId !== _termActiveProjectId() || workspaceId !== _termWorkspaceId()) return;
      // Brand-new session — clear any stale dead/backoff state for this
      // tmux name (possible if the user just recycled the same logical
      // name after the previous session died).
      _termClearDead(created.name);
      // Framework pseudo-projects use the project-id-aware helper.
      if (projectId === CEREBRO_PROJECT_ID || projectId === SELF_PROJECT_ID) {
        await termRefreshSessionsByProjectId(projectId);
      } else {
        await termRefreshSessions(projectId);
      }
      if (!_termIsScopeActive(projectId)) return;
      if (!termSessions.some(s => s && s.name === created.name)) {
        termSessions = [{...created, project_id: created.project_id || projectId}, ...termSessions];
        _termSessionsCache.set(_termSessionsKey(projectId, workspaceId), termSessions);
        termRenderSessionList();
      }
      termAttach(created.name, projectId);
    } catch (e) {
      alert('Failed to create session: ' + e.message);
      termSetStatus('err', 'create failed');
    }
  }

  async function termKillCurrent() {
    if (!termCurrentSession) return;
    const projectId = _termActiveProjectId();
    const workspaceId = typeof _termWorkspaceId === 'function' ? _termWorkspaceId() : null;
    if (!confirm('Close terminal session ' + termCurrentSession + '? It will stay closed after reload.')) return;
    const name = termCurrentSession;
    termDetach();  // full close (soft=false) — evicts cache entry
    try { await fetch('/api/term/sessions/' + encodeURIComponent(name) + '?purge=true', {method: 'DELETE'}); } catch {}
    await termSetAutoSpawnEnabled(projectId, false, workspaceId);
    if (projectId !== _termActiveProjectId()
        || (typeof _termWorkspaceId === 'function' && workspaceId !== _termWorkspaceId())) return;
    if (projectId === CEREBRO_PROJECT_ID || projectId === SELF_PROJECT_ID) await termRefreshSessionsByProjectId(projectId);
    else if (projectId) await termRefreshSessions(projectId);
    if (!_termIsScopeActive(projectId)) return;
    if (termSessions.length > 0) termAttach(termSessions[0].name, projectId);
    else { termShowEmpty(); termSetStatus('idle', 'no session — click + New'); }
  }

  async function termCopyAttachCmd() {
    // Prefer the currently-attached session; fall back to the first
    // session in the pill list so the button still works while disconnected.
    const name = termCurrentSession || (termSessions && termSessions[0] && termSessions[0].name) || null;
    if (!name) { termFlashCopy('no session'); return; }
    // `-r` = read-only client: sees every keystroke + output, can't inject
    // input. Good for riding along a running Claude session from iTerm
    // without risk of accidentally typing into it.
    const cmd = `tmux attach -t ${name} -r`;
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
    const projectId = _termActiveProjectId();
    if (!projectId) return;
    ev.preventDefault();
    ev.stopPropagation();
    termSetStatus('idle', 'saving pasted image...');
    try {
      const dataUrl = await _termReadFileAsDataUrl(file);
      const r = await fetch('/api/term/paste-image', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: projectId,
          workspace: _termWorkspaceId(),
          session_name: termCurrentSession,
          name: file.name || 'clipboard-image',
          mime: file.type || 'image/png',
          data: dataUrl,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || r.statusText || 'paste failed');
      const path = body.path || body.absolute_path;
      if (!path) throw new Error('paste response missing path');
      if (termWS && termWS.readyState === WebSocket.OPEN) {
        termWS.send(JSON.stringify({ type: 'input', data: path }));
      }
      termSetStatus('live', 'pasted image · ' + path);
      _termClientLog('info', 'terminal image paste saved', {
        event_type: 'term.paste_image',
        target: projectId,
      });
    } catch (e) {
      console.warn('[term] image paste failed', e);
      termSetStatus('err', 'image paste failed');
      _termClientLog('warning', 'terminal image paste failed: ' + (e && e.message || e), {
        event_type: 'term.paste_image_failed',
        target: projectId,
      });
    }
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
    el.innerHTML = `Click <b>+ New</b> to spawn a <code>tmux</code> session running <code>claude</code> in this project's folder. You can also attach from iTerm anytime with <code>tmux attach -t &lt;name&gt;</code>.`;
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
    const prevProjectId = termCurrentProjectId;
    // Record activity at the moment a tab is left. This matters when a tab
    // stayed selected longer than the recent window: its attach timestamp may
    // be old, but the user was actively looking at it until right now.
    if (typeof _termMarkRecent === 'function') _termMarkRecent(prevProjectId, prev);
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
      // overlay over an unrelated project. (We did try nulling all
      // listeners here — that turned out to break input echo on the
      // cache-hit re-attach because the WS was reused without rebinding.)
      const prevContainer = termContainer;
      _termSetPaneActive(prevContainer, false);
      if (prev && prevProjectId && termWS && termXterm && prevContainer) {
        // Release the GPU context while parked — hidden panes render fine
        // (and cheaply) on the DOM renderer, and this keeps us well under
        // the browser's WebGL context cap no matter how many sessions are
        // cached. Re-enabled on the next attach.
        _termDisableWebgl(termXterm);
        if (prevProjectId) {
          _termCache.set(_termCacheKey(prevProjectId, prev), {
            projectId: prevProjectId,
            name: prev,
            xterm: termXterm,
            fitAddon: termFitAddon,
            ws: termWS,
            container: prevContainer,
            parkedAt: Date.now(),
          });
        }
        console.log('[term] parked', prev, 'project=', prevProjectId, 'ws.readyState=', termWS.readyState, 'cache size=', _termCache.size);
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
      if (prev) _termEvictCache(prev, prevProjectId);
    }
    termXterm = null;
    termFitAddon = null;
    termWS = null;
    termContainer = null;
    termCurrentSession = null;
    termCurrentProjectId = null;
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
  async function _termSessionGone(name, projectId) {
    if (!_termIsScopeActive(projectId)) return;
    const now = Date.now();
    if (now - (_termAutoRestoreAt[name] || 0) < TERM_AUTO_RESTORE_MIN_GAP_MS) {
      _termMarkDead(name, 'session keeps ending: ' + name, projectId);
      return;
    }
    _termAutoRestoreAt[name] = now;
    _termClientLog('info', 'terminal session gone — auto-restoring', {
      event_type: 'term.restore.auto',
      target: String(projectId) + '::' + String(name),
    });
    // Drop the dead pane's client state so restore attaches fresh.
    if (name === termCurrentSession && projectId === termCurrentProjectId) {
      if (termWS) { try { termWS.close(); } catch {} termWS = null; }
      termCurrentSession = null;
      termCurrentProjectId = null;
    }
    _termEvictCache(name, projectId);
    delete termReconnectAttempts[name];
    termSetStatus('idle', 'session ended — restoring…');
    await _termRestoreSessionsForProject(projectId);
  }

  // Endless capped-backoff reconnect after a WS drop. Waits the backoff,
  // refreshes the session list, then either re-attaches (session still
  // listed — including the "server unreachable, keep the last-known list"
  // case) or hands off to _termSessionGone once a successful refresh
  // confirms tmux no longer has the session. Deliberately no attempt cap:
  // transient outages (lab server restart, laptop sleep) heal on their
  // own, and the only terminal state is "confirmed gone".
  function _termScheduleReconnect(name, projectId, myWS) {
    const attempts = (termReconnectAttempts[name] || 0) + 1;
    termReconnectAttempts[name] = attempts;
    const delay = _termBackoffMs(attempts);
    termSetStatus('err', 'disconnected — reconnecting in ' + Math.max(1, Math.round(delay / 1000)) + 's…');
    if (termReconnectTimer) clearTimeout(termReconnectTimer);
    termReconnectTimer = setTimeout(async () => {
      termReconnectTimer = null;
      if (termWS !== null && termWS !== myWS) return;
      if (!_termIsScopeActive(projectId)) return;
      if (termDeadSessions.has(name)) return;
      let refreshOk = false;
      try { refreshOk = !!(await _termRefreshSessionsForProjectId(projectId)); } catch {}
      if (termDeadSessions.has(name)) return;
      if (_termCanAttach(projectId, name)) {
        termWS = null;
        termCurrentSession = null;
        termCurrentProjectId = null;
        termAttach(name, projectId);
      } else if (!_termIsScopeActive(projectId)) {
        return;
      } else if (refreshOk) {
        _termSessionGone(name, projectId);
      } else {
        // Server unreachable and the name isn't even in the last-known
        // list — keep the loop alive until the server answers.
        _termScheduleReconnect(name, projectId, myWS);
      }
    }, delay);
  }

  // Mark a session dead: stop reconnecting, clear timers, render the
  // recovery overlay. Used as the crash-loop fallback (see
  // _termSessionGone) and from termAttach on an already-dead name.
  function _termMarkDead(name, statusText, projectId = termCurrentProjectId || _termActiveProjectId()) {
    console.log('[term] MARK DEAD', name, 'project=', projectId, statusText);
    termDeadSessions.add(name);
    delete termReconnectAttempts[name];
    if (termReconnectTimer) { clearTimeout(termReconnectTimer); termReconnectTimer = null; }
    if (name === termCurrentSession && projectId === termCurrentProjectId) {
      termCurrentSession = null;
      termCurrentProjectId = null;
    }
    _termEvictCache(name, projectId);  // drop xterm+WS for this dead session
    if (_termIsScopeActive(projectId)) {
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
  function _xtermFor(name, projectId = termCurrentProjectId || _termActiveProjectId()) {
    if (projectId === termCurrentProjectId && name === termCurrentSession && termXterm) return termXterm;
    const entry = _termCache.get(_termCacheKey(projectId, name));
    return entry && entry.xterm ? entry.xterm : null;
  }

  // Evict a session from the xterm cache: close its WS, dispose the
  // Terminal instance, and remove its container from the DOM.
  function _termEvictCache(name, projectId = termCurrentProjectId || _termActiveProjectId()) {
    const keys = [];
    if (projectId) {
      keys.push(_termCacheKey(projectId, name));
    } else {
      for (const [key, entry] of _termCache.entries()) {
        if (entry && entry.name === name) keys.push(key);
      }
    }
    console.log('[term] EVICT', name, 'project=', projectId, 'keys=', keys);
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

  async function termAttach(name, projectId = _termActiveProjectId()) {
    projectId = projectId || _termActiveProjectId();
    console.log('[term] termAttach', name, 'project=', projectId, 'currentSession=', termCurrentSession, 'currentProject=', termCurrentProjectId, 'cacheHas=', _termCache.has(_termCacheKey(projectId, name)));
    if (!name || !projectId) return;
    if (!_termCanAttach(projectId, name)) return;
    // A selection counts as recent immediately. termDetach records the
    // previous tab again when the user leaves it, keeping the timestamp true
    // to the end of a long viewing session.
    if (typeof _termMarkRecent === 'function') _termMarkRecent(projectId, name);
    const attachRequestSeq = ++termAttachRequestSeq;
    if (name === termCurrentSession && projectId === termCurrentProjectId && termWS && termWS.readyState === WebSocket.OPEN) {
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
    if (!_termAttachRequestIsCurrent(attachRequestSeq, projectId, name)) return;

    // Park the current session: hide its container, stash refs in cache.
    termDetach(true);
    termUserDetached = false;  // fresh attach — future drops should trigger recovery
    termCurrentSession = name;
    termCurrentProjectId = projectId;
    // Persist the selection so a full page reload (project-tab navigation)
    // can restore the same pill instead of snapping back to "claude".
    const _attachMeta = (termSessions || []).find(s => s.name === name);
    if (_attachMeta && _attachMeta.logical_name) {
      _termRememberLast(projectId, _attachMeta.logical_name);
    }
    console.log('[term] after soft detach, cache keys=', Array.from(_termCache.keys()));
    // Hide the empty/recovery overlay if visible.
    const _emptyEl = document.getElementById('termEmpty');
    if (_emptyEl) _emptyEl.style.display = 'none';

    const scopeKey = _termCacheKey(projectId, name);
    let cached = _termCache.get(scopeKey);
    if (cached && cached.ws && cached.ws.readyState === WebSocket.OPEN && !_termCachedPaneIsFresh(cached)) {
      console.info('[term] evicting aged parked pane before attach', name, projectId);
      _termEvictCache(name, projectId);
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
      if (termCurrentSession !== name || termCurrentProjectId !== projectId) return null;
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
          if (termCurrentSession !== name || termCurrentProjectId !== projectId || termUserDetached) return;
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
        return termWS !== myWS || termCurrentSession !== name || termCurrentProjectId !== projectId;
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
        // project tab (full page reload → cache empty → cache miss) and
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
          const xt = _xtermFor(name, projectId);
          if (xt) xt.write(_termStripModes(msg.data));
        } else if (msg.type === 'exit') {
          // If this WS is parked (we're viewing a different session /
          // project), don't surface the exit. The user has no UI for
          // this pane right now, and the next attach will discover
          // the dead socket via cached.ws.readyState !== OPEN and
          // reconnect through _openWS.
          if (name !== termCurrentSession || projectId !== termCurrentProjectId) return;
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
            const pid = _termActiveProjectId();
            (async () => {
              let refreshOk = false;
              if (pid) {
                try { refreshOk = !!(await _termRefreshSessionsForProjectId(pid)); } catch {}
              }
              if (_termCanAttach(projectId, name)) {
                // tmux still has it — the "no-session" was stale.
                // Reconnect without showing the recovery overlay.
                termWS = null;
                termCurrentSession = null;
                termCurrentProjectId = null;
                termAttach(name, projectId);
              } else if (refreshOk && _termIsScopeActive(projectId)) {
                // Confirmed gone — respawn saved sessions and reattach
                // instead of asking the user what to do.
                _termSessionGone(name, projectId);
              } else if (_termIsScopeActive(projectId)) {
                _termMarkDead(name, 'session not found', projectId);
              }
            })();
          } else {
            termSetStatus('idle', 'detached — ' + (msg.reason || 'closed'));
          }
        }
      };
      myWS.onclose = (ev) => {
        console.log('[term] WS onclose name=', name, 'project=', projectId, 'currentSession=', termCurrentSession, 'currentProject=', termCurrentProjectId, 'userDetached=', termUserDetached, 'cacheHas=', _termCache.has(scopeKey), 'code=', ev.code);
        detachListeners();
        if (isStale()) return;
        if (termUserDetached || termCurrentSession !== name || termCurrentProjectId !== projectId) return;
        if (termDeadSessions.has(name)) return;
        _termScheduleReconnect(name, projectId, myWS);
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
      termCurrentProjectId = projectId;
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
      termCurrentProjectId = projectId;
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
      if (termCurrentSession !== name || termCurrentProjectId !== projectId) return;
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

  // Deep-link support: #/nb?path=projects/<id>/<rest>.ipynb
  // The fragment-style URL points at a notebook directly. We resolve the
  // owning project, plant the doc in last-opened state so the existing
  // `selectRepo → getLastProjectDoc → openProjectDoc` flow opens it, and
  // rewrite the URL to the canonical ?project=<abs> form for refreshes.
  let _nbHashProject = null;
  (function consumeNbHash() {
    const hash = location.hash || '';
    const m = hash.match(/^#\/nb\?(.*)$/);
    if (!m) return;
    const params = new URLSearchParams(m[1]);
    const rel = params.get('path') || '';
    const seg = rel.match(/^projects\/([^/]+)\/(.+\.ipynb)$/i);
    if (!seg) return;
    const projectId = seg[1];
    const docPath = seg[2];
    if (projectId === '.' || projectId === '..'
        || docPath.split('/').some((part) => part === '..')) return;
    // A cross-workspace project tab already carries its absolute project in
    // ?project=. Prefer that authoritative owner over the shell workspace;
    // otherwise a Local notebook opened while the SSD workspace is active is
    // remembered under the wrong project and silently falls back to read-only.
    const explicitProject = _normalizeAbsolutePath(urlProject);
    const projectSuffix = `/projects/${projectId}`;
    let absProject = explicitProject && explicitProject.endsWith(projectSuffix)
      ? explicitProject : null;
    if (!absProject) {
      const workspaceRoot = _normalizeAbsolutePath(WORKSPACE_ROOT);
      if (!workspaceRoot) return;
      const rootPrefix = workspaceRoot === '/' ? '/' : workspaceRoot + '/';
      absProject = rootPrefix + 'projects/' + projectId;
    }
    setLastProjectDoc(absProject, docPath);
    _nbHashProject = absProject;
    const url = new URL(location.href);
    url.hash = '';
    url.searchParams.set('project', absProject);
    history.replaceState(null, '', url);
  })();
  const _effectiveProject = urlProject || _nbHashProject;

  if (_effectiveProject) {
    const provisionalName = (_effectiveProject.replace(/\/+$/, '').split('/').pop() || 'Project');
    currentProject = {
      name: provisionalName,
      path: _effectiveProject,
      is_project: true,
      description: 'Opening project dashboard...',
      repos: [],
    };
    document.body.classList.remove('cerebro-active', 'self-active', 'workspace-active', 'has-diff-tabs');
    document.body.classList.add('project-active');
    document.getElementById('diffTabs').style.display = 'none';
    paintProjectShell();
    // Share the in-flight /api/repos promise with loadRepos +
    // projTabsRefresh instead of firing a third network call (all three
    // callers resolve to the same response on initial load).
    fetchRepos().then(projects => {
      projectsList = projects;
      const proj = projects.find(p => p.path === _effectiveProject);
      if (proj) {
        selectRepo(proj.path);
      }
    });
  } else if (urlRepo) {
    fetchRepos().then(projects => {
      projectsList = projects;
      const proj = projects.find(p => p.repos.some(r => r.path === urlRepo));
      if (proj) {
        selectRepo(proj.path);
        if (proj.repos.length > 1) {
          const targetRepo = proj.repos.find(r => r.path === urlRepo);
          if (targetRepo) selectProjectRepo(targetRepo.path);
        }
      }
    });
  } else if (urlView === 'cerebro' || urlView === 'productivity' || urlView === 'workspace' || urlView === 'code-search' || urlView === 'logs') {
    // These views handle their own initialization above.
  } else {
    // No explicit target means the framework-owned Productivity home.
    initSelf();
  }

  // Compatibility handler for cached markup that still calls goHome().
  function goHome(ev) {
    if (ev) ev.preventDefault();
    goToProductivity();
  }

  // ─── In-page navigation (project tabs + dashboard cards) ────────────────
  //
  // Project-tab clicks USED to do `window.location.href = '/?project=…'`
  // which is a full page reload — the entire JS scope (including
  // `_termCache`) was destroyed every time the user moved between projects,
  // and the brief blank-screen flash on every click was a real UX
  // annoyance. These helpers do the same logical navigation in-page via
  // history.pushState + view-class swap, mirroring the goHome pattern.
  //
  // Bonus: `_termCache` survives now, so returning to a project the user
  // recently visited is a cache HIT — the WS + xterm buffer come back
  // intact instead of the user seeing a fresh tmux re-attach replay.
  // Look for `[term] cache HIT` in DevTools to confirm on a return visit.

  // Park the previous view's state cleanly before swapping. Detaches the
  // active terminal session into _termCache (soft-park, NOT eviction) and
  // strips the mutually-exclusive body classes; the destination init will
  // assert its own.
  function _swapViewState() {
    if (typeof termDetach === 'function') termDetach(true);
    document.body.classList.remove(
      'cerebro-active', 'self-active', 'workspace-active',
      'project-active', 'has-diff-tabs',
    );
    currentProject = null;
    currentRepo = null;
    currentRepoInProject = null;
    const dt = document.getElementById('diffTabs');
    if (dt) dt.style.display = 'none';
  }

  // Navigate to a real project by absolute path. `replace` is true when
  // called from popstate (browser already updated URL — replaceState would
  // create a duplicate; do nothing).
  function goToProject(path, opts = {}) {
    if (!path) return;
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.set('project', path);
      url.searchParams.delete('repo');
      url.searchParams.delete('view');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('workspace');
      url.searchParams.delete('subview');
      history.pushState({nav: 'project', path}, '', url.pathname + url.search + url.hash);
    }
    const dispatch = () => {
      const proj = (projectsList || []).find(p => p.path === path);
      if (proj) selectRepo(proj.path);
    };
    if (projectsList && projectsList.length) {
      dispatch();
    } else {
      fetchRepos().then(projects => { projectsList = projects; dispatch(); });
    }
  }

  // Navigate to a project by its id (CLAUDE-style /p/<id> URLs in the DOM).
  // Translates to a path lookup and delegates to goToProject. Falls back
  // to the legacy server-side redirect if the project isn't in projectsList.
  function goToProjectById(pid, opts = {}) {
    if (!pid) return;
    const fromCache = (projectsList || []).find(p => p.name === pid);
    if (fromCache && fromCache.path) { goToProject(fromCache.path, opts); return; }
    fetchRepos().then(projects => {
      projectsList = projects;
      const proj = projects.find(p => p.name === pid);
      if (proj && proj.path) goToProject(proj.path, opts);
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

  // Renders any monorepo-relative "shared" file inline in the project doc
  // pane — used by Meta sidebar entries for `projects/CLAUDE.md`
  // and any file under the shared `.claude/`. For `.md` we use the same
  // marked.js client renderer the project doc pane uses (so styling
  // matches the rest of the UI); for `.json/.csv` we use the same
  // viewers Cerebro uses; for `.html` we get the rendered/code toggle.
  async function openSharedFile(path) {
    if (!currentProject) return;
    const content = document.getElementById('content');
    if (!content) return;
    // Highlight whichever Meta entry corresponds to this path. The CLAUDE.md
    // entry has a fixed label; other shared files match by trailing filename.
    const lastSeg = path.split('/').pop();
    document.querySelectorAll('.sidebar-file').forEach(el => el.classList.remove('active'));
    document.querySelectorAll('.sidebar-file').forEach(el => {
      const t = el.textContent.trim();
      if (t.endsWith(lastSeg) || (path.endsWith('projects/CLAUDE.md') && t.includes('CLAUDE.md (shared)'))) {
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
        // Reuse the same HTML toggle pattern as in-project HTML files —
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
          rendered = fmHtml + marked.parse(body);
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

      content.innerHTML = `<div class="project-content" style="padding:24px;max-width:900px">${header}${rendered}</div>`;
      if (isCsv) cerebroAttachCSVFilter();
      if (window.hljs) {
        content.querySelectorAll('pre code').forEach(el => { try { window.hljs.highlightElement(el); } catch {} });
      }
    } catch (e) {
      content.innerHTML = `<div class="no-repo"><p>Error: ${esc(e.message || e)}</p></div>`;
    }
  }

  // HTML render helper used by openSharedFile — mirrors _projectRenderHtml
  // but uses the cerebro asset/file endpoints and stays inside the given
  // host element rather than reaching for currentProject's path.
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
      // Same iframe re-mount guard as _projectRenderHtml — avoids a white
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

  // Populate both `.claude/` and `code/` placeholders in the Meta
  // section. Called after every sidebar render. The fid args are kept
  // for back-compat but we no longer use them — the placeholder host is
  // looked up via a stable data-attribute selector so that races
  // between sidebar re-renders and the (slow, ~1.4s) /api/cerebro/tree
  // fetch don't strand the "loading…" placeholder.
  //
  // Caches the response in `cerebroTreeData` so the second+ render in a
  // session paints synchronously with no network — the tree is reused
  // by the Cerebro view's `cerebroRefresh` for the same reason.
  function _populateSharedMetaPlaceholders(_claudeFid, _codeFid) {
    // Cache hit: paint immediately, then fire a background reconcile
    // so the next render also sees fresh data.
    if (cerebroTreeData && cerebroTreeData.length) {
      _renderMetaFromCerebroTree(cerebroTreeData);
      afterPageQuiet(() => _fetchCerebroTree({force: true}).then(t => {
        if (t && t.length) _renderMetaFromCerebroTree(t);
      }).catch(err => console.error('[populateSharedMeta] background:', err)), 1500);
      return;
    }
    afterPageQuiet(() => _fetchCerebroTree().then(t => {
      _renderMetaFromCerebroTree(t || []);
    }).catch(err => console.error('[populateSharedMeta] failed:', err)), 1500);
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

  function _renderMetaFromCerebroTree(tree) {
    const ts = tree || [];
    // Look up the host via the folder's stable data attributes — the
    // children container is its next DOM sibling. Survives sidebar
    // re-renders that mint new random fids each time.
    const claudeHost = document.querySelector(
      '.sidebar-folder[data-tree-scope="shared-claude"][data-tree-path=".claude"] + .sidebar-folder-children'
    );
    const codeHost = document.querySelector(
      '.sidebar-folder[data-tree-scope="shared-code"][data-tree-path="code"] + .sidebar-folder-children'
    );
    const agentsHost = document.querySelector(
      '.sidebar-folder[data-tree-scope="shared-agents"][data-tree-path=".agents"] + .sidebar-folder-children'
    );
    _renderSharedMetaPlaceholder({
      host: claudeHost,
      node: ts.find(n => n && n.name === '.claude'),
      basePath: '.claude',
      scope: 'shared-claude',
      labelPrefix: '.claude/',
    });
    _renderSharedMetaPlaceholder({
      host: agentsHost,
      node: ts.find(n => n && n.name === '.agents'),
      basePath: '.agents',
      scope: 'shared-agents',
      labelPrefix: '.agents/',
    });
    _renderSharedMetaPlaceholder({
      host: codeHost,
      node: ts.find(n => n && n.name === 'code'),
      basePath: 'code',
      scope: 'shared-code',
      labelPrefix: 'code/',
    });
  }

  function _renderSharedMetaPlaceholder({host, node, basePath, scope, labelPrefix}) {
    if (!host) return;
    if (!node || !node.children || !node.children.length) {
      host.innerHTML = `<div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">(empty)</div>`;
      return;
    }
    host.innerHTML = renderSharedClaudeTree(node.children, basePath, scope);
    host.querySelectorAll('a.sidebar-file').forEach(a => {
      const onclickAttr = a.getAttribute('onclick') || '';
      const m = onclickAttr.match(/openSharedFile\('([^']+)'\)/);
      if (m) a.title = m[1];
    });
    // Folder tooltips show the full cerebro-relative path. Folders and
    // their children-containers are DOM siblings, so we hop up by:
    // folder → its parent container → that container's
    // previousElementSibling (the enclosing folder), repeat.
    host.querySelectorAll('.sidebar-folder').forEach(d => {
      const parts = [];
      let cur = d;
      while (cur && cur !== host) {
        if (cur.classList && cur.classList.contains('sidebar-folder')) {
          const label = (cur.firstChild && cur.firstChild.nextSibling ? cur.firstChild.nextSibling.textContent : cur.textContent).trim();
          parts.unshift(label.replace(/\/$/, ''));
        }
        const parent = cur.parentElement;
        if (!parent || parent === host) break;
        cur = parent.previousElementSibling;
      }
      d.title = labelPrefix + parts.join('/') + '/';
    });
  }

  // Renders a shared subtree (fetched from /api/cerebro/tree) as a
  // collapsible folder structure in the Meta sidebar section. File
  // clicks call openSharedFile with the cerebro-relative path.
  //
  // `scope` controls expand-state namespacing in _treeIsOpen — pass
  // 'shared-claude' for the `.claude/` tree, 'shared-code' for the
  // `code/` tree, etc. State is keyed (scope, path), so distinct
  // scopes keep their open-folder sets separate.
  function renderSharedClaudeTree(nodes, basePath, scope = 'shared-claude') {
    let html = '';
    const dirs = nodes.filter(n => n.type === 'dir');
    const files = nodes.filter(n => n.type !== 'dir');
    dirs.forEach(d => {
      const fid = 'sf-' + Math.random().toString(36).substr(2, 6);
      const fullPath = basePath + '/' + d.name;
      const open = _treeIsOpen(scope, fullPath, false);
      const arrowCls = open ? ' open' : '';
      const childrenCls = open ? ' open' : '';
      html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(scope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">▶</span>${symlinkMarker(d)}${esc(d.name)}/</div>`;
      html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
      html += renderSharedClaudeTree(d.children || [], fullPath, scope);
      html += '</div>';
    });
    files.forEach(f => {
      const safePath = (basePath + '/' + f.name).replace(/'/g, "\\'");
      const icon = fileIconHtml(f.name, f);
      html += `<a class="sidebar-file${symlinkClass(f)}"${symlinkTitle(f)} onclick="openSharedFile('${safePath}')" style="opacity:.85"><span class="sidebar-fname">${icon}${esc(f.name)}</span></a>`;
    });
    return html;
  }

  async function goToCerebro(initialPath = '', opts = {}) {
    if (!LAB_IS_ADMIN) {
      const data = await fetchWorkspaceCatalog();
      const first = (data.workspaces || [])[0];
      if (first) goToWorkspace(first.id, opts);
      return;
    }
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
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
      const data = await fetchWorkspaceCatalog();
      const first = (data.workspaces || [])[0];
      if (first) goToWorkspace(first.id, opts);
      return;
    }
    _swapViewState();
    _contextSubView = 'overview';
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('workspace');
      url.searchParams.set('view', 'productivity');
      if (opts.subview) url.searchParams.set('subview', opts.subview);
      else url.searchParams.delete('subview');
      history.pushState({nav: 'productivity'}, '', url.pathname + url.search + url.hash);
    }
    initSelf();
    if (opts.subview === 'admin') selfShowAdmin();
    else if (opts.subview === 'code-search') showScopedCodeSearch();
  }

  function goToWorkspace(workspaceId, opts = {}) {
    // Backwards compatibility for the old goToWorkspace({replace:true}) form.
    if (workspaceId && typeof workspaceId === 'object') {
      opts = workspaceId;
      workspaceId = null;
    }
    workspaceId = workspaceId
      || _projectWorkspaceId(currentProject)
      || (_workspaceCurrent && _workspaceCurrent.id)
      || currentWorkspaceId;
    if (!workspaceId) return;
    _swapViewState();
    _contextSubView = 'overview';
    _setWorkspaceTabOpen(workspaceId, true);
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.delete('subview');
      url.searchParams.set('view', 'workspace');
      url.searchParams.set('workspace', workspaceId);
      history.pushState({nav: 'workspace', workspace: workspaceId}, '', url.pathname + url.search + url.hash);
    }
    initWorkspaceView(workspaceId);
  }

  // Compatibility entry points for old bookmarks and cached inline handlers.
  // The standalone surfaces are retired; both now land in Productivity.
  function goToLogs(opts = {}) {
    goToProductivity({replace: !!opts.replace, subview: 'admin'});
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
    const project = params.get('project');
    const repo = params.get('repo');
    const view = params.get('view');
    const cerebroPath = params.get('path') || '';
    if (project) {
      goToProject(project, {replace: true});
    } else if (view === 'cerebro') {
      goToCerebro(cerebroPath, {replace: true});
    } else if (view === 'productivity') {
      goToProductivity({replace: true, subview: params.get('subview') || null});
    } else if (view === 'workspace') {
      goToWorkspace(params.get('workspace') || currentWorkspaceId, {replace: true});
    } else if (view === 'code-search') {
      goToCodeSearch({replace: true});
    } else if (view === 'logs') {
      goToLogs({replace: true});
    } else if (repo) {
      _swapViewState();
      fetchRepos().then(projects => {
        projectsList = projects;
        const proj = projects.find(p => p.repos.some(r => r.path === repo));
        if (proj) selectRepo(proj.path);
      });
    } else {
      goToProductivity({replace: true});
    }
  });

  function escapeHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  // ─── Dashboard: Servers section ─────────────────────────────────────────
  // GET /api/servers → {"servers": [{project_id, workspace, path, port,
  // state: "running"|"starting"|"unhealthy"|"stopped", desired, healthy,
  // session_name, attach_command, session_created, restarts, has_stop,
  // health_url}]}. Rows come from every registered workspace, sorted
  // (workspace, project_id) — a project id can repeat across workspaces, so
  // every lookup/action below is keyed on the (workspace, project_id) pair,
  // never project_id alone. Start/stop/restart post to
  // /api/servers/{workspace}/{project_id}/{start|stop|restart}.

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
        ${dashKpiTileHtml('Terminal sessions', termRows.length)}
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
    const pid = row.project_id;
    const ws = row.workspace || '';
    const key = ws + '/' + pid;
    const pending = _dashServersPending.has(key);
    const cls = dashServerStateClass(row);
    const wsBadge = ws
      ? `<span class="ws-badge" title="workspace: ${escapeHtml(ws)}">${escapeHtml(ws)}</span>`
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
      ? `<button type="button" class="mini-btn" data-act="copy-attach" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}" data-attach="${escapeHtml(row.attach_command)}" title="Copy tmux attach command: ${escapeHtml(row.attach_command)}">⧉ Copy</button>`
      : '';
    const actionBtns = row.status === 'stopped'
      ? `<button type="button" class="mini-btn primary" data-act="start" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}" ${pending ? 'disabled' : ''}>Start</button>`
      : `<button type="button" class="mini-btn danger" data-act="stop" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}" ${pending ? 'disabled' : ''}>Stop</button>
         <button type="button" class="mini-btn" data-act="restart" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}" ${pending ? 'disabled' : ''}>Restart</button>`;
    const titleAttr = row.path ? ` title="${escapeHtml(row.path)}"` : '';
    return `
      <div class="srv-card srv-card-${cls}" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}"${titleAttr}>
        <div class="srv-card-body">
          <div class="srv-card-head">
            <span class="srv-name">${escapeHtml(pid)}</span>
            ${wsBadge}
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
      ? '<div class="srv-empty">No projects with a server Makefile (server-start target).</div>'
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
    const pid = btn.getAttribute('data-pid');
    const ws = btn.getAttribute('data-workspace') || '';
    if (act === 'copy-attach') {
      const cmd = btn.getAttribute('data-attach') || '';
      if (cmd) await _copyToClipboard(cmd, btn);
      return;
    }
    if (!pid || !['start', 'stop', 'restart'].includes(act)) return;
    const key = ws + '/' + pid;
    if (_dashServersPending.has(key)) return;
    _dashServersPending.add(key);
    _dashServersActionErr = null;
    // Optimistic chip flip on Start/Restart: the actual state lags behind
    // the spawned tmux session by a beat, and sitting on "stopped" until
    // the next poll reads as broken. Stop needs no such nudge — the card's
    // own "disabled" state already gives immediate feedback.
    if (act === 'start' || act === 'restart') {
      const row = (_dashServersRows || []).find(r => (r.workspace || '') === ws && r.project_id === pid);
      if (row) row.status = 'starting';
    }
    dashServersRender();  // disable the card's buttons immediately
    try {
      const url = '/api/servers/' + encodeURIComponent(ws) + '/' + encodeURIComponent(pid) + '/' + act;
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
  // {name, created, attached, windows, workspace} from tmux plus
  // {project_id, logical_name, kind, agent, cwd, created_at, label, summary,
  // attach_command} from the runtime registry. Grouped by (workspace,
  // project_id) — a project id can exist in two workspaces, so the group
  // key must carry both; workspace-root sessions carry project_id
  // "__self__" (SELF_PROJECT_ID) and are labeled "workspace". Sessions
  // whose project_id couldn't be resolved at all (pre-existing orphaned
  // tmux sessions from before a naming-scheme change) fall back to a single
  // "(unassigned)" group with no "Close all" button, since there's no
  // project id (or workspace) to scope that call to.

  function dashFmtAgo(unixSeconds) {
    if (!unixSeconds) return null;
    const diff = Math.max(0, Math.floor(Date.now() / 1000) - unixSeconds);
    if (diff < 60) return diff + 's ago';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }

  function dashTermGroupKey(s) {
    if (!s.project_id) return '__unknown__';
    return (s.workspace || '') + '/' + s.project_id;
  }

  function dashTermGroupLabel(pid) {
    if (pid === SELF_PROJECT_ID) return 'workspace';
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
    const pid = first.project_id || '__unknown__';
    const ws = first.workspace || '';
    const label = dashTermGroupLabel(pid);
    const wsBadge = (key !== '__unknown__' && ws)
      ? `<span class="ws-badge" title="workspace: ${escapeHtml(ws)}">${escapeHtml(ws)}</span>`
      : '';
    const pending = _dashTermsPending.has('group:' + key);
    const closeAllBtn = key === '__unknown__'
      ? ''
      : `<button type="button" class="mini-btn danger" data-act="term-close-all" data-pid="${escapeHtml(pid)}" data-workspace="${escapeHtml(ws)}" data-key="${escapeHtml(key)}" ${pending ? 'disabled' : ''}>Close all</button>`;
    return `
      <div class="term-card">
        <div class="term-card-head">
          <span class="term-card-label">${escapeHtml(label)}</span>
          ${wsBadge}
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
      } catch (err) { /* best-effort, matches projTabsClose/termKillCurrent */ }
      _dashTermsPending.delete(name);
      await dashTermsRefresh();
      if (typeof projTabsRefresh === 'function') projTabsRefresh();
    } else if (act === 'term-close-all') {
      const pid = btn.getAttribute('data-pid');
      const ws = btn.getAttribute('data-workspace') || '';
      const key = btn.getAttribute('data-key') || (ws + '/' + pid);
      if (!pid || _dashTermsPending.has('group:' + key)) return;
      const sessions = (_dashTermsRows || []).filter(s => dashTermGroupKey(s) === key);
      const label = dashTermGroupLabel(pid);
      if (!confirm(`Close all ${sessions.length} terminal sessions for ${label}? This kills their tmux sessions.`)) return;
      _dashTermsPending.add('group:' + key);
      dashTermsRender();
      try {
        await fetch('/api/term/sessions/project/' + encodeURIComponent(pid) + '?workspace=' + encodeURIComponent(ws), {method: 'DELETE'});
      } catch (err) { /* best-effort */ }
      _dashTermsPending.delete('group:' + key);
      await dashTermsRefresh();
      if (typeof projTabsRefresh === 'function') projTabsRefresh();
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

  // ─── Project server bar (below top tabs, above diff tabs) ───
  // Deliberately narrow: project planning metadata belongs in project files,
  // so this chrome only exposes the local-server configuration.

  async function refreshAttrsBar() {
    const bar = document.getElementById('projectAttrsBar');
    if (!bar) return;
    if (!currentProject || !currentProject.is_project) {
      bar.innerHTML = '';
      document.body.classList.remove('project-active');
      return;
    }
    const pid = currentProject.name;
    const projectPath = currentProject.path;

    // Warm switch: paint synchronously from the last-known project record.
    // Background reconcile re-paints only on change. Cache miss falls
    // through to the foreground fetch below.
    const cached = _projectAttrsCache.get(projectPath);
    if (cached) {
      _renderAttrsBarFromRecord(bar, pid, cached);
      Promise.resolve().then(async () => {
        try {
          const r = await fetch('/api/project-info?path=' + encodeURIComponent(projectPath));
          if (!r.ok) return;
          const fresh = await r.json();
          const prev = _projectAttrsCache.get(projectPath);
          _projectAttrsCache.set(projectPath, fresh);
          if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
          if (!currentProject || currentProject.path !== projectPath) return;
          _renderAttrsBarFromRecord(bar, pid, fresh);
        } catch {}
      });
      return;
    }

    let p = null;
    try {
      const r = await fetch('/api/project-info?path=' + encodeURIComponent(projectPath));
      if (r.ok) p = await r.json();
    } catch {}
    if (!p) { bar.innerHTML = ''; return; }
    _projectAttrsCache.set(projectPath, p);
    _renderAttrsBarFromRecord(bar, pid, p);
  }

  // Extracted from refreshAttrsBar so both the cold and warm-switch
  // paths share one render. Pure DOM write — no network, no state
  // mutation. Reads only the server declarations on project record `p`.
  function _renderAttrsBarFromRecord(bar, pid, p) {
    const proxyCount = Array.isArray(p.proxies) ? p.proxies.length : 0;
    const proxiesLabel = proxyCount ? `${proxyCount} server${proxyCount === 1 ? '' : 's'}` : 'add server';
    const proxiesCls = proxyCount ? '' : 'empty';

    bar.innerHTML = `
      <span class="ab-spacer"></span>
      <span class="ab-chip" data-act="proxies" title="manage proxied local servers for this project">&#x1F310; <span class="v ${proxiesCls}">${escapeHtml(proxiesLabel)}</span></span>
    `;
    bar.querySelectorAll('[data-act]').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const act = chip.getAttribute('data-act');
        if (act === 'proxies') openProxiesModal();
      });
    });
  }

  // ─── Proxies modal (manage project-root servers.json from the UI) ───
  // Opened from the attrs-bar "Servers" chip. Saved proxies render as
  // management cards; fields only become editable after an explicit Edit.
  // Optional make commands power Start / Restart and Stop controls through
  // routes/proxy.py. Saving migrates legacy project.json proxies to servers.json.
  let _proxiesEscHandler = null;
  let _proxiesRowSeq = 0;
  let _proxiesProjectPath = null;
  let _proxiesProjectId = null;
  let _proxiesWorkspaceId = null;
  let _proxiesListDirty = false;
  let _proxiesHasConfigFile = false;

  async function openProxiesModal() {
    if (!currentProject || !currentProject.is_project) return;
    const overlay = document.getElementById('proxiesModal');
    if (!overlay) return;
    _proxiesProjectPath = currentProject.path;
    _proxiesProjectId = currentProject.name;
    _proxiesWorkspaceId = _projectWorkspaceId(currentProject);
    const projectPath = _proxiesProjectPath;
    const err = document.getElementById('proxiesError');
    const addBtn = document.getElementById('proxiesAddBtn');
    const saveBtn = document.getElementById('proxiesSaveBtn');
    const createBtn = document.getElementById('proxiesCreateBtn');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    if (addBtn) addBtn.disabled = true;
    if (saveBtn) saveBtn.disabled = false;
    _proxiesHasConfigFile = false;
    if (createBtn) createBtn.disabled = true;
    const cached = _projectSidebarCache.get(currentProject.path);
    const proxies = (cached && Array.isArray(cached.proxies)) ? cached.proxies : [];
    _renderProxiesRows(proxies);
    overlay.classList.add('active');
    _proxiesEscHandler = (ev) => { if (ev.key === 'Escape') closeProxiesModal(); };
    document.addEventListener('keydown', _proxiesEscHandler);
    await reloadProxyConfig(true);
    if (projectPath === _proxiesProjectPath && addBtn) addBtn.disabled = false;
  }

  function _serverConfigUrl(endpoint) {
    const params = new URLSearchParams({project_id: _proxiesProjectId || ''});
    if (_proxiesWorkspaceId) params.set('workspace', _proxiesWorkspaceId);
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
    if (!_proxiesProjectId) return false;
    if (!initialLoad && _proxyRowsAreDirty() && !confirm('Discard unsaved server changes and reload servers.json?')) return false;
    const projectPath = _proxiesProjectPath;
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
      if (projectPath !== _proxiesProjectPath || projectPath !== (currentProject && currentProject.path)) return false;
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
      if (projectPath === _proxiesProjectPath) {
        if (reloadBtn) reloadBtn.disabled = false;
        _syncProxyCreateButton(false);
      }
    }
  }

  async function createProxyConfigTemplate() {
    if (!_proxiesProjectId) return;
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
      _projectSidebarCache.delete(_proxiesProjectPath);
      _projectAttrsCache.delete(_proxiesProjectPath);
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

  function _proxyWorkspaceQuery() {
    return _proxiesWorkspaceId ? `?workspace=${encodeURIComponent(_proxiesWorkspaceId)}` : '';
  }

  async function proxyServerAction(rowId, action) {
    const row = document.querySelector(`#proxiesRows .proxies-card[data-row-id="${rowId}"]`);
    if (!row || !_proxiesProjectId) return;
    const values = _proxyRowValues(row);
    const status = row.querySelector('.proxies-action-status');
    const buttons = Array.from(row.querySelectorAll('[data-proxy-action]'));
    buttons.forEach(btn => { btn.disabled = true; btn.classList.add('busy'); });
    if (status) { status.textContent = `${action === 'stop' ? 'Stopping' : 'Starting / restarting'} ${values.label || values.name}…`; status.className = 'proxies-action-status'; }
    try {
      const url = `/api/proxies/${encodeURIComponent(_proxiesProjectId)}/${encodeURIComponent(values.name)}/${action}${_proxyWorkspaceQuery()}`;
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
    if (!_proxiesProjectPath) { closeProxiesModal(); return; }
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
    _projectSidebarCache.delete(_proxiesProjectPath);
    _projectAttrsCache.delete(_proxiesProjectPath);
    closeProxiesModal();
    if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
    if (typeof _refreshProjectSidebar === 'function') _refreshProjectSidebar({preserveScroll: true});
  }

  // ─── Productivity self-view (file tree sidebar + Lab framework workbench) ───

  async function initSelf() {
    if (!LAB_IS_ADMIN) {
      const data = await fetchWorkspaceCatalog();
      const first = (data.workspaces || [])[0];
      if (first) goToWorkspace(first.id, {replace: true});
      return;
    }
    document.body.classList.add('self-active');
    document.title = 'Home';
    // Set up a synthetic currentProject so openProjectDoc(), the sidebar, and
    // the terminal panel all work exactly like a real project tab.
    currentProject = {
      name: '__self__',
      path: SELF_REPO_PATH,
      is_project: true,
      repos: [],
      workspace_id: null,
    };
    _sidebarActivateFileConfig();
    document.getElementById('diffTabs').style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    // Re-render the tab strip so the Productivity tab flips to `.active`
    // immediately. On in-page navigation (the common case) projTabsAll
    // is already populated so all tabs render correctly. On the very
    // first page load with `?view=productivity` projTabsAll may still
    // be empty for ~50ms — the in-flight projTabsRefresh() will repaint
    // with the full tab list as soon as it returns. Mirrors what
    // initCerebro and selectRepo already do.
    if (typeof projTabsRender === 'function') projTabsRender();
    renderRepoTabs();

    // Paint the workbench scaffold synchronously. The refresh fills in
    // tasks, changed areas, and recent commits after first paint.
    selfPaintWorkbench();
    afterPageQuiet(() => {
      selfPopulateSidebar();
      selfRefreshWorkbench();
      if (!UI_CHECK) termOpenForSelf();
    });
  }

  // Shared file-tree row renderer for the self + workspace sidebars. One
  // implementation (not a sixth render site): both views feed it a
  // buildSidebarTree() node and differ only in tree scope (persisted
  // expand state), top-level auto-open folders, and active path. Rows use
  // the same fileIconHtml icons, symlink markers, notebook running/unseen
  // dots, and data-filepath hooks the git decorations poller keys on.
  const _AUTO_OPEN_SELF = new Set(['apps', 'docs', 'knowledge']);
  const _AUTO_OPEN_WORKSPACE = new Set(['projects', 'content', 'docs']);

  function renderSidebarFileTree(node, depth, parentPath, opts) {
    const {scope, autoOpen, activePath, root} = opts;
    let html = '';
    treeFolderNames(node).forEach(folder => {
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
    treeFiles(node).forEach(f => {
      const safePath = f.path.replace(/'/g, "\\'");
      const safeRoot = String(root || (currentProject && currentProject.path) || '').replace(/'/g, "\\'");
      const fname = f.path.split('/').pop();
      const icon = fileIconHtml(fname, f);
      const activeCls = activePath === f.path ? ' active' : '';
      // Notebook running / unseen dots — same logic as the project view's
      // _refreshProjectSidebar so these views surface in-flight notebooks
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
        dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openProjectDocAndJumpToUnseen('${safePath}','${safeRoot}')"></span>`;
      }
      html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}" data-entry-kind="file" data-entry-path="${escAttr(f.path)}" data-entry-root="${escAttr(root || '')}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}',{root:'${safeRoot}'})" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}',{root:'${safeRoot}'})"><span class="sidebar-fname">${dotHtml}${symlinkMarker(f)}${icon}${fname}</span></a>`;
    });
    return html;
  }

  // Populate #sidebar with a file tree rooted at SELF_REPO_PATH.
  // Mirrors the pattern used by showProjectInfo() for real projects.
  async function selfPopulateSidebar() {
    const sidebar = document.getElementById('sidebar');
    try {
      const baseRoot = SELF_REPO_PATH;
      await _sidebarEnsureWorktrees(baseRoot);
      const fileRoot = _sidebarScopedRoot(baseRoot);
      const files = await _sidebarFetchProjectFiles(fileRoot);
      if (!document.body.classList.contains('self-active')
          || !currentProject || currentProject.path !== baseRoot
          || _sidebarScopedRoot(baseRoot) !== fileRoot) return;
      _sidebarRememberAvailableExtensions(files);
      _sidebarMaybeLogRecentDiagnostics(files, fileRoot);
      _rememberNotebookFolders(fileRoot, files);

      // Bake .active onto the rendered HTML (data-filepath + class) so any
      // future sidebar rebuild — mtime poll, WS index-updated — keeps the
      // current file highlighted. Without this the active class is only
      // applied imperatively after rebuild and the selection flickers.
      const activePath = _projDocRoot === fileRoot ? (_projDocPath || null) : null;
      const workbenchActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${workbenchActive}" data-workbench="1" onclick="selfShowWorkbench()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Overview</span></a>`;
      sbHtml += _sidebarFileConfigButtonHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(baseRoot);
      sbHtml += _sidebarWorktreePickerHtml(baseRoot);
      sbHtml += symlinkLegendHtml();
      sbHtml += _sidebarWorktreeScopeStartHtml(baseRoot);
      sbHtml += _sidebarRecentSectionHtml(files, activePath, fileRoot);
      sbHtml += _sidebarFilesTitle(fileRoot);

      const tree = buildSidebarTree(files);

      sbHtml += renderSidebarFileTree(tree, 0, '', {scope: `self:${fileRoot}`, autoOpen: _AUTO_OPEN_SELF, activePath, root: fileRoot});
      sbHtml += _sidebarWorktreeScopeEndHtml(baseRoot);

      // Meta section — mirrors the per-project sidebar so `.claude/`
      // (shared skills, agents, hooks, settings) is one click away from
      // the productivity tab too. The `.claude/` placeholder is filled
      // async by /api/cerebro/tree, same as the project view.
      sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
      // Canonical cross-tool instructions at the monorepo root (CLAUDE.md → AGENTS.md).
      sbHtml += `<a class="sidebar-file sidebar-file-meta" onclick="openSharedFile('AGENTS.md')" title="AGENTS.md — canonical shared instructions (CLAUDE.md symlinks to it)" style="opacity:.7"><span class="sidebar-fname">${fileIconHtml('AGENTS.md')}AGENTS.md</span></a>`;
      const sharedClaudeFid = 'sf-claude-self-' + Math.random().toString(36).substr(2, 6);
      const _shClOpen = _treeIsOpen('shared-claude', '.claude', false);
      const _shClArrow = _shClOpen ? ' open' : '';
      const _shClChildren = _shClOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-claude" data-tree-path=".claude" data-tree-target="${sharedClaudeFid}" onclick="_treeToggleFolder(this)" title=".claude/ — skills, agents, hooks, settings (monorepo root)" style="opacity:.7"><span class="folder-arrow${_shClArrow}">▶</span>.claude/</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shClChildren}" id="${sharedClaudeFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;
      const sharedAgentsFid = 'sf-agents-self-' + Math.random().toString(36).substr(2, 6);
      const _shAgOpen = _treeIsOpen('shared-agents', '.agents', false);
      const _shAgArrow = _shAgOpen ? ' open' : '';
      const _shAgChildren = _shAgOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-agents" data-tree-path=".agents" data-tree-target="${sharedAgentsFid}" onclick="_treeToggleFolder(this)" title=".agents/ — shared config, memory & skills (cross-tool)" style="opacity:.7"><span class="folder-arrow${_shAgArrow}">▶</span>.agents/</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shAgChildren}" id="${sharedAgentsFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;

      // `content/code/` — the source for code-* skills (hello.py,
      // spike_analysis.py, etc.). Same placeholder-then-async pattern
      // as .claude/. Tree scope 'shared-code' keeps its expand state
      // separate from .claude/.
      const sharedCodeFid = 'sf-code-self-' + Math.random().toString(36).substr(2, 6);
      const _shCdOpen = _treeIsOpen('shared-code', 'code', false);
      const _shCdArrow = _shCdOpen ? ' open' : '';
      const _shCdChildren = _shCdOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-code" data-tree-path="code" data-tree-target="${sharedCodeFid}" onclick="_treeToggleFolder(this)" title="content/code/ — source for code-* skills" style="opacity:.7"><span class="folder-arrow${_shCdArrow}">▶</span>code/</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shCdChildren}" id="${sharedCodeFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;

      sidebar.innerHTML = sbHtml;

      // Populate both `.claude/` and `code/` placeholders from one
      // /api/cerebro/tree fetch. Same scope as the project view so
      // expand state syncs across tabs.
      _populateSharedMetaPlaceholders(sharedClaudeFid, sharedCodeFid);
    } catch(e) {
      sidebar.innerHTML = '<div class="sidebar-title">Home</div>';
    }
  }

  // Render the Productivity workbench scaffold into #content. The refresh
  // functions look for element IDs inside here.
  function selfPaintWorkbench() {
    _projDocPath = null;
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
          <button class="refresh-btn" onclick="openProjectDoc('AGENTS.md')">AGENTS.md</button>
          <button class="refresh-btn" onclick="openProjectDoc('Makefile')">Makefile</button>
          <button class="refresh-btn" onclick="openProjectDoc('README.md')">README.md</button>
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
    _projDocPath = null;
    _contextSubView = 'overview';
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
    _projDocPath = null;
    _contextSubView = 'admin';
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
            <h2>Users &amp; workspace access</h2>
            <form class="admin-access-toolbar" onsubmit="return adminCreateUser(event)">
              <label>User name<input id="adminNewUsername" autocomplete="off" required placeholder="username"></label>
              <label>Display name<input id="adminNewName" autocomplete="off" placeholder="Name"></label>
              <label>Role<select id="adminNewRole"><option value="user">User</option><option value="admin">Admin</option></select></label>
              <label>Password<input id="adminNewPassword" type="password" autocomplete="new-password" required placeholder="Password"></label>
              <button class="refresh-btn" type="submit">Add user</button>
            </form>
            <div class="admin-user-list" id="adminUsersList"><div class="ws-muted">Loading users…</div></div>
          </div>
          <div class="s-section admin-access-section">
            <h2>Add workspace</h2>
            <form class="admin-access-toolbar admin-workspace-form" onsubmit="return adminAddWorkspace(event)">
              <label>Name<input id="adminWorkspaceName" placeholder="Team workspace"></label>
              <label>Path<input id="adminWorkspacePath" required placeholder="/absolute/path/to/workspace"></label>
              <label style="flex-direction:row;align-items:center;padding-bottom:7px"><input id="adminWorkspaceCreate" type="checkbox"> Create if missing</label>
              <button class="refresh-btn" type="submit">Add workspace</button>
            </form>
            <div class="admin-user-status" id="adminWorkspaceStatus"></div>
          </div>
          <div class="s-section" id="dashKpis"></div>
          <div class="s-section" id="dashServers"><h2>Servers</h2><div class="srv-empty">Loading servers…</div></div>
          <div class="s-section" id="dashTerms"><h2>Terminals</h2><div class="term-empty">Loading terminal sessions…</div></div>
          <div class="s-section admin-logs-section">
            <h2>Logs <span class="count" id="adminLogCount"></span></h2>
            <div class="admin-log-toolbar">
              <button class="refresh-btn" data-log="errors.log">Errors</button>
              <button class="refresh-btn" data-log="backend.log">Backend</button>
              <button class="refresh-btn" data-log="frontend.log">Frontend</button>
              <span class="admin-log-toolbar-spacer"></span>
              <button class="refresh-btn" id="adminLogCopyButton" type="button" data-log-action="copy">Copy errors</button>
              <button class="refresh-btn admin-log-flush" id="adminLogFlushButton" type="button" data-log-action="flush">Flush errors</button>
              <span class="admin-log-status" id="adminLogStatus" role="status"></span>
            </div>
            <pre class="admin-log-output" id="adminLogOutput">Loading consolidated logs…</pre>
          </div>
        </div>
      </div>`;
    content.querySelector('#dashServers').addEventListener('click', dashServersOnClick);
    content.querySelector('#dashTerms').addEventListener('click', dashTermsOnClick);
    content.querySelectorAll('[data-log]').forEach(btn => {
      btn.addEventListener('click', () => adminRefreshLogs(btn.getAttribute('data-log')));
    });
    content.querySelector('#adminLogCopyButton').addEventListener('click', event => {
      adminCopyLogs(event.currentTarget);
    });
    content.querySelector('#adminLogFlushButton').addEventListener('click', event => {
      adminFlushLogs(event.currentTarget);
    });
    if (!UI_CHECK) dashStartPolling();
    dashPollTick();
    adminLoadAccess();
    adminRefreshLogs('errors.log');
  }
  window.selfShowAdmin = selfShowAdmin;

  let _adminAccessWorkspaces = [];

  function adminRenderUsers(users) {
    const host = document.getElementById('adminUsersList');
    if (!host) return;
    if (!users.length) {
      host.innerHTML = '<div class="ws-muted">No users.</div>';
      return;
    }
    host.innerHTML = users.map(user => {
      const builtIn = user.built_in === true;
      const permissions = _adminAccessWorkspaces.map(workspace => {
        const checked = (user.workspaces || []).includes(workspace.id) ? ' checked' : '';
        const disabled = user.role === 'admin' || builtIn ? ' disabled' : '';
        return `<label><input type="checkbox" data-workspace-permission="${escAttr(workspace.id)}"${checked}${disabled}>${selfEsc(workspace.name || workspace.id)}</label>`;
      }).join('') || '<span class="ws-muted">Add a workspace before assigning access.</span>';
      return `<div class="admin-user-row" data-admin-user="${escAttr(user.username)}">
        <div class="admin-user-head">
          <div class="admin-user-identity"><strong>${selfEsc(user.name)}</strong><code>${selfEsc(user.username)}${builtIn ? ' · built-in' : ''}</code></div>
          <label class="admin-user-field">Role<select data-user-role${builtIn ? ' disabled' : ''}><option value="user"${user.role === 'user' ? ' selected' : ''}>User</option><option value="admin"${user.role === 'admin' ? ' selected' : ''}>Admin</option></select></label>
          <label class="admin-user-field">New password<input data-user-password type="password" autocomplete="new-password" placeholder="${builtIn ? 'Fixed local password' : 'Leave unchanged'}"${builtIn ? ' disabled' : ''}></label>
          <label class="admin-user-field" style="flex-direction:row;align-items:center;padding-bottom:7px"><input data-user-disabled type="checkbox"${user.disabled ? ' checked' : ''}${builtIn ? ' disabled' : ''}> Disabled</label>
          ${builtIn ? '<span class="admin-built-in-badge">Fixed admin</span>' : '<button class="refresh-btn" type="button" onclick="adminSaveUser(this)">Save</button>'}
        </div>
        <div class="admin-permissions">${permissions}</div>
        <div class="admin-user-status" data-user-status>${builtIn ? 'Built-in local administrator. Username and password are fixed.' : (user.role === 'admin' ? 'Admins can access every workspace.' : '')}</div>
      </div>`;
    }).join('');
  }

  async function adminLoadAccess() {
    const host = document.getElementById('adminUsersList');
    try {
      const [usersRes, workspacesRes] = await Promise.all([
        fetch('/api/admin/users'),
        fetchWorkspaceCatalog(),
      ]);
      if (!usersRes.ok) throw new Error((await usersRes.json().catch(() => ({}))).detail || 'Could not load users');
      const usersBody = await usersRes.json();
      _adminAccessWorkspaces = Array.isArray(workspacesRes.workspaces) ? workspacesRes.workspaces : [];
      adminRenderUsers(usersBody.users || []);
    } catch (e) {
      if (host) host.innerHTML = `<div class="ws-muted">${selfEsc(e.message || e)}</div>`;
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
      workspaces: Array.from(row.querySelectorAll('[data-workspace-permission]:checked')).map(input => input.getAttribute('data-workspace-permission')),
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
      workspaces: [],
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

  async function adminAddWorkspace(event) {
    if (event) event.preventDefault();
    const status = document.getElementById('adminWorkspaceStatus');
    const payload = {
      name: document.getElementById('adminWorkspaceName').value.trim() || null,
      path: document.getElementById('adminWorkspacePath').value.trim(),
      create: document.getElementById('adminWorkspaceCreate').checked,
    };
    if (status) status.textContent = 'Adding…';
    try {
      const response = await fetch('/api/workspaces', {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || 'Could not add workspace');
      workspaceCatalog = [];
      _workspaceCatalogInFlight = null;
      _reposInFlight = null;
      event.target.reset();
      if (status) status.textContent = 'Workspace added';
      await adminLoadAccess();
      await projTabsRefresh();
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.adminAddWorkspace = adminAddWorkspace;

  function _adminLogLabel(file) {
    return String(file || 'errors.log').replace(/\.log$/i, '');
  }

  function _adminLogRowText(row) {
    const stamp = row.ts || row.timestamp || '';
    const level = String(row.level || '').toUpperCase();
    const message = row.msg || row.message || row.raw || JSON.stringify(row);
    const lines = [`[${row.workspace || 'workspace'}] ${stamp} ${level} ${message}`.trim()];
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

  async function adminRefreshLogs(file = 'errors.log') {
    const output = document.getElementById('adminLogOutput');
    const count = document.getElementById('adminLogCount');
    const status = document.getElementById('adminLogStatus');
    const copyButton = document.getElementById('adminLogCopyButton');
    const flushButton = document.getElementById('adminLogFlushButton');
    if (!output) return;
    output.setAttribute('data-log-file', file);
    document.querySelectorAll('.admin-log-toolbar [data-log]').forEach(button => {
      button.classList.toggle('active', button.getAttribute('data-log') === file);
    });
    const label = _adminLogLabel(file);
    if (copyButton) copyButton.textContent = `Copy ${label}`;
    if (flushButton) flushButton.textContent = `Flush ${label}`;
    if (status) status.textContent = '';
    output.textContent = 'Loading…';
    try {
      const r = await fetch('/api/log/tail/all?file=' + encodeURIComponent(file) + '&tail=300');
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'load failed');
      const data = await r.json();
      const entries = data.entries || [];
      if (count) count.textContent = entries.length ? String(entries.length) : '';
      output.textContent = entries.length ? entries.map(_adminLogRowText).join('\n') : 'No log entries.';
    } catch (e) {
      output.textContent = 'Could not load logs: ' + (e.message || e);
    }
  }
  window.adminRefreshLogs = adminRefreshLogs;

  async function adminCopyLogs(button) {
    const output = document.getElementById('adminLogOutput');
    const status = document.getElementById('adminLogStatus');
    if (!output) return;
    const ok = await _copyToClipboard(output.textContent || '', button);
    if (status) status.textContent = ok ? 'Copied to clipboard' : 'Copy failed';
  }
  window.adminCopyLogs = adminCopyLogs;

  async function adminFlushLogs(button) {
    const output = document.getElementById('adminLogOutput');
    const status = document.getElementById('adminLogStatus');
    const file = output && output.getAttribute('data-log-file') || 'errors.log';
    const label = _adminLogLabel(file);
    if (!confirm(`Flush ${file} across all registered workspaces? This cannot be undone.`)) return;
    if (button) button.disabled = true;
    if (status) status.textContent = `Flushing ${label}…`;
    try {
      const response = await fetch('/api/log/clear/all?file=' + encodeURIComponent(file), {method: 'DELETE'});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || 'flush failed');
      const cleared = Array.isArray(data.cleared) ? data.cleared.length : 0;
      const failed = Array.isArray(data.failed) ? data.failed : [];
      if (failed.length) {
        throw new Error(`cleared ${cleared}; failed: ${failed.map(row => row.workspace).join(', ')}`);
      }
      await adminRefreshLogs(file);
      if (status) status.textContent = `Flushed ${label} in ${cleared} workspace${cleared === 1 ? '' : 's'}`;
    } catch (e) {
      if (status) status.textContent = 'Flush failed: ' + (e.message || e);
    } finally {
      if (button) button.disabled = false;
    }
  }
  window.adminFlushLogs = adminFlushLogs;

  // Toggle hidden-files visibility for the productivity sidebar.
  // Mirrors toggleProjectDotFiles() but re-renders via selfPopulateSidebar()
  // instead of showProjectInfo().
  function selfToggleDotFiles(checked) {
    showProjectDotFiles = checked;
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
      const open = row.file ? ` onclick="openProjectDoc('${safePath}')"` : '';
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
      const r = await fetch('/api/projects/' + SELF_PROJECT_ID + '/tasks');
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
      await fetch(`/api/tasks/${SELF_PROJECT_ID}/${taskId}/status`, {
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
        body: JSON.stringify({project_id: SELF_PROJECT_ID, title, priority: prio.value}),
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
          : `<button type="button" class="s-file-link" onclick="openProjectDoc('${safePath}')">${name}</button>`;
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

  // Terminal panel for the Productivity pseudo-project: claude session at repo root.
  // Terminal panel for the Productivity pseudo-project: sessions rooted at the
  // repo root. Mirrors termOpenForCerebro() exactly, substituting SELF_PROJECT_ID.
  async function termOpenForSelf() {
    if (!_termIsScopeActive(SELF_PROJECT_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(SELF_PROJECT_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForProject(SELF_PROJECT_ID);
    termStartPeriodicRefresh();
  }

  // Terminal panel for the Workspace pseudo-project: sessions start at the
  // active workspace root and persist independently from every real project.
  async function termOpenForWorkspace() {
    if (!_termIsScopeActive(WORKSPACE_PROJECT_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(WORKSPACE_PROJECT_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForProject(WORKSPACE_PROJECT_ID);
    termStartPeriodicRefresh();
  }

  // ─── Workspace view (workspace-scoped management surface) ───
  // Mirrors initSelf(): synthetic currentProject rooted at the selected
  // registered workspace so its files/config/projects can stay open beside
  // tabs from every other workspace.

  async function initWorkspaceView(workspaceId) {
    // The initial `?view=…` dispatch calls us directly without
    // _swapViewState, so strip mutually exclusive view classes here.
    document.body.classList.remove(
      'cerebro-active', 'self-active', 'project-active',
    );
    document.body.classList.add('workspace-active');
    document.title = 'Workspace';
    const dt = document.getElementById('diffTabs');
    if (dt) dt.style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    // Re-render the tab strip so the workspace tab flips to `.active`
    // immediately (same first-load caveat as initSelf: projTabsRefresh
    // repaints with the full list once it returns).
    _projDocPath = null;

    // Scaffold synchronously; the fetch below fills in the real content.
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="s-inner ws-overview"><div class="loading">Loading workspace…</div></div>';

    const data = await fetchWorkspaceCatalog();
    // The user may have navigated away while the fetch was in flight.
    if (!document.body.classList.contains('workspace-active')) return;
    const current = ((data && data.workspaces) || []).find(w => w.id === workspaceId)
      || ((data && data.workspaces) || []).find(w => w.active)
      || null;
    _workspaceCurrent = current;
    if (!current || !current.path) {
      if (content) content.innerHTML = '<div class="s-inner ws-overview"><div class="loading">Could not load the active workspace.</div></div>';
      return;
    }
    _setWorkspaceTabOpen(current.id, true);
    document.title = 'Workspace — ' + (current.name || current.id);
    // Synthetic project rooted at the workspace root (same trick as the
    // self view) so the doc pane, sidebar, and pollers treat it like a
    // real project.
    currentProject = {
      name: WORKSPACE_PROJECT_ID,
      path: current.path,
      is_project: true,
      repos: [],
      workspace_id: current.id,
      workspace_name: current.name || current.id,
      workspace_color: current.color || '#8b949e',
    };
    _sidebarActivateFileConfig();
    if (typeof projTabsRender === 'function') projTabsRender();
    renderRepoTabs();
    _sidebarApplyForView();
    workspacePaintOverview(current);
    afterPageQuiet(() => {
      workspacePopulateSidebar();
      workspaceRefreshCards();
      if (!UI_CHECK) termOpenForWorkspace();
    });
  }

  // Overview scaffold: header (name + id badge + active pill + path) and
  // the three cards. Reuses the productivity workbench's .s-inner /
  // .s-workbench-grid / .s-section card classes so it reads like the
  // existing dashboards. workspaceRefreshCards() fills the card bodies.
  function workspacePaintOverview(current) {
    _projDocPath = null;
    _contextSubView = 'overview';
    renderRepoTabs();
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="s-inner ws-overview">
        <div class="s-head ws-ov-head">
          <h1>${selfEsc(current.name || current.id)}
            <span class="ws-badge" title="workspace id">${selfEsc(current.id)}</span></h1>
        </div>
        <div class="ws-ov-path" title="${escAttr(current.path)}">${selfEsc(current.path)}</div>
        <div class="s-workbench-grid ws-ov-grid">
          <div class="s-section" id="wsAppearanceCard">
            <h2>Appearance</h2>
            <form class="ws-appearance-form" onsubmit="return workspaceSaveAppearance(event)">
              <label>Name or alias
                <input id="wsAppearanceName" type="text" value="${escAttr(current.name || current.id)}" maxlength="80" required>
              </label>
              <label>Tab color
                <span class="ws-color-row">
                  <input id="wsAppearanceColor" type="color" value="${escAttr(current.color || '#8b949e')}" oninput="this.nextElementSibling.textContent=this.value">
                  <span class="ws-color-value">${selfEsc(current.color || '#8b949e')}</span>
                </span>
              </label>
              <div class="ws-card-actions"><button class="refresh-btn" type="submit">Save appearance</button><span class="ws-appearance-status" id="wsAppearanceStatus"></span></div>
            </form>
          </div>
          <div class="s-section" id="wsConfigCard">
            <h2>Configuration</h2>
            <div class="ws-card-body" id="wsConfigBody"><div class="ws-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="wsAgentsCard">
            <h2>Agents</h2>
            <div class="ws-card-body" id="wsAgentsBody"><div class="ws-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="wsProjectsCard">
            <h2>Projects <span class="count" id="wsProjectsCount"></span>
              <button class="refresh-btn" type="button" onclick="openWorkspaceProjectModal()">+ New project</button></h2>
            <ul class="ws-proj-list" id="wsProjectsList"><li class="s-empty">Loading…</li></ul>
          </div>
        </div>
      </div>`;
  }

  // Return to the overview from a doc view (sidebar "Overview" link).
  function workspaceShowOverview() {
    _projDocPath = null;
    _contextSubView = 'overview';
    renderRepoTabs();
    document.querySelectorAll('#sidebar .sidebar-file').forEach(el => el.classList.remove('active'));
    if (_workspaceCurrent && currentProject && currentProject.name === WORKSPACE_PROJECT_ID) {
      workspacePaintOverview(_workspaceCurrent);
      afterFirstPaint(() => workspaceRefreshCards());
    } else {
      initWorkspaceView(_workspaceCurrent && _workspaceCurrent.id);
    }
  }

  async function workspaceSaveAppearance(event) {
    if (event) event.preventDefault();
    if (!_workspaceCurrent) return false;
    const nameEl = document.getElementById('wsAppearanceName');
    const colorEl = document.getElementById('wsAppearanceColor');
    const status = document.getElementById('wsAppearanceStatus');
    const name = (nameEl && nameEl.value || '').trim();
    const color = colorEl && colorEl.value;
    if (status) status.textContent = 'Saving…';
    try {
      const r = await fetch('/api/workspaces/' + encodeURIComponent(_workspaceCurrent.id) + '/appearance', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, color}),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'save failed');
      const updated = await r.json();
      _workspaceCurrent.name = updated.name;
      _workspaceCurrent.color = updated.color;
      const catalogRow = _workspaceById(_workspaceCurrent.id);
      if (catalogRow) Object.assign(catalogRow, updated);
      if (currentProject) {
        currentProject.workspace_name = updated.name;
        currentProject.workspace_color = updated.color;
      }
      workspacePaintOverview(_workspaceCurrent);
      projTabsRender();
      const savedStatus = document.getElementById('wsAppearanceStatus');
      if (savedStatus) savedStatus.textContent = 'Saved';
    } catch (e) {
      if (status) status.textContent = e.message || String(e);
    }
    return false;
  }
  window.workspaceSaveAppearance = workspaceSaveAppearance;

  async function workspaceRefreshCards() {
    if (!document.body.classList.contains('workspace-active')) return;
    await Promise.all([
      workspaceRenderConfigCard(),
      workspaceRenderAgentsCard(),
      workspaceRenderProjectsCard(),
    ]);
  }

  // "Configuration" card: workspace.json status from /api/workspace/config.
  // The file is optional — absent is a normal, valid state. The card offers
  // a starter-file button when absent and, in every state, a "Copy setup
  // prompt" button that produces a state-aware prompt for the workspace
  // agent (structure reference + the current validation problems).
  let _wsCfgLast = null;

  async function workspaceRenderConfigCard() {
    const body = document.getElementById('wsConfigBody');
    if (!body) return;
    let cfg = null;
    try {
      const r = await fetch('/api/workspace/config?workspace=' + encodeURIComponent(_workspaceCurrent.id));
      if (r.ok) cfg = await r.json();
    } catch {}
    if (!body.isConnected) return;  // view repainted/navigated meanwhile
    _wsCfgLast = cfg;
    if (!cfg) {
      body.innerHTML = '<div class="ws-muted">Could not load workspace.json status.</div>';
      return;
    }
    const copyBtn = '<button class="refresh-btn" onclick="wsCopySetupPrompt(this)" title="Copy a prompt for your workspace agent: expected workspace.json structure plus the current validation state">Copy setup prompt</button>';
    if (!cfg.present) {
      body.innerHTML = [
        '<div class="ws-muted">workspace.json not present (optional).</div>',
        `<div class="ws-card-actions"><button class="refresh-btn" onclick="wsCreateConfig(this)">Create workspace config</button>${copyBtn}</div>`,
      ].join('');
      return;
    }
    const errors = cfg.errors || [];
    const warnings = cfg.warnings || [];
    const rows = [];
    if (cfg.valid) {
      rows.push(`<div class="ws-cfg-status ok">✓ workspace.json is valid${warnings.length ? ' (with warnings)' : ''}</div>`);
    } else {
      rows.push('<div class="ws-cfg-status err">✗ workspace.json has problems</div>');
    }
    for (const e of errors) rows.push(`<div class="ws-cfg-issue err">${selfEsc(e)}</div>`);
    for (const w of warnings) rows.push(`<div class="ws-cfg-issue warn">${selfEsc(w)}</div>`);
    rows.push(`<div class="ws-card-actions"><button class="refresh-btn" onclick="openProjectDoc('workspace.json')">Open workspace.json</button>${copyBtn}</div>`);
    body.innerHTML = rows.join('');
  }

  // The setup prompt handed to the workspace agent. Self-contained: the
  // agent works inside the workspace repo and may not have framework docs.
  function _wsSetupPromptText() {
    const cfg = _wsCfgLast || {};
    const root = cfg.root || (_workspaceCurrent && _workspaceCurrent.path) || '(workspace root)';
    const configUrl = location.origin + '/api/workspace/config?workspace=' +
      encodeURIComponent((_workspaceCurrent && _workspaceCurrent.id) || '');
    const issues = [];
    for (const e of (cfg.errors || [])) issues.push('- ERROR: ' + e);
    for (const w of (cfg.warnings || [])) issues.push('- warning: ' + w);
    let state;
    if (!cfg.present) {
      state = 'There is no workspace.json yet. Create it at ' + root + '/workspace.json.';
    } else if (!cfg.valid) {
      state = 'workspace.json exists but is INVALID. Fix these problems:\n' + issues.join('\n');
    } else if (issues.length) {
      state = 'workspace.json exists and is valid, but has warnings to clean up:\n' + issues.join('\n');
    } else {
      state = 'workspace.json exists and is valid. Review it against the structure below and extend it to describe what this workspace actually uses.';
    }
    return [
      "Set up this workspace's workspace.json — the declarative configuration Neurona",
      'reads at the workspace root. Work from the workspace root: ' + root,
      '',
      'Current state: ' + state,
      '',
      'Expected structure (version 1). Everything except "version" is optional —',
      'describe only what this workspace actually uses:',
      '',
      '{',
      '  "version": 1,',
      '  "id": "workspace-id",',
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
      '  "project": {',
      '    "template": "templates/project",',
      '    "features": ["tasks", "docs", "notebooks", "prs", "diffs"],',
      '    "mounts": [',
      '      {"source": "skills", "target": ".agents/skills", "mode": "symlink"},',
      '      {"source": "skills", "target": ".claude/skills", "mode": "symlink", "when": "claude"}',
      '    ]',
      '  },',
      '  "notebooks": {',
      '    "enabled": true,',
      '    "provider": "darwin",',
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
      '- "agents.supported" lists the agent CLIs this workspace uses ("claude",',
      '  "codex", "copilot"); "agents.default" must be one of them.',
      '- "agents.projections" map one tool-neutral source file to the per-tool',
      '  surfaces (AGENTS.md, CLAUDE.md, .github/copilot-instructions.md).',
      '  "mode" is "symlink" | "adapter" | "copy"; "when" limits an entry to one',
      '  supported agent.',
      '- "project.features" are the surfaces projects get; "project.mounts" are',
      '  shared sources linked into each project (e.g. skills -> .agents/skills).',
      '- "notebooks" selects the executor ("darwin" is the only provider today).',
      '- "display" holds UI hints: "autoOpen", "hide", "showProjectionOrigin".',
      '',
      'How to work:',
      '1. Look at what actually exists in the workspace tree (agents/, skills/,',
      '   code/, templates/, projects/, repositories/) and write configuration that',
      '   matches reality, not aspiration.',
      '2. Write valid JSON (no comments, no trailing commas) at',
      '   ' + root + '/workspace.json.',
      '3. Projections declare intent. If you also apply them, use relative symlinks',
      '   and never overwrite a real file — only replace links that already point',
      '   into workspace sources, or files whose first line marks them generated.',
      '4. Verify when done: ' + configUrl + ' must show',
      '   "valid": true with an empty "errors" list. The Workspace tab\'s',
      '   Configuration card shows the same.',
    ].join('\n');
  }

  async function wsCopySetupPrompt(btn) {
    await _copyToClipboard(_wsSetupPromptText(), btn);
  }
  window.wsCopySetupPrompt = wsCopySetupPrompt;

  async function wsCreateConfig(btn) {
    if (btn) btn.disabled = true;
    try {
      const r = await fetch('/api/workspace/config/init?workspace=' + encodeURIComponent(_workspaceCurrent.id), { method: 'POST' });
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail || 'create failed';
        if (btn) { btn.textContent = String(detail); btn.disabled = false; }
        return;
      }
      _wsCfgLast = await r.json();
      // Hand the user the next step in one motion: starter written, prompt
      // for the agent already on the clipboard.
      await _copyToClipboard(_wsSetupPromptText(), btn);
      await workspaceRenderConfigCard();
    } finally {
      if (btn && btn.isConnected) btn.disabled = false;
    }
  }
  window.wsCreateConfig = wsCreateConfig;

  // "Agents" card: workspace.json controls which agent choices appear in
  // every terminal/settings menu. Autopilot remains a launch setting edited
  // in Settings; availability is toggled here at workspace scope.
  async function workspaceRenderAgentsCard() {
    const body = document.getElementById('wsAgentsBody');
    if (!body) return;
    let s = _settings;
    // force: the workspace agent may have edited workspace.json directly
    // (that's the documented flow) — a cached policy would keep stale
    // agents in every menu until a full reload.
    let policy = await loadWorkspaceAgentPolicy({force: true});
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
      return `<label class="ws-agent-row${available ? '' : ' off'}">
        <input type="checkbox" ${available ? 'checked' : ''} ${lastEnabled ? 'disabled' : ''}
               onchange="workspaceToggleAgent('${a}', this.checked, this)"
               title="${lastEnabled ? 'At least one agent must remain enabled' : `Show ${escAttr(AGENT_LABELS[a])} in workspace menus`}">
        <span class="ws-agent-name">${selfEsc(AGENT_LABELS[a])}</span>
        ${available && a === defaultAgent ? '<span class="ws-agent-default">default</span>' : ''}
        <span class="ws-agent-auto${on ? ' on' : ''}">autopilot ${on ? 'on' : 'off'}${selfEsc(flag)}</span>
      </label>`;
    });
    rows.unshift('<div class="ws-agent-hint">Enabled agents appear in every <strong>+ New</strong> menu.</div>');
    rows.push('<div class="ws-card-actions"><button class="refresh-btn" onclick="openSettings()">Launch settings</button></div>');
    body.innerHTML = rows.join('');
  }

  async function workspaceToggleAgent(agent, checked, checkbox) {
    const policy = await loadWorkspaceAgentPolicy();
    const next = new Set(policy.supported || []);
    if (checked) next.add(agent);
    else next.delete(agent);
    if (!next.size) {
      if (checkbox) checkbox.checked = true;
      return;
    }
    const card = document.getElementById('wsAgentsBody');
    if (card) card.querySelectorAll('input,button').forEach(el => { el.disabled = true; });
    try {
      const r = await fetch('/api/workspace/agents', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          workspace: _workspaceCurrent && _workspaceCurrent.id,
          supported: Object.keys(AGENT_LABELS).filter(a => next.has(a)),
        }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'update failed');
      _workspaceAgentPolicy = Object.assign({workspace: _workspaceCurrent && _workspaceCurrent.id}, await r.json());
      await Promise.all([workspaceRenderAgentsCard(), workspaceRenderConfigCard()]);
    } catch (e) {
      if (card && card.isConnected) {
        card.innerHTML = `<div class="ws-cfg-issue err">${selfEsc(e.message || e)}</div>`;
        setTimeout(() => workspaceRenderAgentsCard(), 1800);
      }
    }
  }
  window.workspaceToggleAgent = workspaceToggleAgent;

  let _workspaceProjectCreateBusy = false;

  function openWorkspaceProjectModal() {
    if (!_workspaceCurrent || _workspaceCurrent.unavailable) return;
    const modal = document.getElementById('workspaceProjectModal');
    const form = document.getElementById('workspaceProjectForm');
    const context = document.getElementById('workspaceProjectContext');
    const error = document.getElementById('workspaceProjectError');
    if (!modal || !form) return;
    form.reset();
    if (context) context.textContent = _workspaceCurrent.name || _workspaceCurrent.id;
    if (error) {
      error.textContent = '';
      error.classList.remove('on');
    }
    modal.classList.add('active');
    setTimeout(() => {
      const input = document.getElementById('workspaceProjectId');
      if (input) input.focus();
    }, 0);
  }
  window.openWorkspaceProjectModal = openWorkspaceProjectModal;

  function closeWorkspaceProjectModal() {
    if (_workspaceProjectCreateBusy) return;
    const modal = document.getElementById('workspaceProjectModal');
    if (modal) modal.classList.remove('active');
  }
  window.closeWorkspaceProjectModal = closeWorkspaceProjectModal;

  function _workspaceProjectCsv(value) {
    return String(value || '').split(',').map(item => item.trim()).filter(Boolean);
  }

  async function submitWorkspaceProject(event) {
    if (event) event.preventDefault();
    if (_workspaceProjectCreateBusy || !_workspaceCurrent) return false;
    const form = document.getElementById('workspaceProjectForm');
    const error = document.getElementById('workspaceProjectError');
    const submit = document.getElementById('workspaceProjectSubmit');
    if (!form) return false;

    const workspaceId = _workspaceCurrent.id;
    _workspaceProjectCreateBusy = true;
    if (submit) {
      submit.disabled = true;
      submit.textContent = 'Creating…';
    }
    if (error) {
      error.textContent = '';
      error.classList.remove('on');
    }

    try {
      const response = await fetch('/api/projects', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          id: form.elements.id.value.trim(),
          workspace: workspaceId,
          description: form.elements.description.value.trim(),
          priority: form.elements.priority.value || null,
          due: form.elements.due.value || null,
          tags: _workspaceProjectCsv(form.elements.tags.value),
          labels: _workspaceProjectCsv(form.elements.labels.value),
        }),
      });
      const created = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(created.detail || 'project creation failed');

      // A catalog request that started before creation may not contain the
      // new row. Let it settle, then fetch an authoritative post-create list.
      const pendingCatalog = _workspaceCatalogInFlight;
      if (pendingCatalog) await pendingCatalog;
      const data = await fetchWorkspaceCatalog();
      const workspaces = (data && data.workspaces) || [];
      const refreshed = workspaces.find(row => row.id === workspaceId);
      if (refreshed) _workspaceCurrent = refreshed;
      projectsList = workspaces.flatMap(row => row.project_rows || []);
      const project = projectsList.find(row =>
        row.workspace === workspaceId && row.name === created.id);

      _workspaceProjectCreateBusy = false;
      closeWorkspaceProjectModal();
      if (project && project.path) goToProject(project.path);
      else await workspaceRenderProjectsCard();
    } catch (e) {
      if (error) {
        error.textContent = e.message || String(e);
        error.classList.add('on');
      }
    } finally {
      _workspaceProjectCreateBusy = false;
      if (submit) {
        submit.disabled = false;
        submit.textContent = 'Create project';
      }
    }
    return false;
  }
  window.submitWorkspaceProject = submitWorkspaceProject;

  // "Projects" card: the shown workspace's project ids from
  // /api/workspaces/projects. Rows open the project the same way Home's
  // active-workspace rows do (goToProjectById → in-page nav).
  async function workspaceRenderProjectsCard() {
    const list = document.getElementById('wsProjectsList');
    const count = document.getElementById('wsProjectsCount');
    if (!list) return;
    if (!list.isConnected) return;
    const ws = _workspaceCurrent;
    if (!ws) {
      if (count) count.textContent = '';
      list.innerHTML = '<li class="s-empty">Could not load projects.</li>';
      return;
    }
    if (ws.unavailable) {
      if (count) count.textContent = '';
      list.innerHTML = `<li class="s-empty">${selfEsc(ws.detail || 'workspace volume unavailable')}</li>`;
      return;
    }
    const projects = ws.project_rows || [];
    if (count) count.textContent = projects.length ? String(projects.length) : '';
    if (!projects.length) {
      list.innerHTML = '<li class="s-empty">No projects yet.</li>';
      return;
    }
    list.innerHTML = projects.map(project => `
      <li class="ws-proj-row" data-path="${escAttr(project.path)}" role="button" tabindex="0" title="Open ${escAttr(_projectDisplayName(project))}">
        <span class="ws-proj-name">${selfEsc(_projectDisplayName(project))}</span>
        <span class="p-caret">›</span>
      </li>`).join('');
    list.querySelectorAll('.ws-proj-row').forEach(row => {
      row.addEventListener('click', () => goToProject(row.getAttribute('data-path')));
    });
  }

  // Populate #sidebar with the workspace root's real file tree. Same
  // renderer as the self view (renderSidebarFileTree) — icons, git
  // decorations, notebook dots, hidden-files toggle, symlink legend. No
  // Meta section: the workspace tab shows the root exactly as on disk.
  async function workspacePopulateSidebar() {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar || !currentProject || currentProject.name !== WORKSPACE_PROJECT_ID) return;
    const rootPath = currentProject.path;
    try {
      await _sidebarEnsureWorktrees(rootPath);
      const fileRoot = _sidebarScopedRoot(rootPath);
      const files = await _sidebarFetchProjectFiles(fileRoot);
      if (!document.body.classList.contains('workspace-active')) return;
      if (!currentProject || currentProject.path !== rootPath) return;
      if (_sidebarScopedRoot(rootPath) !== fileRoot) return;
      _sidebarRememberAvailableExtensions(files);
      _sidebarMaybeLogRecentDiagnostics(files, fileRoot);
      _rememberNotebookFolders(fileRoot, files);

      const activePath = _projDocRoot === fileRoot ? (_projDocPath || null) : null;
      const overviewActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${overviewActive}" data-ws-overview="1" onclick="workspaceShowOverview()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Overview</span></a>`;
      sbHtml += _sidebarFileConfigButtonHtml();
      sbHtml += _sidebarFileScopeButtonsHtml(rootPath);
      sbHtml += _sidebarWorktreePickerHtml(rootPath);
      sbHtml += symlinkLegendHtml();
      sbHtml += _sidebarWorktreeScopeStartHtml(rootPath);
      sbHtml += _sidebarRecentSectionHtml(files, activePath, fileRoot);
      sbHtml += _sidebarFilesTitle(fileRoot);
      sbHtml += renderSidebarFileTree(buildSidebarTree(files), 0, '', {scope: `workspace:${fileRoot}`, autoOpen: _AUTO_OPEN_WORKSPACE, activePath, root: fileRoot});
      sbHtml += _sidebarWorktreeScopeEndHtml(rootPath);
      sidebar.innerHTML = sbHtml;
      // Fast first decoration pass (cached + rate-limited server-side);
      // the shared 6s poll keeps it fresh afterwards.
      _sidebarGitStatusRefresh();
    } catch (e) {
      sidebar.innerHTML = '<div class="sidebar-title">Workspace</div>';
    }
  }

  // Toggle hidden-files visibility for the workspace sidebar. Mirrors
  // selfToggleDotFiles().
  function workspaceToggleDotFiles(checked) {
    showProjectDotFiles = checked;
    _sidebarFileConfig.showHidden = checked;
    _storeSidebarFileConfig();
    workspacePopulateSidebar();
  }

  async function initCerebro(initialPath) {
    document.body.classList.add('cerebro-active');
    document.title = 'Cerebro';
    // Re-render the tab strip so the Cerebro tab shows up as active.
    if (typeof projTabsRender === 'function') projTabsRender();
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
          ['date', 'type', 'scope', 'projects', 'tags', 'people'].filter(k => k in fm).map(k => {
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
  // Cerebro viewer and the project doc pane use this so a file viewed in
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
      // Same iframe re-mount guard as _projectRenderHtml — avoids a white
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

  // Terminal panel for the Knowledge pseudo-project: claude session rooted at knowledge/.
  async function termOpenForCerebro() {
    // Mirror termOpenForProject, but wired to the __cerebro__ pseudo-project.
    if (!_termIsScopeActive(CEREBRO_PROJECT_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(CEREBRO_PROJECT_ID)) {
      termStartPeriodicRefresh();
      return;
    }
    await _termRestoreSessionsForProject(CEREBRO_PROJECT_ID);
    termStartPeriodicRefresh();
  }

  async function termRefreshSessionsByProjectId(pid) {
    // Fetches the live session list and re-renders the pill row.
    let fresh = [];
    let ok = false;
    const workspaceId = _termWorkspaceId();
    const sessionCacheKey = _termSessionsKey(pid, workspaceId);
    try {
      const r = await fetch('/api/term/sessions?project_id=' + encodeURIComponent(pid) + _workspaceQuery(workspaceId));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(sessionCacheKey, fresh);
    // Stale-response guard — see termRefreshSessions for why.
    if (pid !== _termActiveProjectId() || workspaceId !== _termWorkspaceId()) return ok;
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

  function _nbLiveKey(workspaceId, relPath) {
    return `${String(workspaceId || '')}::${String(relPath || '')}`;
  }

  function _currentOpenNotebookRelPath() {
    if (!currentProject || !_projDocPath || !/\.ipynb$/i.test(_projDocPath)) return null;
    const root = _projDocRoot || currentProject.path;
    if (root !== currentProject.path) return null;
    const workspace = _notebookWorkspaceContext(currentProject);
    return _workspaceRelativeNotebookPathOrNull(
      currentProject.path, _projDocPath, workspace.workspaceRoot,
    );
  }

  async function _reconcileOpenNotebook(relPath, workspaceId = null) {
    if (_currentOpenNotebookRelPath() !== relPath) return;
    if (workspaceId && workspaceId !== _projectWorkspaceId(currentProject)) return;
    await openProjectDoc(_projDocPath, { preserveScroll: true });
  }

  async function _handleNotebookExecutionEvent(event) {
    if (!event || !event.path) return;
    const relPath = String(event.path);
    const workspaceId = String(event.workspace || '');
    const liveKey = _nbLiveKey(workspaceId, relPath);
    const phase = String(event.phase || '');
    const terminal = phase === 'finished' || phase === 'failed' || phase === 'interrupted';
    if (phase === 'started' || phase === 'output' || phase === 'execution-count') {
      _nbLivePaths.add(liveKey);
    }
    if (terminal) _nbLivePaths.delete(liveKey);

    if (workspaceId && workspaceId !== _projectWorkspaceId(currentProject)) return;
    if (_currentOpenNotebookRelPath() !== relPath) return;
    if (phase === 'started' || terminal) {
      await _reconcileOpenNotebook(relPath, workspaceId);
      return;
    }
    if (phase !== 'output' && phase !== 'execution-count') return;

    const cellId = String(event.cell_id || '');
    if (!cellId) {
      await _reconcileOpenNotebook(relPath, workspaceId);
      return;
    }
    let wrap = document.querySelector(`.nb-cell-interactive[data-cell-id="${CSS.escape(cellId)}"]`);
    if (!wrap) {
      await _reconcileOpenNotebook(relPath, workspaceId);
      return;
    }

    const incomingSequence = Number(event.sequence);
    const currentSequence = Number(wrap.getAttribute('data-live-sequence'));
    if (!Number.isFinite(incomingSequence) || !Number.isFinite(currentSequence)
        || incomingSequence > currentSequence + 1) {
      await _reconcileOpenNotebook(relPath, workspaceId);
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
        await _reconcileOpenNotebook(relPath, workspaceId);
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

  // WS live refresh — re-render current view (home panel or project view)
  // on index-updated. The project view also has a 2s mtime poller as
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
        const reconnectWorkspaceId = reconnectNotebook && currentProject
          ? _projectWorkspaceId(currentProject) : null;
        hasConnected = true;
        if (reconnectNotebook) {
          _nbLiveEventChain = _nbLiveEventChain
            .then(() => _reconcileOpenNotebook(reconnectNotebook, reconnectWorkspaceId))
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
                     && !currentRepo && !_projDocEditing) {
            if (_projDocPath) openProjectDoc(_projDocPath, {preserveScroll: true});
            else {
              selfRefreshWorkbench();
              selfPopulateSidebar();
            }
          } else if (document.body.classList.contains('workspace-active')
                     && !currentRepo && !_projDocEditing) {
            if (_projDocPath) openProjectDoc(_projDocPath, {preserveScroll: true});
            else workspacePopulateSidebar();
          } else if (currentProject && currentProject.is_project
                     && !currentRepo && !_projDocEditing) {
            const liveNotebook = _currentOpenNotebookRelPath();
            if (_projDocPath) {
              const liveKey = _nbLiveKey(_projectWorkspaceId(currentProject), liveNotebook);
              if (!(liveNotebook && _nbLivePaths.has(liveKey))) {
                openProjectDoc(_projDocPath, {preserveScroll: true});
              }
            } else if (!document.body.classList.contains('self-active')) {
              showProjectInfo({preserveScroll: true});
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
