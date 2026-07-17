  let currentRepo = null;
  let currentDiffTab = 'uncommitted';
  let viewMode = 'split';
  let diffCache = { uncommitted: null, branch: null };

  let commitsList = [];
  let projectsList = [];
  let currentProject = null;
  let currentRepoInProject = null;

  const urlRepo = new URLSearchParams(location.search).get('repo');

  // Single-flight cache for `/api/repos`. On initial load the endpoint was
  // being hit THREE times in parallel (loadRepos + projTabsRefresh's
  // Promise.all + the urlProject/urlRepo branch) — each fires a blocking
  // `git rev-parse` subprocess per registered repo, and since the handler
  // is `async def` doing sync I/O the calls serialized on the event loop
  // (~260ms wasted on every reload). All three callers now go through
  // `fetchRepos()` which shares the in-flight promise; once it settles we
  // null the slot so subsequent timer-driven fires (every 5s) still refresh.
  let _reposInFlight = null;
  function fetchRepos() {
    if (_reposInFlight) return _reposInFlight;
    const p = fetch('/api/repos')
      .then(r => r.ok ? r.json() : [])
      .catch(() => []);
    _reposInFlight = p;
    p.finally(() => { if (_reposInFlight === p) _reposInFlight = null; });
    return p;
  }

  let _workspaceSwitching = false;
  // The id of the workspace the server is currently serving. Only one
  // workspace is ever active at a time, so every real project tab / active
  // dashboard row belongs to this same id — it's read by the project-tab
  // badge and by the dashboard row badge below.
  let currentWorkspaceId = null;
  async function workspaceRefresh() {
    try {
      const r = await fetch('/api/workspaces');
      if (!r.ok) return;
      const data = await r.json();
      currentWorkspaceId = data.active || null;
      const rows = Array.isArray(data.workspaces) ? data.workspaces : [];
      const sel = document.getElementById('workspaceSelect');
      if (!sel) return;
      sel.innerHTML = '';
      rows.forEach(row => {
        const opt = document.createElement('option');
        opt.value = row.id;
        opt.textContent = row.name || row.id;
        opt.title = row.path || '';
        opt.disabled = row.exists === false;
        opt.selected = row.active === true || row.id === data.active;
        sel.appendChild(opt);
      });
      if (!rows.length) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'No workspaces';
        sel.appendChild(opt);
      }
    } catch {}
  }

  async function workspaceUse(id) {
    if (!id || _workspaceSwitching) return;
    const sel = document.getElementById('workspaceSelect');
    _workspaceSwitching = true;
    if (sel) sel.disabled = true;
    try {
      const r = await fetch('/api/workspaces/use', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id}),
      });
      if (!r.ok) throw new Error(await r.text());
      // Switching workspace replaces the whole served index, so we always
      // land via a full reload. If the user is on the Workspace view, keep
      // them there: the reload re-runs initWorkspaceView against the newly
      // active workspace, so the tab's content follows the selection.
      location.href = document.body.classList.contains('workspace-active')
        ? '/?view=workspace'
        : '/';
    } catch (e) {
      if (sel) sel.disabled = false;
      _workspaceSwitching = false;
      console.error('workspace switch failed', e);
      workspaceRefresh();
    }
  }
  window.workspaceUse = workspaceUse;

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
        opt.value = p.name;
        opt.textContent = (p.is_project ? '\u{1F4E6} ' : '') + p.name;
        if (p.is_project) opt.style.color = '#58a6ff';
        if (p.name === (currentProject && currentProject.name)) opt.selected = true;
        sel.appendChild(opt);
      });
    } catch (err) {}
  }

  async function selectRepo(name) {
    if (!name) return;
    currentProject = projectsList.find(p => p.name === name);
    if (!currentProject) return;

    if (currentProject.is_project) projTabsSetOpen(currentProject.name, true);

    document.title = currentProject.name;
    // replaceState (not pushState): the caller (goToProject / popstate
    // handler / initial-load dispatch) has already settled the URL. A
    // pushState here would create a duplicate history entry, breaking
    // the back button. replaceState normalizes (e.g., ?repo= → ?project=)
    // without adding to history.
    const url = new URL(window.location);
    url.searchParams.set('project', currentProject.path);
    url.searchParams.delete('repo');
    history.replaceState(null, '', url);

    // Reset cached hold for the new project so the repo-tabs bar doesn't
    // flash stale state while showProjectInfo re-fetches it.
    _currentProjectHold = null;
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
        showProjectInfo({keepShell: !remembered});
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
        const res = await fetch(`/api/notebook?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(filepath)}`);
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
      const res = await fetch(`/api/file?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(filepath)}`);
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
        body: JSON.stringify({ repo: currentRepo, path: filepath, content }),
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
      const res = await fetch(`/api/file?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(deleteTarget)}`, { method: 'DELETE' });
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
  let showDotFiles = false;
  let showProjectDotFiles = false;

  function filterDotFiles(nodes) {
    return nodes.filter(n => !n.name.startsWith('.')).map(n => {
      if (n.type === 'dir' && n.children) {
        return { ...n, children: filterDotFiles(n.children) };
      }
      return n;
    });
  }

  function toggleDotFiles(checked) {
    showDotFiles = checked;
    loadProjectView();
  }

  function toggleProjectDotFiles(checked) {
    showProjectDotFiles = checked;
    showProjectInfo({preserveScroll: true});
  }

  async function loadProjectView() {
    if (!currentRepo) return;
    const sb = document.getElementById('sidebar');
    const content = document.getElementById('content');
    content.innerHTML = '<div class="file-viewer-empty">Select a file from the tree</div>';

    // Ensure branch diff (vs master) is loaded for change indicators
    if (!diffCache.branch) {
      try {
        const dres = await fetch(`/api/diff?repo=${encodeURIComponent(currentRepo)}&type=branch`);
        diffCache.branch = await dres.json();
        document.getElementById('countBranch').textContent = diffCache.branch.files.length;
        if (diffCache.branch.base_branch) document.getElementById('branchTabLabel').textContent = `vs ${diffCache.branch.base_branch}`;
      } catch (err) {}
    }

    // Load file tree
    try {
      const res = await fetch(`/api/tree?repo=${encodeURIComponent(currentRepo)}`);
      fileTree = await res.json();
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
      '<div style="padding:4px 16px"><label style="font-size:11px;color:#8b949e;cursor:pointer;user-select:none"><input type="checkbox" id="dotFilesToggle" onchange="toggleDotFiles(this.checked)" ' + (showDotFiles ? 'checked' : '') + ' style="margin-right:4px"> Include dotfiles</label></div>' +
      symlinkLegendHtml() +
      '<div class="sidebar-create"><button onclick="openCreateModal()">+ New File</button></div>' +
      '<ul class="tree-node">' + renderTreeNodes(filtered, changedFiles) + '</ul>';
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
          <div class="tree-dir${symlinkClass(node)}"${symlinkTitle(node)} onclick="toggleTreeDir(this)">
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
          <div class="tree-file${cls}${symlinkClass(node)}"${symlinkTitle(node)} onclick="openProjectFile('${node.path.replace(/'/g, "\\'")}')">
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

    try {
      const res = await fetch(`/api/file?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(filepath)}`);
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
        body: JSON.stringify({ repo: currentRepo, path: filepath, content: ta.value }),
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

  function renderNotebookCell(cell, status) {
    const statusCls = status && status !== 'unchanged' ? ` nb-${status}` : '';
    const statusLabel = status && status !== 'unchanged'
      ? `<span class="nb-status nb-status-${status}">${status}</span>` : '';
    const execCount = cell.execution_count ? `[${cell.execution_count}]` : '';

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
      const outs = cell.outputs.map(o => {
        if (o.type === 'image') {
          return `<div class="nb-output"><img src="data:image/png;base64,${o.content}"></div>`;
        } else if (o.type === 'html') {
          return `<div class="nb-output-html">${o.content}</div>`;
        } else if (o.type === 'error') {
          return `<div class="nb-output nb-output-error">${esc(o.content)}</div>`;
        } else {
          return `<div class="nb-output">${esc(o.content)}</div>`;
        }
      }).join('');
      outputsHtml = `<div class="nb-outputs">${outs}</div>`;
    }

    return `<div class="nb-cell${statusCls}">
      <div class="nb-cell-header">
        <span class="nb-type">${cell.cell_type}</span>
        <span class="nb-exec">${execCount}</span>
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
  function _cellDraftKey(relPath, index) { return 'nb-draft:' + relPath + ':' + index; }
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
  function _collapseKey(relPath, index) { return 'nb-collapse:' + relPath + ':' + index; }
  function _isOutputCollapsed(relPath, index) {
    try { return localStorage.getItem(_collapseKey(relPath, index)) === '1'; }
    catch (_) { return false; }
  }
  function _setOutputCollapsed(relPath, index, collapsed) {
    try {
      if (collapsed) localStorage.setItem(_collapseKey(relPath, index), '1');
      else localStorage.removeItem(_collapseKey(relPath, index));
    } catch (_) {}
  }

  // "Seen" state per cell — used to highlight new outputs the user hasn't
  // acknowledged yet (handy when Claude Code or a parallel run writes the
  // .ipynb in the background). The stored value is the highest exec count
  // the user has clicked through; if a render sees a higher count, the cell
  // gets a green-bordered "NEW" badge until the user clicks the outputs.
  function _seenKey(relPath, index) { return 'nb-seen:' + relPath + ':' + index; }
  function _baselineSeenIfNew(relPath, index, execCount) {
    if (execCount == null) return;
    try {
      if (localStorage.getItem(_seenKey(relPath, index)) == null) {
        localStorage.setItem(_seenKey(relPath, index), String(execCount));
      }
    } catch (_) {}
  }
  function _isCellSeen(relPath, index, execCount) {
    if (execCount == null) return true;
    try {
      const stored = localStorage.getItem(_seenKey(relPath, index));
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
  function _markCellSeen(relPath, index, execCount) {
    if (execCount == null) return;
    try { localStorage.setItem(_seenKey(relPath, index), String(execCount)); } catch (_) {}
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

  function renderNbCellInteractive(cell, index, relPath, opts) {
    opts = opts || {};
    // `opts.pending` is a client-side draft (Run button not yet sent).
    // `cell.metadata.lab_pending` is server-side: the nb_exec endpoint
    // wrote a placeholder while the Darwin call is in flight. Both get
    // the same .nb-cell-pending visual frame so the user can't tell
    // which side started the run — the "[*]" gutter + running CSS look
    // identical.
    const serverPending = !!(cell && cell.metadata && cell.metadata.lab_pending === true);
    const pending = !!opts.pending || serverPending;
    const isCode = cell.cell_type === 'code';
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
      const outs = cell.outputs.map(o => {
        if (o.type === 'image') return `<div class="nb-output"><img src="data:image/png;base64,${o.content}"></div>`;
        if (o.type === 'html') return `<div class="nb-output-html">${o.content}</div>`;
        if (o.type === 'error') return `<div class="nb-output nb-output-error">${esc(o.content)}</div>`;
        return `<div class="nb-output">${esc(o.content)}</div>`;
      }).join('');
      const collapsed = !opts.pending && _isOutputCollapsed(relPath, index);
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
    const idxAttr = pending ? 'new' : String(index);
    const pendingId = pending ? (opts.pendingId || '') : '';
    const pendingAttr = pendingId ? ` data-pending-id="${esc(pendingId)}"` : '';
    const pendingInsertAt = (pending && opts.insertAt != null) ? String(opts.insertAt) : '';
    const insertAtAttr = pendingInsertAt !== '' ? ` data-insert-at="${pendingInsertAt}"` : '';
    const highlighted = _highlightCellSource(source);
    const execCountNum = (cell.execution_count != null) ? cell.execution_count : '';
    const unseen = !pending && outputsHtml && !_isCellSeen(relPath, index, cell.execution_count);
    const unseenCls = unseen ? ' nb-cell-unseen' : '';
    const newBadge = unseen
      ? `<span class="nb-cell-new-badge" title="New outputs — click anywhere on the output to acknowledge">NEW</span>`
      : '';
    return `<div class="nb-cell nb-cell-interactive${pendingCls}${unseenCls}" data-cell-index="${idxAttr}"${pendingAttr}${insertAtAttr} data-exec-count="${execCountNum}">
      <div class="nb-cell-header">
        <span class="nb-type">code</span>
        <span class="nb-exec">${execCount}</span>
        ${newBadge}
        <div class="nb-cell-actions">
          <span class="nb-cell-busy" style="display:none">running…</span>
          <button class="nb-cell-copy-src" type="button" title="Copy cell source to clipboard">⧉ copy</button>
          <button class="nb-cell-run" type="button" title="Run (Cmd/Ctrl+Enter)">▶ Run</button>
          <button class="nb-cell-del" type="button" title="${pending ? 'Discard draft' : 'Delete cell'}">✕</button>
        </div>
      </div>
      <div class="nb-cell-edit-wrap">
        <pre class="nb-cell-edit-highlight hljs" aria-hidden="true"><code class="hljs">${highlighted}</code></pre>
        <textarea class="nb-cell-edit-area" spellcheck="false" rows="${rowsHint}"
          placeholder="${pending ? 'Type code, then Cmd/Ctrl+Enter or click Run…' : ''}">${esc(source)}</textarea>
      </div>
      ${outputsHtml}
    </div>`;
  }

  function bindNbCellInteractive(wrap, relPath, filepath, onPendingRemoved) {
    if (!wrap || !wrap.classList.contains('nb-cell-interactive')) return;
    const ta = wrap.querySelector('.nb-cell-edit-area');
    if (!ta) return;  // markdown cell
    const runBtn = wrap.querySelector('.nb-cell-run');
    const delBtn = wrap.querySelector('.nb-cell-del');
    const busy = wrap.querySelector('.nb-cell-busy');
    const idxAttr = wrap.getAttribute('data-cell-index');
    const isPending = idxAttr === 'new';
    const cellIndex = isPending ? null : parseInt(idxAttr, 10);
    const pendingId = wrap.getAttribute('data-pending-id') || null;

    // Restore in-flight draft. Committed cells use a per-index draft key;
    // pending cells persist via the path-scoped pending list so they survive
    // navigation away and back.
    const draftKey = isPending ? null : _cellDraftKey(relPath, cellIndex);
    if (draftKey) {
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

    function setRunning(on) {
      runBtn.disabled = on;
      delBtn.disabled = on;
      busy.style.display = on ? '' : 'none';
      const wasRunning = wrap.classList.contains('nb-cell-running');
      wrap.classList.toggle('nb-cell-running', on);
      // Auto-scroll only on the idle → running transition. Re-renders that
      // re-create an already-running cell don't re-scroll.
      if (on && !wasRunning) {
        try { wrap.scrollIntoView({ block: 'center', behavior: 'smooth' }); } catch (_) {}
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
        const body = { path: relPath, code };
        if (cellIndex != null) body.cell_index = cellIndex;
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
          body: JSON.stringify({ path: relPath, cell_index: cellIndex }),
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
        _setOutputCollapsed(relPath, cellIndex, nowCollapsed);
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
        if (!isNaN(execCount)) _markCellSeen(relPath, cellIndex, execCount);

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
    if (!btn) return;
    const original = btn.textContent;
    btn.textContent = ok ? '✓ copied' : '✗ copy failed';
    btn.disabled = true;
    setTimeout(() => { btn.textContent = original; btn.disabled = false; }, 1200);
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
  async function bindNbRestartKernel(container, relPath, filepath) {
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
          body: JSON.stringify({ path: relPath }),
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

  function bindNbAddCellButton(container, relPath, filepath) {
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
      bindNbCellInteractive(node, relPath, filepath);
      const ta = node.querySelector('.nb-cell-edit-area');
      if (ta) ta.focus();
    });
  }

  // Hover-revealed "+ insert cell" bars between every pair of cells. Click
  // inserts a pending cell at that position (data-insert-at), which on Run
  // POSTs `insert_at` so the new cell lands between existing cells instead
  // of being appended at the end.
  function bindNbCellInserters(container, relPath, filepath) {
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
        bindNbCellInteractive(node, relPath, filepath);
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
      const res = await fetch(`/api/notebook?repo=${encodeURIComponent(currentRepo)}&path=${encodeURIComponent(filepath)}`);
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

  // Cached hold metadata for the currently-open project. Populated by
  // showProjectInfo/showProjectDashboard whenever project-info is fetched,
  // so renderRepoTabs can reflect snooze state without re-fetching.
  let _currentProjectHold = null;

  // ─── Focus mode ─────────────────────────────────────────────────────────
  // Hides the topbar (Home / workspace picker / project tabs / gear) and the
  // project attrs bar so only the Overview strip and the content remain.
  // Toggled by the button in the repo-tabs bar; Esc exits; persists across
  // reloads via localStorage.
  const FOCUS_MODE_KEY = 'labFocusMode';
  function applyFocusMode(on) {
    document.body.classList.toggle('focus-mode', !!on);
    try { localStorage.setItem(FOCUS_MODE_KEY, on ? '1' : '0'); } catch {}
    // Re-render the strip so the button label flips.
    try { if (currentProject) renderRepoTabs(); } catch {}
  }
  function toggleFocusMode() {
    applyFocusMode(!document.body.classList.contains('focus-mode'));
  }
  window.toggleFocusMode = toggleFocusMode;
  try { if (localStorage.getItem(FOCUS_MODE_KEY) === '1') document.body.classList.add('focus-mode'); } catch {}
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || !document.body.classList.contains('focus-mode')) return;
    // Don't steal Esc from terminals, form fields, or open modals.
    const t = e.target;
    if (t && t.closest && t.closest('input, textarea, select, [contenteditable="true"], .term-panel')) return;
    if (document.querySelector('.modal-overlay.active')) return;
    applyFocusMode(false);
  });

  function renderRepoTabs() {
    const container = document.getElementById('repoTabs');
    if (!currentProject || (!currentProject.is_project && currentProject.repos.length <= 1)) {
      container.style.display = 'none';
      document.body.classList.remove('has-repo-tabs');
      return;
    }

    container.style.display = 'flex';
    document.body.classList.add('has-repo-tabs');

    let html = '';

    // A server (proxy) view counts as its own tab — while one is open the
    // Overview tab must not also read as active.
    const proxyOpen = typeof _projDocPath === 'string' && _projDocPath.startsWith('__proxy__/');

    if (currentProject.is_project) {
      const dashActive = (!currentRepo && !proxyOpen) ? ' active' : '';
      html += `<button class="repo-tab${dashActive}" onclick="showProjectDashboard()" style="font-weight:600">&#x1F4CB; Overview</button>`;
    }

    html += currentProject.repos.map(r => {
      const active = r.path === currentRepo ? ' active' : '';
      return `<button class="repo-tab${active}" onclick="selectProjectRepo('${r.path}')">${r.name} <span style="color:#484f58;font-size:10px">${r.branch}</span></button>`;
    }).join('');

    // One tab per declared server (project.json proxies) — clicking it opens
    // the same inline iframe view as the sidebar Servers entry. The list
    // comes from the sidebar payload cache; on a cold load it's empty until
    // _refreshProjectSidebar fetches project-info and re-calls us.
    if (currentProject.is_project) {
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

    // Snooze controls — right-aligned on the same bar as Overview. Always
    // render the Snooze button for a project; when a hold is active also
    // (Snooze controls moved to the project attrs bar above; the repo-tabs
    // bar stays focused on repo navigation only.)

    // Focus mode toggle — right-aligned; stays reachable while everything
    // above this strip is hidden.
    const focusOn = document.body.classList.contains('focus-mode');
    html += `<button class="repo-tab focus-toggle" onclick="toggleFocusMode()" title="${focusOn ? 'Show tabs and status bar again (Esc)' : 'Hide the tab strip and status bar'}">${focusOn ? '✖ Exit focus' : '⛶ Focus mode'}</button>`;

    container.innerHTML = html;
  }

  let _projDocPath = null;
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
  // Same idea for the project attrs bar (the row with status / P:N /
  // Due / LOE / description / Snooze controls). Keyed by project id.
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

  let _docModalEscHandler = null;

  async function openProjectDocModal(filepath, { editing = false } = {}) {
    if (!currentProject) return;
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
    const _stillActiveNav = () => (
      _projDocPath === filepath
      && currentProject
      && currentProject.path === _navProjectPath
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
      const src = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`;
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
        const r = await fetch(`/api/project-file?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`);
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
    const _stillActiveNav = () => (
      _projDocPath === filepath
      && currentProject
      && currentProject.path === _navProjectPath
    );

    // Image files
    const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
    if (imageExts.some(ext => filepath.toLowerCase().endsWith(ext))) {
      if (!_stillActiveNav()) return;
      const src = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`;
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
      const src = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`;
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
      const src = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`;
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
      const absKey = currentProject.path + '/' + filepath;
      const mode = getHtmlViewPref(absKey);
      _projectRenderHtml(container, filepath, absKey, mode);
      return;
    }

    // Notebooks: render cells via /api/nb — activateNotebookScripts runs post-inject.
    // A trailing editor lets you POST new cells to /api/nb/exec; the resulting
    // .ipynb write triggers the watcher, every open viewer re-renders.
    if (filepath.toLowerCase().endsWith('.ipynb')) {
      try {
        let relPath = currentProject.path + '/' + filepath;
        const rootPrefix = SELF_REPO_PATH.endsWith('/') ? SELF_REPO_PATH : SELF_REPO_PATH + '/';
        if (relPath.startsWith(rootPrefix)) relPath = relPath.slice(rootPrefix.length);

        // A brand-new notebook 404s on /api/nb; treat that as "empty, ready to
        // receive its first cell" rather than an error.
        const [nbRes, sessRes] = await Promise.all([
          fetch(`/api/nb?path=${encodeURIComponent(relPath)}`),
          fetch(`/api/nb/session?path=${encodeURIComponent(relPath)}`),
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
        const session = sessRes.ok ? (await sessRes.json()).session : '';

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
          (nb.cells || []).forEach((c, i) => _baselineSeenIfNew(relPath, i, c.execution_count));
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
        const sessionBadge = session
          ? `<span title="Darwin kernel pinned to this file" style="font-family:ui-monospace,monospace;font-size:11px;background:var(--bg-tertiary);color:var(--accent);padding:1px 6px;border-radius:3px">kernel: ${esc(session)}</span>`
          : '';
        const restartBtnHtml = session
          ? `<button class="nb-restart-kernel" type="button" title="Restart kernel (wipes variables, like Jupyter's Restart Kernel)">↻ Restart kernel</button>`
          : '';
        const header = `<div style="display:flex;align-items:center;gap:8px;margin-bottom:16px"><span style="font-size:12px;color:var(--text-dim);font-family:ui-monospace,monospace;flex:1">${esc(filepath)}</span>${sessionBadge}${restartBtnHtml}<span style="font-size:11px;color:var(--text-secondary)">${updatedLabel}</span></div>`;
        const pendingList = _readPending(relPath);
        const realCells = nb.cells || [];
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
          cellsHostHtml += renderNbCellInteractive(c, i, relPath, {
            queuePos: _pendingPositions[i] || null,
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
        container.innerHTML = `<div style="padding:24px">${header}<div class="nb-container">${cellsHostHtml}</div>${addBtnHtml}</div>`;
        activateNotebookScripts(container);
        // Bind every interactive cell + inserters + the trailing add-cell
        // button + restart.
        container.querySelectorAll('.nb-cell-interactive').forEach((wrap) => {
          bindNbCellInteractive(wrap, relPath, filepath);
        });
        bindNbCellInserters(container, relPath, filepath);
        bindNbAddCellButton(container, relPath, filepath);
        bindNbRestartKernel(container, relPath, filepath);
        // Auto-scroll the currently-running cell into view. The
        // server-side placeholder lands here as .nb-cell-pending with
        // its [*] gutter; bring it to the user's focus so they can see
        // what's executing even when the run was kicked off from a
        // terminal / curl rather than the in-UI Run button.
        const runningCell = container.querySelector('.nb-cell-interactive.nb-cell-running');
        if (runningCell) {
          runningCell.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
      const cacheKey = _projDocCacheKey(currentProject.path, filepath);
      const cached = _projDocCache.get(cacheKey);
      if (cached) {
        _projDocContent = cached.content;
        _projComments = cached.comments;
        _projDocArtifact = cached.artifact;
        if (!_stillActiveNav()) return;
        renderProjectDoc(filepath, container);
      }
      const [fileRes, commentsRes, infoRes] = await Promise.all([
        fetch(`/api/project-file?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`),
        fetch(`/api/project-comments?path=${encodeURIComponent(currentProject.path)}`),
        fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`),
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

  async function openProjectDoc(filepath, {preserveScroll = false} = {}) {
    if (!currentProject) return;
    // Pseudo-paths starting with `__proxy__/` are not real files — they
    // refer to a declared local-dev-server proxy. Route to the iframe
    // renderer; everything else (active highlight, last-opened memory)
    // is handled inside openProjectProxy.
    if (typeof filepath === 'string' && filepath.startsWith('__proxy__/')) {
      const name = filepath.slice('__proxy__/'.length);
      return openProjectProxy(name);
    }
    _projDocPath = filepath;
    _projDocEditing = false;
    setLastProjectDoc(currentProject.path, filepath);
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
      const cacheKey = _projDocCacheKey(currentProject.path, filepath);
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
      );
      // Notebooks, images, video, and HTML iframes have no meaningful _projDocContent
      // to diff against — delegate straight to _renderDocInto so they get the correct
      // renderer (its per-type guards keep live players/iframes unmolested).
      const lower = filepath.toLowerCase();
      const imageExts = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp'];
      const videoExts = ['.mp4', '.webm', '.mov', '.m4v'];
      if (lower.endsWith('.ipynb') || lower.endsWith('.html') || lower.endsWith('.pdf') || imageExts.some(ext => lower.endsWith(ext)) || videoExts.some(ext => lower.endsWith(ext))) {
        await _renderDocInto(filepath, content, { preserveScroll: true });
        if (!_stillActiveNav()) return;
        content.scrollTop = prevScroll;
        return;
      }
      try {
        const [fileRes, commentsRes, infoRes] = await Promise.all([
          fetch(`/api/project-file?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(filepath)}`),
          fetch(`/api/project-comments?path=${encodeURIComponent(currentProject.path)}`),
          fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`),
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
        _projDocCache.set(_projDocCacheKey(_navProjectPath, filepath),
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
  // routes/proxy.py. Declared in project.json:
  //   "proxies": [{"name": "frontend", "host": "localhost", "port": 3000, "path": "/"}]
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

  function _proxyMountPath(projectId, name) {
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
    return _proxyMountPath(projectId, name) + initial;
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
  async function openProjectDocAndJumpToUnseen(filepath) {
    await openProjectDoc(filepath);
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
              href = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(resolvedHref)}&t=${_lastProjectMtime || Date.now()}`;
            }
            return `<img src="${href}" alt="${text || ''}"${title ? ` title="${title}"` : ''} style="max-width:100%;border-radius:4px;margin:8px 0">`;
          };
          rendered = marked.parse(_projDocContent, { renderer });
          // Rewrite relative src in iframes/embeds to use project-asset API
          rendered = rendered.replace(/<iframe([^>]*) src="([^"]+)"([^>]*)>/g, (match, pre, src, post) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            const newSrc = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(resolved)}`;
            return `<iframe${pre} src="${newSrc}"${post} onload="applyIframeDarkMode(this)">`;
          });
          // Also rewrite other relative src (img etc) not already handled
          rendered = rendered.replace(/ src="([^"]+)"/g, (match, src) => {
            if (src.startsWith('http') || src.startsWith('data:') || src.startsWith('/api/')) return match;
            const dir = filepath.includes('/') ? filepath.substring(0, filepath.lastIndexOf('/')) : '';
            const resolved = _resolveRelPath(dir, src);
            return ` src="/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(resolved)}"`;
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
        body: JSON.stringify({ path: currentProject.path, file: filepath, text: _pendingCommentText, comment }),
      });
      _pendingCommentText = '';
      _pendingCommentMark = null;  // the upcoming re-render rebuilds the DOM from scratch
      openProjectDoc(filepath);
    } catch (err) { alert('Error: ' + err.message); }
  }

  function startProjectDocEdit() {
    if (!_projDocPath) return;
    openProjectDocModal(_projDocPath, { editing: true });
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
        body: JSON.stringify({ path: currentProject.path, file: filepath, content: ta.value }),
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
        body: JSON.stringify({ path: currentProject.path, comment_id: commentId }),
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
        img.src = `/api/project-asset?path=${encodeURIComponent(currentProject.path)}&file=${encodeURIComponent(resolved)}`;
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
    currentRepo = null;
    currentRepoInProject = null;
    // Clear the doc path BEFORE rendering tabs — the Overview tab's active
    // state (and the sidebar view suffix) both read it. User explicitly
    // chose Dashboard, so also drop the remembered doc for this project.
    if (currentProject) setLastProjectDoc(currentProject.path, null);
    _projDocPath = null;
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
    currentRepoInProject = currentProject.repos.find(r => r.path === repoPath);
    currentRepo = repoPath;
    // The diff view replaces any open doc/server view — clear the doc path
    // so the server tab un-highlights and the sidebar preference resets.
    _projDocPath = null;
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
          row.appendChild(badge);
        }
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
    const path = currentProject.path;
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
      if (currentProject && currentProject.path === path) _sidebarApplyGitStatus(entry);
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

    // Warm switch: when no `_data` override is passed but the cache has
    // a payload for this project, paint instantly from the cache and
    // then reconcile against the server in the background. The
    // recursive call with `_data` set skips the fetches entirely so
    // the second paint only re-runs the render body (no network).
    if (!_data) {
      const cachedPayload = _projectSidebarCache.get(projectPath);
      if (cachedPayload) {
        // Synchronous warm paint — recursive call returns a Promise but
        // because `_data` short-circuits both fetches, all the render
        // work happens in the synchronous prefix.
        _refreshProjectSidebar({preserveScroll, _data: cachedPayload});
        // Background reconcile.
        Promise.resolve().then(async () => {
          try {
            const filesRes = await fetch(`/api/project-files?path=${encodeURIComponent(projectPath)}&include_dotfiles=${showProjectDotFiles}`);
            const files = await filesRes.json();
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
            const fresh = {files, pinned, references, proxies};
            const prev = _projectSidebarCache.get(projectPath);
            _projectSidebarCache.set(projectPath, fresh);
            // Re-render only if (a) the data actually changed and (b)
            // the user is still on this project.
            if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
            if (!currentProject || currentProject.path !== projectPath) return;
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
        const filesRes = await fetch(`/api/project-files?path=${encodeURIComponent(currentProject.path)}&include_dotfiles=${showProjectDotFiles}`);
        files = await filesRes.json();
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
        _projectSidebarCache.set(projectPath, {files, pinned: pinnedNames, references, proxies});
      }
      const fileEntries = (files || []).filter(f => f && f.type !== 'dir');
      const dirEntries = (files || []).filter(f => f && f.type === 'dir');
      const pinnedSet = new Set(pinnedNames);
      const filesByName = new Map(fileEntries.map(f => [f.name, f]));
      const pinnedFiles = pinnedNames.filter(n => fileEntries.some(f => f.name === n));
      const otherFiles = fileEntries.filter(f => !pinnedSet.has(f.name));

      // "Meta" files are demoted to a bottom section so the sidebar reads as
      // a working list of docs first, plumbing second. Still visible; just
      // out of the way of daily navigation.
      const META_FILES = new Set(['project.json', 'tasks.json', 'comments.json', 'CLAUDE.md']);
      // Folders that should open automatically — docs is where 95% of the
      // reading lives, so showing it collapsed by default hides everything.
      const AUTO_OPEN_FOLDERS = new Set(['docs', 'notebooks', 'links']);

      const metaFiles = otherFiles.filter(f => !f.path.includes('/') && META_FILES.has(f.name));
      const mainFiles = otherFiles.filter(f => !(f.path === f.name && META_FILES.has(f.name)));

      // Active-file highlighting is baked into the rendered HTML (data-filepath
      // + .active class) so periodic sidebar rebuilds — from the mtime poller
      // and the index-updated WS event — preserve the red selection bar
      // instead of dropping it and waiting for openProjectDoc to re-add it,
      // which made the selection blink.
      const activePath = _projDocPath || null;
      const dashActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${dashActive}" data-dashboard="1" onclick="showProjectDashboard()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">&#x1F4CB; Dashboard</span></a>`;
      sbHtml += '<div style="padding:4px 16px"><label style="font-size:11px;color:var(--text-secondary);cursor:pointer;user-select:none"><input type="checkbox" id="projectDotFiles" onchange="toggleProjectDotFiles(this.checked)" ' + (showProjectDotFiles ? 'checked' : '') + ' style="margin-right:4px">Show hidden files</label></div>';
      sbHtml += symlinkLegendHtml();
      pinnedFiles.forEach(name => {
        const f = filesByName.get(name) || {name, path: name};
        const safeName = name.replace(/'/g, "\\'");
        const label = name.replace(/\.md$/, '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        const activeCls = activePath === name ? ' active' : '';
        sbHtml += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(name)}"${symlinkTitle(f)} onclick="openProjectDoc('${safeName}')" ondblclick="event.stopPropagation();openProjectDocModal('${safeName}')" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">${symlinkMarker(f)}&#x1F4CC; ${label}</span><span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${safeName}')" title="Unpin">&#x2716;</button></span></a>`;
      });

      // Servers — proxied local dev servers declared in project.json
      // under ``proxies: [{name, host?, port, path?}]``. Each entry opens
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
      const _projTreeScope = 'project:' + (currentProject && currentProject.name ? currentProject.name : '');
      if (mainFiles.length > 0 || dirEntries.length > 0) {
        sbHtml += '<div class="sidebar-title">Files</div>';
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
            html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(_projTreeScope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">\u25B6</span>${symlinkMarker(d)}${esc(folder)}/</div>`;
            html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
            html += renderTree(node[folder], depth + 1, fullPath);
            html += '</div>';
          });
          // Then files
          treeFiles(node).forEach(f => {
            const safePath = f.path.replace(/'/g, "\\'");
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
              dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openProjectDocAndJumpToUnseen('${safePath}')"></span>`;
            }
            const activeCls = activePath === f.path ? ' active' : '';
            html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}')" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}')"><span class="sidebar-fname">${dotHtml}${icon}${fname}</span><span class="sidebar-actions"><button onclick="event.stopPropagation();togglePin('${f.name}')" title="Pin to top">&#x1F4CC;</button></span></a>`;
          });
          return html;
        }
        sbHtml += renderTree(tree, 0, '');
      }

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

      // Plumbing — project.json, tasks.json, CLAUDE.md, plus a deep-link
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
          sbHtml += `<a class="sidebar-file sidebar-file-meta${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}')" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}')" style="opacity:.55"><span class="sidebar-fname">${icon}${fname}</span></a>`;
        });
      } else {
        sbHtml += '<div class="sidebar-title" style="margin-top:14px;opacity:.7">Meta</div>';
      }
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
      const sharedClaudeFid = 'sf-claude-' + Math.random().toString(36).substr(2, 6);
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
      const sharedCodeFid = 'sf-code-' + Math.random().toString(36).substr(2, 6);
      const _shCdOpen = _treeIsOpen('shared-code', 'code', false);
      const _shCdArrow = _shCdOpen ? ' open' : '';
      const _shCdChildren = _shCdOpen ? ' open' : '';
      sbHtml += `<div class="sidebar-folder sidebar-file-meta" data-tree-scope="shared-code" data-tree-path="code" data-tree-target="${sharedCodeFid}" onclick="_treeToggleFolder(this)" title="content/code/ — source for code-* skills" style="opacity:.7"><span class="folder-arrow${_shCdArrow}">▶</span>code/ (shared)</div>`;
      sbHtml += `<div class="sidebar-folder-children${_shCdChildren}" id="${sharedCodeFid}"><div style="padding:6px 16px 6px 32px;font-size:11px;color:var(--text-dim)">loading…</div></div>`;
      sidebar.innerHTML = sbHtml;
      if (preserveScroll) sidebar.scrollTop = prevSidebarScroll;
      // Server tabs on the top bar are derived from the same proxies list
      // rendered above — re-sync so they appear/update as soon as the list
      // is known (cold load fetch or background reconcile).
      renderRepoTabs();
      // Populate both `.claude/` and `code/` placeholders from one
      // /api/cerebro/tree fetch.
      _populateSharedMetaPlaceholders(sharedClaudeFid, sharedCodeFid);
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
            <h1 style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(currentProject.name || 'Project')}</h1>
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

  async function showProjectInfo({preserveScroll = false, keepShell = false} = {}) {
    if (!currentProject || !currentProject.is_project) return;
    const content = document.getElementById('content');
    const prevContentScroll = preserveScroll ? content.scrollTop : 0;
    if (!preserveScroll && !keepShell) content.innerHTML = '<div class="loading">Loading project dashboard...</div>';
    await _refreshProjectSidebar({preserveScroll});

    try {
      const [infoRes, actionsRes, onepagerRes, artifactsRes, alertsRes] = await Promise.all([
        fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`),
        fetch(`/api/project-actions?path=${encodeURIComponent(currentProject.path)}`),
        fetch(`/api/project-onepager?path=${encodeURIComponent(currentProject.path)}`),
        fetch(`/api/project-artifacts?path=${encodeURIComponent(currentProject.path)}`),
        fetch(`/api/project-alerts?path=${encodeURIComponent(currentProject.path)}`),
      ]);

      const info = await infoRes.json();
      const actions = await actionsRes.json();
      const onepager = await onepagerRes.json();
      const artifacts = await artifactsRes.json();
      const alerts = await alertsRes.json();

      // Repo tabs (top bar) needs hold state to render the right-hand
      // Snooze/Reschedule/Clear cluster. Cache and re-render.
      _currentProjectHold = info.hold || null;
      renderRepoTabs();

      // Status color
      const statusColor = info.status === 'active' ? '#3fb950' : info.status === 'paused' ? '#d29922' : '#8b949e';

      let html = '<div style="padding:24px;max-width:900px">';

      // Header with prominent TLDR. The Snooze controls live on the
      // top repo-tabs bar (see renderRepoTabs); keep this header focused
      // on identity + description.
      const snoozeInfo = holdState(info.hold);
      html += `<div style="margin-bottom:28px">`;
      html += `<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">`;
      html += `<h1 style="color:var(--text-primary);font-size:28px;font-weight:600;margin:0;flex:1">${esc(info.name)}</h1>`;
      html += `<span style="color:${statusColor};font-size:13px;font-weight:600;background:${statusColor}18;padding:2px 10px;border-radius:12px">${info.status}</span>`;
      html += `<button onclick="copyForGDocs(event)" style="background:var(--bg-tertiary);color:var(--text-secondary);border:1px solid var(--border);padding:4px 12px;border-radius:4px;font-size:12px;cursor:pointer">&#x1F4CB; Copy</button>`;
      html += `</div>`;
      if (info.description) {
        html += `<p style="color:var(--text-primary);font-size:20px;line-height:1.7;margin-bottom:16px">${esc(info.description)}</p>`;
      }
      // Hold banner — surfaces reason + URL + resurface time inline with the
      // header, so it's the first thing you see when reopening a snoozed
      // project. Styled yellow when the timer has passed (ready-for-review).
      if (info.hold && snoozeInfo.state !== 'none') {
        const color = snoozeInfo.state === 'ready' ? '#d29922' : 'var(--accent)';
        const icon = snoozeInfo.state === 'ready' ? '&#x23F0;' : '&#x1F4A4;';
        const when = snoozeInfo.state === 'ready'
          ? `ready for review (timer hit ${fmtRelative(snoozeInfo.ms)} ago)`
          : `resurfaces in ${fmtRelative(snoozeInfo.ms)}`;
        const reason = info.hold.reason ? ` · ${esc(info.hold.reason)}` : '';
        const url = info.hold.url
          ? ` · <a href="${esc(info.hold.url)}" target="_blank" style="color:${color}">&#x1F517; ${esc(info.hold.url)}</a>`
          : '';
        html += `<div style="border:1px solid ${color};background:${color}18;border-radius:6px;padding:10px 14px;margin-bottom:16px;font-size:13px;color:${color}">${icon} ${when}${reason}${url}</div>`;
      }
      html += `<div style="display:flex;gap:16px;font-size:13px;color:var(--text-dim)">`;
      html += `<span>Created: ${info.created}</span>`;
      html += `<span>Updated: ${info.updated}</span>`;
      html += `</div></div>`;

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
  let _setDraft = null;      // {defaultAgent, model, theme} while the modal is open
  let _setProjDraft = null;  // {agent, model} override for the active project

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
    for (const a of Object.keys(AGENT_LABELS)) {
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
      Object.keys(AGENT_LABELS).map(a => ({ value: a, label: AGENT_LABELS[a] })),
      _setDraft.defaultAgent,
      (a) => { _setDraft.defaultAgent = a; _renderSettingsGlobal(); });
    _renderAutopilotRow();
    const modelSel = document.getElementById('setModel');
    _fillModelSelect(modelSel, _setDraft.defaultAgent, _setDraft.model);
    modelSel.onchange = (e) => { _setDraft.model = e.target.value || null; };
    _buildSeg('setThemeSeg',
      [{ value: 'dark', label: 'Dark' }, { value: 'light', label: 'Light' }],
      _setDraft.theme,
      (t) => { _setDraft.theme = t; applyTheme(t); _renderSettingsGlobal(); });
  }

  async function openSettings() {
    _setDraft = {
      defaultAgent: _settings.defaultAgent || 'claude',
      model: _settings.model || null,
      theme: document.body.classList.contains('light-mode') ? 'light' : 'dark',
      autopilot: { ...(_settings.autopilot || {}) },
    };
    _renderSettingsGlobal();

    // Per-project override (only when a real project tab is active).
    const sec = document.getElementById('setProjectSection');
    _setProjDraft = null;
    const pid = (typeof currentProject !== 'undefined' && currentProject) ? currentProject.name : null;
    if (pid) {
      document.getElementById('setProjectName').textContent = pid;
      sec.style.display = 'flex';
      const pAgent = document.getElementById('setProjectAgent');
      const pModel = document.getElementById('setProjectModel');
      pAgent.value = '';
      _fillModelSelect(pModel, _setDraft.defaultAgent, '');
      try {
        const r = await fetch('/api/projects/' + encodeURIComponent(pid));
        if (r.ok) {
          const proj = await r.json();
          _setProjDraft = { agent: proj.agent || '', model: proj.model || '' };
          pAgent.value = _setProjDraft.agent || '';
          _fillModelSelect(pModel, _setProjDraft.agent || _setDraft.defaultAgent, _setProjDraft.model);
        }
      } catch {}
      pAgent.onchange = (e) => {
        _setProjDraft = _setProjDraft || { agent: '', model: '' };
        _setProjDraft.agent = e.target.value;
        _fillModelSelect(pModel, e.target.value || _setDraft.defaultAgent, _setProjDraft.model);
      };
      pModel.onchange = (e) => {
        _setProjDraft = _setProjDraft || { agent: '', model: '' };
        _setProjDraft.model = e.target.value;
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
      const r = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          defaultAgent: _setDraft.defaultAgent,
          model: _setDraft.model || null,
          theme: _setDraft.theme,
          autopilot: _setDraft.autopilot || {},
        }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || 'save failed');
      _settings = await r.json();
      applyTheme(_settings.theme);

      const pid = (typeof currentProject !== 'undefined' && currentProject) ? currentProject.name : null;
      if (_setProjDraft && pid) {
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
  let projTabsHot = [];           // project ids with >=1 live tmux session
  let projTabsAll = [];           // registered-project list (from /api/repos)
  let projTabsAttention = [];     // project ids where every claude is idle
  let projTabsRefreshTimer = null;
  let projTabsOrder = [];        // user-chosen order (from /api/ui/tab-order)
  let projTabsPseudoOpen = [];   // open pseudo-tabs from /api/ui/pseudo-tabs
  let projTabsDragPid = null;    // pid currently being dragged

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

  // Project tabs the user has opened. Source of truth is `tab_open` in
  // each project's project.json (exposed by /api/repos). Pseudo-tabs such
  // as Logs store their open flag in workspace-local .lab/state/ui-state.json.
  function projTabsOpenIds() {
    return (projTabsAll || []).filter(p => p && p.tab_open).map(p => p.name);
  }
  function projTabsPseudoOpenIds() {
    return (projTabsPseudoOpen || []).filter(id =>
      id === LOGS_PROJECT_ID || id === SELF_PROJECT_ID
    );
  }
  async function projTabsSetOpen(pid, open) {
    if (!pid) return;
    try {
      await fetch('/api/projects/' + encodeURIComponent(pid) + '/tab', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({open: !!open}),
      });
    } catch (e) { /* best-effort; next refresh will pick up the truth */ }
    // Reflect locally so the strip updates without waiting for /api/repos.
    const p = (projTabsAll || []).find(x => x && x.name === pid);
    if (p) p.tab_open = !!open;
  }
  async function projTabsSetPseudoOpen(pid, open) {
    if (!(pid === LOGS_PROJECT_ID || pid === SELF_PROJECT_ID)) return;
    const ids = new Set(projTabsPseudoOpenIds());
    if (open) ids.add(pid);
    else ids.delete(pid);
    projTabsPseudoOpen = Array.from(ids);
    if (typeof projTabsRender === 'function') projTabsRender();
    try {
      await fetch('/api/ui/pseudo-tabs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tab_id: pid, open: !!open}),
      });
    } catch (e) { /* best-effort; next refresh will pick up the truth */ }
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

  // Code Search fixed view: also a pseudo-project. The actual per-repo
  // terminal panel uses `__cs_<repo>__` ids (see _csProjectId); this
  // constant is only for the single topbar tab entry.
  const CODE_SEARCH_PROJECT_ID = '__code_search__';

  // Workspace fixed view: management surface for the ACTIVE workspace (the
  // one selected in the top-left dropdown). Pseudo-project rooted at the
  // workspace root; always pinned in the tab strip before productivity.
  const WORKSPACE_PROJECT_ID = '__workspace__';
  let _workspaceCurrent = null;  // last `current` row painted by initWorkspaceView

  // Logs fixed view: terminal-style reader for errors, backend, and frontend logs.
  const LOGS_PROJECT_ID = '__logs__';
  const LOGS_DEFAULT_FILE = 'errors.log';
  const LOGS_DEFAULT_TAIL = 500;
  const LOGS_MAX_TAIL = 5000;
  const LOGS_POLL_MS = 2000;
  const LOGS_LABELS = {
    'errors.log': {label: 'Errors', key: 'errors'},
    'backend.log': {label: 'Backend', key: 'backend'},
    'frontend.log': {label: 'Frontend', key: 'frontend'},
  };
  let logsState = {
    file: LOGS_DEFAULT_FILE,
    tail: LOGS_DEFAULT_TAIL,
    files: Object.keys(LOGS_LABELS),
    wired: false,
    live: true,
  };
  let logsLiveTimer = null;
  let logsRefreshInFlight = false;

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
  // Same TDZ hoist for the files-sidebar per-view persistence: the apply
  // helper runs inside _termApplyRememberedVisibility during the same
  // initial `?view=…` dispatch.
  const _SIDEBAR_VIS_KEY_PREFIX = 'labSidebarShown:';
  const _SIDEBAR_PCT_KEY_PREFIX = 'labSidebarPct:';

  // Dashboard "Servers" / "Terminals" sections (see renderDashboard and
  // dashServersRefresh/dashTermsRefresh further down). Independent poll loop,
  // independent re-render targets (#dashServers / #dashTerms) so they never
  // clobber the rest of the dashboard (expanded project rows, etc). Hoisted
  // up here — same TDZ rule as the consts above — because initSelf paints the
  // workbench (and starts this poll loop) synchronously during the initial
  // `?view=…` dispatch below.
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
  // dashPollTick itself is a no-op when the dashboard isn't the active view.
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
  } else if (urlView === 'workspace') {
    initWorkspaceView();
  } else if (urlView === 'code-search') {
    document.body.classList.add('code-search-active');
    const initialCodeSearchRepo = initialParams.get('repo');
    setTimeout(() => initCodeSearch(initialCodeSearchRepo), 0);
  } else if (urlView === 'logs') {
    initLogs({
      file: initialParams.get('file'),
      tail: initialParams.get('tail'),
    });
  }

  // Auto-refresh project view when any file in the project folder changes (mtime check)
  let _lastProjectMtime = 0;
  let _projMtimeMissPath = null; // project path the miss counter applies to
  let _projMtimeMisses = 0;      // consecutive "directory missing" responses
  let _projMtimeTick = 0;
  if (!UI_CHECK) setInterval(async () => {
    // A hidden tab can't show the refresh anyway, and the next visible
    // tick (≤1s away) catches up — don't let backgrounded windows keep
    // hitting the server (browser timer throttling made them poll ~1/min
    // forever, including tabs whose project no longer existed).
    if (document.hidden) return;
    if (!currentProject || !currentProject.is_project) return;
    if (currentRepo) return;
    if (_projDocEditing) return;
    if (_projMtimeMissPath !== currentProject.path) {
      _projMtimeMissPath = currentProject.path;
      _projMtimeMisses = 0;
    }
    _projMtimeTick += 1;
    // Project dir gone (deleted / volume unplugged): after a few misses,
    // probe only once a minute so it self-heals if the volume comes back.
    if (_projMtimeMisses >= 3 && _projMtimeTick % 60 !== 0) return;
    try {
      const res = await fetch(`/api/project-mtime?path=${encodeURIComponent(currentProject.path)}`);
      const { mtime } = await res.json();
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
    } catch(e) {}
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
    if (document.body.classList.contains('logs-active')) return LOGS_PROJECT_ID;
    if (document.body.classList.contains('cerebro-active')) return CEREBRO_PROJECT_ID;
    if (document.body.classList.contains('self-active')) return SELF_PROJECT_ID;
    if (document.body.classList.contains('code-search-active') && _csState && _csState.repo) {
      return _csProjectId(_csState.repo);
    }
    if (currentProject && currentProject.is_project) return currentProject.name;
    return null;
  }
  async function termAutoSpawnEnabled(projectId) {
    if (!projectId) return true;
    try {
      const r = await fetch('/api/ui/term-autospawn?project_id=' + encodeURIComponent(projectId));
      if (!r.ok) return true;
      const body = await r.json();
      return body.enabled !== false;
    } catch {
      return true;
    }
  }
  async function termSetAutoSpawnEnabled(projectId, enabled) {
    if (!projectId) return;
    try {
      await fetch('/api/ui/term-autospawn', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({project_id: projectId, enabled: !!enabled}),
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
      // Use fetchRepos() so the shared in-flight promise covers the
      // initial-load case (loadRepos + urlProject branch hit it too).
      // Wrap it so Promise.all gets four comparable values.
      const [hotRes, all, orderRes, attnRes, pseudoRes] = await Promise.all([
        fetch('/api/term/projects-with-sessions'),
        fetchRepos(),
        fetch('/api/ui/tab-order'),
        fetch('/api/term/projects-attention'),
        fetch('/api/ui/pseudo-tabs'),
      ]);
      const hotRaw = hotRes.ok ? await hotRes.json() : [];
      // Filter out the Code Search per-repo pseudo-project ids
      // (`__cs_<repo>__`). They spawn real tmux sessions when the
      // user opens a repo in the Code Search tab, which puts them in
      // /api/term/projects-with-sessions — but they shouldn't show up
      // as standalone tabs. The single `🔍 code-search` pseudo-tab in
      // projTabsRender already covers them.
      projTabsHot = (Array.isArray(hotRaw) ? hotRaw : []).filter(id => !id.startsWith('__cs_'));
      projTabsAll = (Array.isArray(all) ? all : []).filter(p => p.is_project);
      projTabsOrder = orderRes.ok ? await orderRes.json() : [];
      if (!Array.isArray(projTabsOrder)) projTabsOrder = [];
      projTabsAttention = attnRes.ok ? await attnRes.json() : [];
      if (!Array.isArray(projTabsAttention)) projTabsAttention = [];
      projTabsPseudoOpen = pseudoRes.ok ? await pseudoRes.json() : [];
      if (!Array.isArray(projTabsPseudoOpen)) projTabsPseudoOpen = [];
    } catch { /* leave stale state; next tick will retry */ }
    projTabsRender();
  }

  function projTabsRender() {
    const el = document.getElementById('projectTabs');
    if (!el) return;
    // Candidate tabs = hot sessions ∪ {currentProject} ∪ active pseudo-view
    //                  ∪ persisted open tabs.
    const seen = new Set();
    const tabs = [];
    const logsViewActive = document.body.classList.contains('logs-active');
    const pseudoOpen = new Set(projTabsPseudoOpenIds());
    if (logsViewActive || pseudoOpen.has(LOGS_PROJECT_ID)) {
      seen.add(LOGS_PROJECT_ID);
      tabs.push({id: LOGS_PROJECT_ID, hot: false});
    }
    for (const id of projTabsHot) { if (!seen.has(id)) { seen.add(id); tabs.push({id, hot: true}); } }
    const activeId = (currentProject && currentProject.is_project) ? currentProject.name : null;
    if (activeId && !seen.has(activeId)) { seen.add(activeId); tabs.push({id: activeId, hot: false}); }
    // Sticky open tabs: projects with `tab_open: true` in project.json. They
    // persist across in-page navigations (Home click) and full reloads until
    // the user clicks the X on the tab (which writes tab_open: false).
    for (const id of projTabsOpenIds()) {
      if (!seen.has(id)) { seen.add(id); tabs.push({id, hot: false}); }
    }
    const cerebroViewActive = document.body.classList.contains('cerebro-active');
    if (cerebroViewActive && !seen.has(CEREBRO_PROJECT_ID)) {
      seen.add(CEREBRO_PROJECT_ID);
      tabs.push({id: CEREBRO_PROJECT_ID, hot: false});
    }
    // Workspace is a fixed pseudo-tab — always pinned in the strip, pushed
    // just before productivity so the default order reads
    // "workspace · productivity". Content always reflects the ACTIVE
    // workspace (top-left dropdown); switching workspaces re-renders it.
    const workspaceViewActive = document.body.classList.contains('workspace-active');
    if (!seen.has(WORKSPACE_PROJECT_ID)) {
      seen.add(WORKSPACE_PROJECT_ID);
      tabs.push({id: WORKSPACE_PROJECT_ID, hot: false});
    }
    const selfViewActive = document.body.classList.contains('self-active');
    if (!seen.has(SELF_PROJECT_ID)) {
      seen.add(SELF_PROJECT_ID);
      tabs.push({id: SELF_PROJECT_ID, hot: false});
    }
    // Code Search is a fixed pseudo-tab — always pinned in the strip
    // (same UX as the productivity / cerebro pseudo-projects, which
    // are pinned via tab_open in their hidden project.json shells).
    // No gate: the user wants it one click away regardless of whether
    // a repo was previously opened or the view is currently active.
    const csViewActive = document.body.classList.contains('code-search-active');
    if (!seen.has(CODE_SEARCH_PROJECT_ID)) {
      seen.add(CODE_SEARCH_PROJECT_ID);
      tabs.push({id: CODE_SEARCH_PROJECT_ID, hot: false});
    }

    // Apply the user's saved order. Anything in `projTabsOrder` that's
    // still a candidate keeps its relative position; leftovers append.
    const byId = Object.fromEntries(tabs.map(t => [t.id, t]));
    const ordered = [];
    const used = new Set();
    for (const id of projTabsOrder) {
      if (byId[id]) { ordered.push(byId[id]); used.add(id); }
    }
    for (const t of tabs) {
      if (!used.has(t.id)) ordered.push(t);
    }
    // The workspace tab defaults to the slot immediately BEFORE the
    // productivity tab. Only until the user drags it somewhere: once its id
    // is in the saved order, that position wins like any other tab.
    if (!used.has(WORKSPACE_PROJECT_ID)) {
      const wIdx = ordered.findIndex(t => t.id === WORKSPACE_PROJECT_ID);
      const sIdx = ordered.findIndex(t => t.id === SELF_PROJECT_ID);
      if (wIdx !== -1 && sIdx !== -1 && wIdx !== sIdx - 1) {
        const [w] = ordered.splice(wIdx, 1);
        ordered.splice(ordered.findIndex(t => t.id === SELF_PROJECT_ID), 0, w);
      }
    }
    // Logs is pinned in slot 1 whenever it is open, active or not.
    const logsIdx = ordered.findIndex(t => t.id === LOGS_PROJECT_ID);
    if (logsIdx > 0) ordered.unshift(ordered.splice(logsIdx, 1)[0]);

    const attnSet = new Set(projTabsAttention || []);
    el.innerHTML = ordered.map(t => {
      const isLogs = t.id === LOGS_PROJECT_ID;
      const isCerebro = t.id === CEREBRO_PROJECT_ID;
      const isSelf = t.id === SELF_PROJECT_ID;
      const isCodeSearch = t.id === CODE_SEARCH_PROJECT_ID;
      const isWorkspace = t.id === WORKSPACE_PROJECT_ID;
      const isPseudo = isLogs || isCerebro || isSelf || isCodeSearch || isWorkspace;
      const active =
        (isLogs && logsViewActive) ||
        (isCerebro && cerebroViewActive) ||
        (isSelf && selfViewActive) ||
        (isCodeSearch && csViewActive) ||
        (isWorkspace && workspaceViewActive) ||
        (!isPseudo && t.id === activeId) ? ' active' : '';
      const dotCls = t.hot ? '' : ' cold';
      const label = isLogs ? 'logs'
        : isCerebro ? 'cerebro'
        : isSelf ? 'productivity'
        : isCodeSearch ? 'code-search'
        : isWorkspace ? 'workspace'
        : t.id;
      const icon = isLogs ? ''
        : isCerebro ? '🧠 '
        : isSelf ? '🛠️ '
        : isCodeSearch ? '🔍 '
        : isWorkspace ? '🗂️ '
        : '';
      // Pseudo-projects (cerebro, self, code-search) are never
      // "attention"-worthy since they can't have a stuck Claude session.
      const needsAttn = !isPseudo && attnSet.has(t.id);
      const attn = needsAttn ? ' attention' : '';
      const attnTitle = needsAttn ? ' · needs your attention (all Claude idle)' : '';
      const tabCls = isLogs ? ' logs-tab'
        : isCerebro ? ' cerebro-tab'
        : isSelf ? ' self-tab'
        : isCodeSearch ? ' code-search-tab'
        : isWorkspace ? ' workspace-tab'
        : '';
      const unseenCls = isLogs && document.body.classList.contains('logs-have-unseen-errors') ? ' has-unseen' : '';
      const closeTitle = isLogs
        ? 'Close Logs (kills its terminal sessions)'
        : isCerebro
        ? 'Close Cerebro (tab disappears; reopen from Home)'
        : (isSelf
            ? 'Close Productivity (tab disappears; reopen from Home)'
            : (isCodeSearch
                ? 'Close Code Search (tab disappears; reopen from Home)'
                : 'Close this project (kills its tmux sessions)'));
      // Real project tabs all belong to the one workspace the server is
      // currently serving — badge them with its id so it's obvious at a
      // glance which volume a tab's data is coming from.
      const wsBadge = (!isPseudo && currentWorkspaceId)
        ? `<span class="ws-badge" title="workspace: ${projTabsEsc(currentWorkspaceId)}">${projTabsEsc(currentWorkspaceId)}</span>`
        : '';
      const isBlocked = !isPseudo && tabBlocked.pid === t.id;
      const blockedCls = isBlocked ? ' blocked' : '';
      const blockedTitle = isBlocked ? ' · blocked: ' + tabBlocked.detail : '';
      const blockedIcon = isBlocked
        ? `<span class="blocked-icon" title="${projTabsEsc(tabBlocked.detail || '')}" aria-label="blocked">&#9888;</span>`
        : '';
      // The workspace tab is permanently pinned — no X (there is nothing
      // to close; the view always exists for the active workspace).
      const xBtn = isWorkspace
        ? ''
        : `<button class="x" title="${closeTitle}" data-x="${projTabsEsc(t.id)}">&times;</button>`;
      return `
        <div class="proj-tab${active}${tabCls}${attn}${unseenCls}${blockedCls}" draggable="true" data-pid="${projTabsEsc(t.id)}" role="tab" title="${projTabsEsc(label)}${attnTitle}${blockedTitle}">
          <span class="dot${dotCls}" title="${t.hot ? 'live session(s)' : 'no session yet'}"></span>
          <span class="label">${icon}${projTabsEsc(label)}</span>
          ${wsBadge}
          ${blockedIcon}
          <span class="attn-dot" aria-label="needs attention"></span>
          ${xBtn}
        </div>`;
    }).join('');

    // Click handlers. In-page nav (history.pushState + view swap) — no
    // full reload, no JS-scope reset, _termCache survives across switches.
    el.querySelectorAll('.proj-tab').forEach(node => {
      const pid = node.getAttribute('data-pid');
      node.addEventListener('click', (e) => {
        if (e.target.closest('.x')) return;  // X handled separately
        if (pid === LOGS_PROJECT_ID)        { goToLogs(); return; }
        if (pid === CEREBRO_PROJECT_ID)     { goToCerebro(); return; }
        if (pid === SELF_PROJECT_ID)        { goToProductivity(); return; }
        if (pid === CODE_SEARCH_PROJECT_ID) { goToCodeSearch(); return; }
        if (pid === WORKSPACE_PROJECT_ID)   { goToWorkspace(); return; }
        const proj = projTabsAll.find(p => p.name === pid);
        if (proj && proj.path) goToProject(proj.path);
      });
    });
    el.querySelectorAll('.proj-tab .x').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        projTabsClose(btn.getAttribute('data-x'));
      });
    });
    // Drag-and-drop reorder handlers.
    projTabsWireDnD(el);
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

  async function projTabsClose(pid) {
    if (!pid) return;
    if (pid === WORKSPACE_PROJECT_ID) return;  // permanently pinned, no X rendered
    const label =
      pid === CEREBRO_PROJECT_ID ? 'Cerebro'
      : pid === SELF_PROJECT_ID ? 'Productivity'
      : pid === LOGS_PROJECT_ID ? 'Logs'
      : pid;
    if (!confirm(`Close "${label}"? This kills all its tmux sessions (Claude conversations stay saved and will resume on reopen).`)) return;
    try {
      await fetch('/api/term/sessions/project/' + encodeURIComponent(pid), {method: 'DELETE'});
    } catch (e) { /* best effort */ }
    // Persist tab-closed in project.json so it doesn't reappear on next
    // Home/refresh. Pseudo-projects don't have a project.json — skip them.
    if (pid === LOGS_PROJECT_ID || pid === SELF_PROJECT_ID) {
      await projTabsSetPseudoOpen(pid, false);
    } else if (pid !== CEREBRO_PROJECT_ID && pid !== SELF_PROJECT_ID) {
      await projTabsSetOpen(pid, false);
    }
    await projTabsRefresh();
    // If we just closed the active project or a pseudo-project view, go home.
    const activeId = (currentProject && currentProject.is_project) ? currentProject.name : null;
    const logsViewActive = document.body.classList.contains('logs-active');
    const cerebroViewActive = document.body.classList.contains('cerebro-active');
    const selfViewActive = document.body.classList.contains('self-active');
    if (
      activeId === pid
      || (pid === LOGS_PROJECT_ID && logsViewActive)
      || (pid === CEREBRO_PROJECT_ID && cerebroViewActive)
      || (pid === SELF_PROJECT_ID && selfViewActive)
    ) {
      goHome();
    }
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
    const inTabs = new Set(projTabsHot);
    for (const id of projTabsPseudoOpenIds()) inTabs.add(id);
    const activeId = (currentProject && currentProject.is_project) ? currentProject.name : null;
    if (activeId) inTabs.add(activeId);
    if (document.body.classList.contains('logs-active')) inTabs.add(LOGS_PROJECT_ID);
    if (document.body.classList.contains('cerebro-active')) inTabs.add(CEREBRO_PROJECT_ID);
    inTabs.add(SELF_PROJECT_ID);
    const candidates = projTabsAll.filter(p => !inTabs.has(p.name));
    // Pseudo-projects sit at the top of the picker
    // unless they're already a tab.
    const logsRow = inTabs.has(LOGS_PROJECT_ID) ? '' : `
      <div class="row" data-logs="1">
        <span>logs</span>
        <span class="meta">errors · backend · frontend</span>
      </div>`;
    const selfRow = inTabs.has(SELF_PROJECT_ID) ? '' : `
      <div class="row" data-self="1">
        <span>🛠️ productivity</span>
        <span class="meta">this repo</span>
      </div>`;
    const cerebroRow = inTabs.has(CEREBRO_PROJECT_ID) ? '' : `
      <div class="row" data-cerebro="1">
        <span>🧠 cerebro</span>
        <span class="meta">knowledge base</span>
      </div>`;
    const codeSearchRow = inTabs.has(CODE_SEARCH_PROJECT_ID) ? '' : `
      <div class="row" data-code-search="1">
        <span>🔍 code-search</span>
        <span class="meta">repositories/</span>
      </div>`;
    if (!logsRow && !selfRow && !cerebroRow && !codeSearchRow && candidates.length === 0) {
      picker.innerHTML = '<div class="empty">Everything is already open.</div>';
      return;
    }
    picker.innerHTML = logsRow + selfRow + cerebroRow + codeSearchRow + candidates.map(p => `
      <div class="row" data-path="${projTabsEsc(p.path)}">
        <span>${projTabsEsc(p.name)}</span>
        <span class="meta">${(p.repos || []).length} repo(s)</span>
      </div>`).join('');
    picker.querySelectorAll('.row').forEach(row => {
      row.addEventListener('click', () => {
        picker.classList.remove('open');
        if (row.getAttribute('data-logs') === '1')        { goToLogs(); return; }
        if (row.getAttribute('data-self') === '1')        { goToProductivity(); return; }
        if (row.getAttribute('data-cerebro') === '1')     { goToCerebro(); return; }
        if (row.getAttribute('data-code-search') === '1') { goToCodeSearch(); return; }
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
    const isWarmSwitch = _termSessionsCache.has(projectId);
    if (isWarmSwitch) {
      termSessions = _termSessionsCache.get(projectId) || [];
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
      termStartStatusPolling();
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
    // Live working/idle indicator on each pill.
    termStartStatusPolling();
  }

  function _termHasOpenCachedPane(projectId, name) {
    if (typeof _termCache === 'undefined' || typeof _termCacheKey !== 'function') return false;
    const cached = _termCache.get(_termCacheKey(projectId, name));
    return _termCachedPaneIsFresh(cached);
  }

  async function _termTryWarmOpen(projectId) {
    if (!_termSessionsCache.has(projectId)) return false;
    termSessions = _termSessionsCache.get(projectId) || [];
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
    await _termRefreshSessionsForProjectId(projectId);
    if (!_termIsScopeActive(projectId)) return;

    let saved = [];
    try {
      const r = await fetch('/api/term/sessions/saved?project_id=' + encodeURIComponent(projectId));
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
    const projectAutoSpawn = globalAutoSpawn && await termAutoSpawnEnabled(projectId);
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
          kind: s.kind || 'claude',
          agent: s.agent,
          name: s.name,
          auto: true,
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
      // Active pseudo-views win over a stale currentProject from the previous
      // tab. Otherwise, use the loaded real project id.
      let pid = null;
      if (document.body.classList.contains('logs-active')) pid = LOGS_PROJECT_ID;
      else if (document.body.classList.contains('cerebro-active')) pid = CEREBRO_PROJECT_ID;
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

  // Poll /api/term/sessions/status periodically so session pills show live
  // "working / waiting on you" state. Cheap server-side (cached), cheap
  // client-side (tiny response). Stops when the panel closes.
  function termStartStatusPolling() {
    if (_termStatusTimer || UI_CHECK) return;
    const tick = async () => {
      if (!document.body.classList.contains('term-open')) {
        termStopStatusPolling();
        return;
      }
      let pid = null;
      if (document.body.classList.contains('logs-active')) pid = LOGS_PROJECT_ID;
      else if (document.body.classList.contains('cerebro-active')) pid = CEREBRO_PROJECT_ID;
      else if (document.body.classList.contains('self-active')) pid = SELF_PROJECT_ID;
      else if (currentProject && currentProject.is_project) pid = currentProject.name;
      if (!pid) return;
      try {
        const r = await fetch('/api/term/sessions/status?project_id=' + encodeURIComponent(pid));
        const rows = r.ok ? await r.json() : [];
        // Wipe old entries not in the new response so killed sessions don't
        // linger with stale status.
        for (const k of Object.keys(termStatus)) delete termStatus[k];
        for (const row of rows) termStatus[row.name] = row.status;
        termRenderSessionList();
      } catch {}
    };
    afterPageQuiet(tick, 500);
    _termStatusTimer = setInterval(tick, 8000);
  }

  function termStopStatusPolling() {
    if (_termStatusTimer) { clearInterval(_termStatusTimer); _termStatusTimer = null; }
  }

  function termStopPeriodicRefresh() {
    if (termRefreshTimer) { clearInterval(termRefreshTimer); termRefreshTimer = null; }
  }

  function termClose() {
    document.body.classList.remove('term-open');
    document.body.classList.remove('term-collapsed');
    termStopPeriodicRefresh();
    termStopStatusPolling();
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
  // is namespaced by the active view (a real project id, the cerebro/
  // self pseudo id, or "__code_search__" for the code-search tab).
  // Default-visibility differs per view: code-search starts collapsed
  // (it has its own three-pane layout that wants the width); every-
  // thing else starts expanded.
  // (`_TERM_VIS_KEY_PREFIX` is declared higher up to avoid a TDZ when
  // these helpers run during the initial `?view=…` URL dispatch.)
  function _termVisibilityKey() {
    if (document.body.classList.contains('code-search-active')) return _TERM_VIS_KEY_PREFIX + 'code-search';
    if (document.body.classList.contains('logs-active')) return _TERM_VIS_KEY_PREFIX + 'logs';
    if (document.body.classList.contains('cerebro-active')) return _TERM_VIS_KEY_PREFIX + 'cerebro';
    if (document.body.classList.contains('self-active')) return _TERM_VIS_KEY_PREFIX + 'self';
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
  // Called from termOpenForProject/Self/Cerebro and initCodeSearch so
  // every view enters with the user's last preference for that view.
  // Default is "shown" except for code-search, which has its own
  // 3-pane layout that wants the width — terminal is hidden until
  // the user clicks the toggle.
  function _termApplyRememberedVisibility() {
    const key = _termVisibilityKey();
    const defaultShown = !key.endsWith(':code-search');
    const shown = _termRecallVisibility(key, defaultShown);
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
    if (document.body.classList.contains('code-search-active')) return 'code-search';
    if (document.body.classList.contains('logs-active')) return 'logs';
    if (document.body.classList.contains('cerebro-active')) return 'cerebro';
    if (document.body.classList.contains('self-active')) return 'self';
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
    let fresh = [];
    let ok = false;
    try {
      const r = await fetch('/api/term/sessions?project_id=' + encodeURIComponent(projectId));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(projectId, fresh);
    // Stale-response guard. termOpenForProject's warm-switch path fires
    // this refresh without awaiting, so by the time the response lands
    // the user may already be on a different tab. Cache the result but
    // don't touch globals or repaint — the active view's own refresh
    // will handle its own pills.
    if (projectId !== _termActiveProjectId()) return ok;
    // On a failed fetch (server restarting, network blip) fall back to the
    // last successful list for this project instead of wiping the pills —
    // the tmux sessions are almost certainly still alive, and the reconnect
    // loop needs their names to keep retrying.
    termSessions = ok ? fresh : (_termSessionsCache.get(projectId) || []);
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
  // Status map: session tmux-name -> "working" | "idle" | "n/a" | "unknown".
  // Populated by termPollStatus; consumed by termRenderSessionList.
  const termStatus = {};
  let _termStatusTimer = null;

  function _termSessionDisplay(s) {
    return (s && (s.label || s.logical_name || s.name)) || '';
  }

  function _termSessionTitle(s, statusTitle) {
    const parts = [];
    const display = _termSessionDisplay(s);
    if (display) parts.push(display);
    if (s && s.summary) parts.push(s.summary);
    if (s && s.name) parts.push(s.name);
    if (statusTitle) parts.push(statusTitle);
    parts.push('Double-click or use the pencil to rename');
    return parts.join('\n');
  }

  async function termRenameSession(name) {
    const session = _termSessionMeta(name);
    if (!session) return;
    const projectId = _termActiveProjectId();
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
          name: logical,
          label: next || null,
        }),
      });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(body.detail || r.statusText || 'rename failed');
      const updated = body.session || {};
      termSessions = (termSessions || []).map(s =>
        s.name === name ? {...s, label: updated.label || null, summary: updated.summary || s.summary} : s
      );
      _termSessionsCache.set(projectId, termSessions);
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

  function termRenderSessionList() {
    const el = document.getElementById('termSessionList');
    if (!el) return;
    if (!termSessions || termSessions.length === 0) {
      el.innerHTML = '<span class="empty">no sessions — click + New</span>';
      return;
    }
    el.innerHTML = termSessions.map(s => {
      const display = _termSessionDisplay(s);
      const kind = (s.kind || '').toLowerCase();
      // Badge + icon reflect the actual agent (claude/codex/copilot), not the
      // transport kind — codex sessions have kind==='claude' but must not read
      // "CLAUDE". Terminal sessions show their kind ('terminal').
      const agent = (s.agent || (kind === 'claude' ? 'claude' : '')).toLowerCase();
      const isClaude = agent === 'claude';
      const badge = kind === 'claude' ? (agent || 'claude') : kind;
      const icon = kind !== 'claude' ? '💻'
        : agent === 'codex' ? '🧠'
        : agent === 'copilot' ? '🐙'
        : '🤖';
      const active = (s.name === termCurrentSession && _termActiveProjectId() === termCurrentProjectId) ? ' active' : '';
      const logical = s.logical_name || '';
      const dead = termDeadSessions.has(s.name) ? ' dead' : '';
      // status: 'working' (pulsing yellow dot) or 'idle' (solid red dot) — only
      // the Claude agent has a UI we can classify. codex/copilot/terminal: none.
      const status = termStatus[s.name] || '';
      const statusCls = (!dead && isClaude && (status === 'working' || status === 'idle'))
        ? ` ${status}` : '';
      const statusTitle = dead
        ? 'Session unreachable — click to retry'
        : (isClaude
            ? (status === 'working' ? 'Claude is working…'
               : status === 'idle'   ? 'Claude idle — needs your input'
               : 'Claude — status unknown')
            : '');
      const labelCls = s.label ? ' custom' : '';
      return `<span class="sess ${kind}${active}${statusCls}${dead}" draggable="true" data-name="${termSessEsc(s.name)}" data-logical="${termSessEsc(logical)}" title="${termSessEsc(_termSessionTitle(s, statusTitle))}">
        <span class="stat"></span>
        <span>${icon}</span>
        <span class="sess-label${labelCls}">${termSessEsc(display)}</span>
        <span class="k">${termSessEsc(badge)}</span>
        <button type="button" class="rename" data-rename="${termSessEsc(s.name)}" title="Rename terminal tab" aria-label="Rename terminal tab">✎</button>
      </span>`;
    }).join('');
    el.querySelectorAll('.sess').forEach(node => {
      const renameBtn = node.querySelector('[data-rename]');
      if (renameBtn) {
        renameBtn.addEventListener('click', (e) => {
          e.preventDefault();
          e.stopPropagation();
          termRenameSession(renameBtn.getAttribute('data-rename'));
        });
      }
      node.addEventListener('dblclick', (e) => {
        e.preventDefault();
        e.stopPropagation();
        termRenameSession(node.getAttribute('data-name'));
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
    termWireSessionDnD(el);
  }

  function termWireSessionDnD(container) {
    container.querySelectorAll('.sess').forEach(pill => {
      pill.addEventListener('dragstart', (e) => {
        _termDragLogical = pill.getAttribute('data-logical');
        pill.classList.add('dragging');
        if (e.dataTransfer) {
          e.dataTransfer.effectAllowed = 'move';
          e.dataTransfer.setData('text/plain', _termDragLogical || '');
        }
      });
      pill.addEventListener('dragend', () => {
        pill.classList.remove('dragging');
        container.querySelectorAll('.sess.drop-before, .sess.drop-after')
          .forEach(p => p.classList.remove('drop-before', 'drop-after'));
        _termDragLogical = null;
      });
      pill.addEventListener('dragover', (e) => {
        if (!_termDragLogical) return;
        e.preventDefault();
        if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        container.querySelectorAll('.sess.drop-before, .sess.drop-after')
          .forEach(p => p.classList.remove('drop-before', 'drop-after'));
        const rect = pill.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        pill.classList.add(before ? 'drop-before' : 'drop-after');
      });
      pill.addEventListener('drop', async (e) => {
        e.preventDefault();
        const src = _termDragLogical;
        const dst = pill.getAttribute('data-logical');
        container.querySelectorAll('.sess.drop-before, .sess.drop-after')
          .forEach(p => p.classList.remove('drop-before', 'drop-after'));
        if (!src || !dst || src === dst) return;
        const rect = pill.getBoundingClientRect();
        const before = (e.clientX - rect.left) < rect.width / 2;
        await termReorderSessions(src, dst, before);
      });
    });
  }

  async function termReorderSessions(srcLogical, dstLogical, placeBefore) {
    // Compute new order from current DOM (authoritative — keeps us in
    // sync with the most recent render).
    const current = Array.from(document.querySelectorAll('#termSessionList .sess'))
      .map(n => n.getAttribute('data-logical'))
      .filter(Boolean);
    const si = current.indexOf(srcLogical);
    if (si === -1) return;
    current.splice(si, 1);
    let di = current.indexOf(dstLogical);
    if (di === -1) di = current.length;
    if (!placeBefore) di += 1;
    current.splice(di, 0, srcLogical);

    // Reorder termSessions to match so the next render picks it up.
    const byLogical = Object.fromEntries(
      (termSessions || []).map(s => [s.logical_name, s])
    );
    termSessions = current.map(n => byLogical[n]).filter(Boolean);
    termRenderSessionList();

    // Persist server-side. Same project-id resolution used elsewhere.
    let projectId = null;
    if (document.body.classList.contains('logs-active')) projectId = LOGS_PROJECT_ID;
    else if (document.body.classList.contains('cerebro-active')) projectId = CEREBRO_PROJECT_ID;
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
        body: JSON.stringify({project_id: projectId, order: current}),
      });
    } catch (e) { /* best-effort; local order already reflects */ }
    // Small grace so filesystem writes + watcher ignore-list settle.
    setTimeout(() => { _termReorderPending = false; }, 250);
  }

  function termSessEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  function termToggleNewPicker(ev) {
    if (ev) ev.stopPropagation();
    const el = document.getElementById('termNewPicker');
    if (!el) return;
    el.classList.toggle('open');
    // One-shot outside-click listener to dismiss.
    if (el.classList.contains('open')) {
      termRefreshAgentAvail(el);
      const off = (e) => {
        if (!el.contains(e.target) && e.target.id !== 'termNewBtn') {
          el.classList.remove('open');
          document.removeEventListener('click', off);
        }
      };
      setTimeout(() => document.addEventListener('click', off), 0);
    }
  }

  // Gray out agents whose CLI isn't installed (e.g. copilot). Cached after the
  // first lookup; failures leave every option enabled (the spawn surfaces a
  // clean error anyway).
  let _agentAvail = null;
  async function termRefreshAgentAvail(picker) {
    try {
      if (!_agentAvail) _agentAvail = await (await fetch('/api/agents/available')).json();
    } catch { return; }
    picker.querySelectorAll('button[data-agent]').forEach(btn => {
      const a = btn.dataset.agent;
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
    // Resolve the project id the new session belongs to. Active pseudo-views
    // can coexist with a stale currentProject from the previous tab, so check
    // them first.
    let projectId = null;
    if (document.body.classList.contains('logs-active')) {
      projectId = LOGS_PROJECT_ID;
    } else if (document.body.classList.contains('cerebro-active')) {
      projectId = CEREBRO_PROJECT_ID;
    } else if (document.body.classList.contains('self-active')) {
      projectId = SELF_PROJECT_ID;
    } else if (currentProject && currentProject.is_project) {
      projectId = currentProject.name;
    }
    if (!projectId) return;

    termSetStatus('idle', kind === 'claude' ? `creating ${agent || 'claude'}…` : 'creating terminal…');
    try {
      const r = await fetch('/api/term/sessions', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          project_id: projectId,
          kind,
          agent,  // null → server resolves project override / global default
          start_fresh: startFresh,
          auto: true,  // only meaningful for claude; ignored for terminal
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        alert('Failed to create session: ' + (body.detail || r.statusText));
        termSetStatus('err', 'create failed');
        return;
      }
      const created = await r.json();
      await termSetAutoSpawnEnabled(projectId, true);
      // Brand-new session — clear any stale dead/backoff state for this
      // tmux name (possible if the user just recycled the same logical
      // name after the previous session died).
      _termClearDead(created.name);
      // termRefreshSessions reads `currentProject` directly when no id is
      // passed; pseudo-projects use the project-id-aware helper.
      if (projectId === CEREBRO_PROJECT_ID || projectId === SELF_PROJECT_ID || projectId === LOGS_PROJECT_ID) {
        await termRefreshSessionsByProjectId(projectId);
      } else {
        await termRefreshSessions(projectId);
      }
      if (!_termIsScopeActive(projectId)) return;
      if (!termSessions.some(s => s && s.name === created.name)) {
        termSessions = [{...created, project_id: created.project_id || projectId}, ...termSessions];
        _termSessionsCache.set(projectId, termSessions);
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
    if (!confirm('Close terminal session ' + termCurrentSession + '? It will stay closed after reload.')) return;
    const name = termCurrentSession;
    termDetach();  // full close (soft=false) — evicts cache entry
    try { await fetch('/api/term/sessions/' + encodeURIComponent(name) + '?purge=true', {method: 'DELETE'}); } catch {}
    await termSetAutoSpawnEnabled(projectId, false);
    if (projectId === CEREBRO_PROJECT_ID || projectId === SELF_PROJECT_ID || projectId === LOGS_PROJECT_ID) await termRefreshSessionsByProjectId(projectId);
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
    termAttachRequestSeq += 1;  // cancel any attach still waiting on assets/layout
    termUserDetached = true;  // mark so onclose doesn't try to recover
    if (termReconnectTimer) { clearTimeout(termReconnectTimer); termReconnectTimer = null; }
    const prev = termCurrentSession;
    const prevProjectId = termCurrentProjectId;
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
  }

  // ─── Home view (dashboard / timeline / search) ───
  // Absorbed the old lab-backend SPA views. Uses the same /api/index,
  // /api/tasks/due, /api/search the old SPA used. Inline, no framework.
  // State declarations MUST come before the init dispatch below — initHome()
  // reads these `let`s and would hit a TDZ error if they were declared later.

  let homeTab = 'dashboard';
  let homeDashboardFilter = 'active';
  let homeTimelineMode = 'list';
  let homeSearchQuery = '';
  let homeSearchResults = null;
  let _homeRendering = false;

  // Code Search can be initialized by the direct ?view=code-search dispatch
  // below, so its state must be ready before that dispatch runs.
  const _CS_LAST_KEY = 'labCsLastRepo';
  const _csCache = {
    repos: null,
    stats: new Map(),
    search: new Map(),
    file: new Map(),
    log: new Map(),
  };
  const _csState = {
    repo: null,
    filter: '',
    mode: 'filenames',
    query: '',
    openFile: null,
    fileLines: null,
    selectedRange: null,
    rangeScope: false,
    hitLine: null,
  };

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
    const rootPrefix = SELF_REPO_PATH.endsWith('/') ? SELF_REPO_PATH : SELF_REPO_PATH + '/';
    const absProject = rootPrefix + 'projects/' + projectId;
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
    document.body.classList.remove('home-active', 'cerebro-active', 'self-active', 'workspace-active', 'code-search-active', 'logs-active', 'has-diff-tabs');
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
        selectRepo(proj.name);
      }
    });
  } else if (urlRepo) {
    fetchRepos().then(projects => {
      projectsList = projects;
      const proj = projects.find(p => p.repos.some(r => r.path === urlRepo));
      if (proj) {
        selectRepo(proj.name);
        if (proj.repos.length > 1) {
          const targetRepo = proj.repos.find(r => r.path === urlRepo);
          if (targetRepo) selectProjectRepo(targetRepo.path);
        }
      }
    });
  } else if (urlView === 'cerebro' || urlView === 'productivity' || urlView === 'workspace' || urlView === 'code-search' || urlView === 'logs') {
    // These views handle their own init above; skip Home.
  } else {
    // No project or repo in URL → show Home (dashboard / timeline / search).
    initHome();
  }

  function initHome() {
    document.body.classList.add('home-active');
    // Remember sub-tab from URL hash (#dashboard / #snoozed / #timeline / #search)
    const h = (location.hash || '').replace(/^#/, '');
    if (h === 'snoozed' || h === 'timeline' || h === 'search') homeTab = h;
    setHomeTab(homeTab);
    // WS subscription is wired once at script bottom (subscribeLiveWS),
    // so both home and project views get live refresh without duplicate
    // sockets.
  }

  // Click handler for the Home link. Switches to the home view in-page so
  // any project tabs the user has opened stay in the strip. The previous
  // implementation used `<a href="/">` which did a full reload and dropped
  // every tab that didn't have a live tmux session.
  function goHome(ev) {
    if (ev) ev.preventDefault();
    _swapViewState();
    document.title = 'Productivity';
    document.body.classList.add('home-active');
    // Update URL without a reload; preserve the sub-tab hash if present.
    const url = new URL(window.location);
    url.searchParams.delete('project');
    url.searchParams.delete('repo');
    url.searchParams.delete('view');
    url.searchParams.delete('path');
    url.searchParams.delete('file');
    url.searchParams.delete('tail');
    history.pushState({nav: 'home'}, '', url.pathname + url.search + url.hash);
    initHome();
    projTabsRender();
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
    if (typeof logsStopLive === 'function') logsStopLive();
    document.body.classList.remove(
      'cerebro-active', 'self-active', 'workspace-active', 'home-active',
      'project-active', 'code-search-active', 'logs-active', 'has-diff-tabs',
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
      history.pushState({nav: 'project', path}, '', url.pathname + url.search + url.hash);
    }
    const dispatch = () => {
      const proj = (projectsList || []).find(p => p.path === path);
      if (proj) selectRepo(proj.name);
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

  function goToCerebro(initialPath = '', opts = {}) {
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

  function goToProductivity(opts = {}) {
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.set('view', 'productivity');
      history.pushState({nav: 'productivity'}, '', url.pathname + url.search + url.hash);
    }
    projTabsSetPseudoOpen(SELF_PROJECT_ID, true);
    initSelf();
  }

  function goToWorkspace(opts = {}) {
    _swapViewState();
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.set('view', 'workspace');
      history.pushState({nav: 'workspace'}, '', url.pathname + url.search + url.hash);
    }
    // No projTabsSetPseudoOpen: the workspace tab is permanently pinned.
    initWorkspaceView();
  }

  function logsNormalizeFile(file) {
    return Object.prototype.hasOwnProperty.call(LOGS_LABELS, file) ? file : LOGS_DEFAULT_FILE;
  }

  function logsNormalizeTail(value) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0) return LOGS_DEFAULT_TAIL;
    return Math.min(Math.floor(n), LOGS_MAX_TAIL);
  }

  function logsInfo(file) {
    return LOGS_LABELS[file] || {label: file || 'Log', key: 'log'};
  }

  function logsUpdateUrl(push) {
    const url = new URL(window.location);
    url.hash = '';
    url.searchParams.delete('project');
    url.searchParams.delete('repo');
    url.searchParams.delete('path');
    url.searchParams.set('view', 'logs');
    url.searchParams.set('file', logsState.file);
    url.searchParams.set('tail', String(logsState.tail));
    const method = push ? 'pushState' : 'replaceState';
    history[method]({nav: 'logs', file: logsState.file, tail: logsState.tail}, '', url.pathname + url.search);
  }

  function goToLogs(opts = {}) {
    const params = new URLSearchParams(location.search);
    const file = logsNormalizeFile(opts.file || params.get('file') || logsState.file);
    const tail = logsNormalizeTail(opts.tail || params.get('tail') || logsState.tail);
    _swapViewState();
    projTabsSetPseudoOpen(LOGS_PROJECT_ID, true);
    logsState.file = file;
    logsState.tail = tail;
    if (!opts.replace) logsUpdateUrl(true);
    initLogs({file, tail});
  }

  function initLogs(opts = {}) {
    logsState.file = logsNormalizeFile(opts.file || logsState.file);
    logsState.tail = logsNormalizeTail(opts.tail || logsState.tail);
    document.body.classList.add('logs-active');
    document.title = 'Logs';
    logsWireHandlers();
    logsRenderSources();
    logsRenderControls();
    logsPaintShell();
    if (typeof projTabsRender === 'function') projTabsRender();
    logsStopLive();
    afterPageQuiet(() => {
      logsLoadFiles()
        .then(() => logsRefresh({forceTail: true, forceScroll: true}))
        .catch(() => logsRefresh({forceTail: true, forceScroll: true}))
        .finally(logsStartLive);
      if (!UI_CHECK) termOpenForLogs();
    });
  }

  function logsWireHandlers() {
    const view = document.getElementById('logsView');
    if (!view || view._wired) return;
    view._wired = true;
    const sourceList = document.getElementById('logsSourceList');
    if (sourceList) {
      sourceList.addEventListener('click', (e) => {
        const btn = e.target.closest('.logs-source');
        if (!btn) return;
        logsSelectFile(btn.getAttribute('data-file'));
      });
    }
    const tailInput = document.getElementById('logsTailInput');
    if (tailInput) {
      tailInput.addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        logsRefresh({forceTail: true, forceScroll: true});
      });
      tailInput.addEventListener('blur', () => {
        tailInput.value = String(logsNormalizeTail(tailInput.value));
        logsState.tail = logsNormalizeTail(tailInput.value);
        logsRenderControls();
        logsUpdateUrl(false);
      });
    }
  }

  function logsStartLive() {
    logsStopLive();
    logsState.live = true;
    logsRenderControls();
    logsLiveTimer = setInterval(() => {
      if (!document.body.classList.contains('logs-active')) {
        logsStopLive();
        return;
      }
      logsRefresh({auto: true});
    }, LOGS_POLL_MS);
  }

  function logsStopLive() {
    if (logsLiveTimer) clearInterval(logsLiveTimer);
    logsLiveTimer = null;
  }

  async function logsLoadFiles() {
    try {
      const r = await fetch('/api/log/files', {cache: 'no-store'});
      if (!r.ok) throw new Error(String(r.status));
      const data = await r.json();
      const available = new Set((data.files || []).map(f => f && f.name).filter(Boolean));
      logsState.files = Object.keys(LOGS_LABELS).filter(name => available.size === 0 || available.has(name));
      if (!logsState.files.length) logsState.files = Object.keys(LOGS_LABELS);
      if (!logsState.files.includes(logsState.file)) logsState.file = LOGS_DEFAULT_FILE;
      logsRenderSources();
      logsRenderControls();
    } catch {
      logsState.files = Object.keys(LOGS_LABELS);
      logsRenderSources();
    }
  }

  function logsRenderSources() {
    const list = document.getElementById('logsSourceList');
    if (!list) return;
    const files = logsState.files && logsState.files.length ? logsState.files : Object.keys(LOGS_LABELS);
    list.innerHTML = files.map(file => {
      const info = logsInfo(file);
      const active = file === logsState.file ? ' active' : '';
      const unseen = file === LOGS_DEFAULT_FILE && document.body.classList.contains('logs-have-unseen-errors') ? ' has-unseen' : '';
      return `
        <button class="logs-source${active}${unseen}" data-file="${escapeHtml(file)}" type="button">
          <span>${escapeHtml(info.label)}</span><span class="source-key">${escapeHtml(info.key)}</span>
        </button>`;
    }).join('');
  }

  function logsRenderControls() {
    const info = logsInfo(logsState.file);
    const active = document.getElementById('logsActiveName');
    const command = document.getElementById('logsCommand');
    const tail = document.getElementById('logsTailInput');
    const status = document.getElementById('logsStatus');
    if (active) active.textContent = info.label;
    if (command) command.textContent = `$ tail -n ${logsState.tail} logs/${logsState.file}`;
    if (tail && document.activeElement !== tail) tail.value = String(logsState.tail);
    if (status && !status.dataset.lines) status.textContent = logsState.live ? 'live' : '';
    document.querySelectorAll('.logs-source').forEach(btn => {
      const file = btn.getAttribute('data-file');
      btn.classList.toggle('active', file === logsState.file);
      btn.classList.toggle('has-unseen', file === LOGS_DEFAULT_FILE && document.body.classList.contains('logs-have-unseen-errors'));
    });
  }

  function logsPaintShell() {
    const terminal = document.getElementById('logsTerminal');
    const status = document.getElementById('logsStatus');
    if (status) status.textContent = 'queued';
    if (!terminal) return;
    const head = `<div class="logs-terminal-head"><span class="prompt">$</span> tail -n ${escapeHtml(logsState.tail)} logs/${escapeHtml(logsState.file)}</div>`;
    terminal.innerHTML = head + '<div class="logs-empty">Fetching log tail...</div>';
  }

  function logsSelectFile(file) {
    const next = logsNormalizeFile(file);
    if (next === logsState.file) {
      logsRefresh({forceTail: true, forceScroll: true});
      return;
    }
    logsState.file = next;
    logsRenderControls();
    logsUpdateUrl(true);
    logsRefresh({forceTail: true, forceScroll: true});
  }

  function logsFmtTs(ts) {
    if (!ts) return '';
    try {
      return new Date(ts).toLocaleTimeString([], {hour12: false});
    } catch {
      return String(ts);
    }
  }

  function logsMeta(entry) {
    const bits = [];
    if (entry.method || entry.status_code) bits.push([entry.method, entry.status_code].filter(Boolean).join(' '));
    if (entry.duration_ms != null) bits.push(`${entry.duration_ms}ms`);
    if (entry.action) bits.push(entry.action);
    if (entry.event_type) bits.push(entry.event_type);
    return bits.join(' ');
  }

  function logsEntryHtml(entry, index) {
    const level = String(entry.level || (entry.raw ? 'raw' : 'log')).toUpperCase();
    const cls = level.toLowerCase().replace(/[^a-z0-9_-]/g, '');
    const source = entry.source || entry.logger || logsInfo(logsState.file).label;
    const path = entry.path || entry.href || entry.source_url || entry.target || logsMeta(entry) || '';
    const msg = entry.msg || entry.message || entry.raw || '';
    const detail = entry.exc && entry.exc !== msg ? entry.exc : '';
    return `
      <div class="logs-entry level-${escapeHtml(cls)}">
        <span class="time">${escapeHtml(logsFmtTs(entry.ts) || String(index + 1))}</span>
        <span class="level">${escapeHtml(level)}</span>
        <span class="source" title="${escapeHtml(source)}">${escapeHtml(source)}</span>
        <span class="path" title="${escapeHtml(path)}">${escapeHtml(path)}</span>
        <span class="message">${escapeHtml(msg)}</span>
        ${detail ? `<pre class="logs-stack">${escapeHtml(detail)}</pre>` : ''}
      </div>`;
  }

  function logsAtBottom(el) {
    return !el || (el.scrollTop + el.clientHeight >= el.scrollHeight - 24);
  }

  function logsRenderEntries(data, opts = {}) {
    const terminal = document.getElementById('logsTerminal');
    if (!terminal) return;
    const shouldStick = opts.forceScroll || logsAtBottom(terminal);
    const priorTop = terminal.scrollTop;
    const entries = data.entries || [];
    const head = `<div class="logs-terminal-head"><span class="prompt">$</span> tail -n ${escapeHtml(logsState.tail)} logs/${escapeHtml(logsState.file)}</div>`;
    if (!entries.length) {
      terminal.innerHTML = head + '<div class="logs-empty">No log lines found.</div>';
      return;
    }
    terminal.innerHTML = head + entries.map(logsEntryHtml).join('');
    terminal.scrollTop = shouldStick ? terminal.scrollHeight : priorTop;
  }

  async function logsRefresh(opts = {}) {
    if (logsRefreshInFlight) return;
    logsRefreshInFlight = true;
    const tailInput = document.getElementById('logsTailInput');
    if (opts.forceTail || document.activeElement !== tailInput) {
      logsState.tail = logsNormalizeTail((tailInput || {}).value || logsState.tail);
    }
    logsState.file = logsNormalizeFile(logsState.file);
    logsRenderControls();
    if (!opts.auto) logsUpdateUrl(false);
    const status = document.getElementById('logsStatus');
    const button = document.getElementById('logsRefreshBtn');
    if (status) {
      status.dataset.lines = '';
      status.textContent = opts.auto ? 'live' : 'refreshing';
    }
    if (button && !opts.auto) button.disabled = true;
    try {
      const qs = new URLSearchParams({file: logsState.file, tail: String(logsState.tail)});
      const r = await fetch('/api/log/tail?' + qs.toString(), {cache: 'no-store'});
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || r.statusText || String(r.status));
      }
      const data = await r.json();
      logsState.file = logsNormalizeFile(data.file || logsState.file);
      logsRenderControls();
      logsRenderEntries(data, opts);
      if (logsState.file === LOGS_DEFAULT_FILE && window.labLogAlertMarkSeen) {
        window.labLogAlertMarkSeen(data.state);
      }
      if (status) {
        status.dataset.lines = String(data.line_count || 0);
        status.textContent = logsState.live ? `live · ${data.line_count || 0} lines` : `${data.line_count || 0} lines`;
      }
    } catch (e) {
      const terminal = document.getElementById('logsTerminal');
      if (!opts.auto && terminal) terminal.innerHTML = `<div class="logs-error">Failed to load logs: ${escapeHtml(e.message || e)}</div>`;
      if (status) status.textContent = 'failed';
    } finally {
      logsRefreshInFlight = false;
      if (button) button.disabled = false;
    }
  }

  window.goToLogs = goToLogs;
  window.logsRefresh = logsRefresh;

  // ─── Code Search tab ─────────────────────────────────────────────
  // Per-repo pseudo project ids drive the terminal panel and the
  // warm-switch cache. Backend treats `__cs_<repo>__` as cwd=
  // repositories/<repo> (see term.py:_project_cwd).
  function _csProjectId(repoName) {
    return repoName ? ('__cs_' + repoName + '__') : null;
  }

  function goToCodeSearch(opts = {}) {
    _swapViewState();
    const initialRepo = (opts && opts.repo) || _csRecallLastRepo() || null;
    if (!opts.replace) {
      const url = new URL(window.location);
      url.searchParams.delete('project');
      url.searchParams.delete('repo');
      url.searchParams.delete('path');
      url.searchParams.delete('file');
      url.searchParams.delete('tail');
      url.searchParams.set('view', 'code-search');
      if (initialRepo) url.searchParams.set('repo', initialRepo);
      history.pushState({nav: 'code-search', repo: initialRepo}, '', url.pathname + url.search + url.hash);
    }
    initCodeSearch(initialRepo);
  }

  // Persist the last-visited code-search repo so re-entering the tab
  // restores it (open question #4 answered: auto-pick).
  function _csRememberLastRepo(repo) {
    try { if (repo) localStorage.setItem(_CS_LAST_KEY, repo); } catch {}
  }
  function _csRecallLastRepo() {
    try { return localStorage.getItem(_CS_LAST_KEY) || null; } catch { return null; }
  }

  async function initCodeSearch(initialRepo) {
    document.body.classList.add('code-search-active');
    document.title = 'Code search';
    if (typeof projTabsRender === 'function') projTabsRender();

    // Wire input handlers once. The view's HTML is static template
    // markup, so attaching listeners on every init would double-fire
    // them on the second visit; guard with a flag on the root.
    const view = document.getElementById('codeSearchView');
    if (view && !view._wired) {
      view._wired = true;
      _csWireHandlers();
    }

    // Paint repos from cache instantly, then reconcile in the
    // background. First-visit hit is one network round-trip; warm
    // switches are zero.
    if (_csCache.repos) {
      _csRenderRepoList(_csCache.repos);
    } else {
      const el = document.getElementById('csRepoList');
      if (el) el.innerHTML = '<div style="padding:14px 12px;color:var(--text-dim);font-size:12px">Loading repos...</div>';
    }
    afterFirstPaint(() => {
      _csFetchRepos().then(() => {
        if (!document.body.classList.contains('code-search-active')) return;
        _csRenderRepoList(_csCache.repos);
        // Once we have the live list, pick the requested repo (or the
        // remembered one, or the first).
        const picked = initialRepo
          || (_csCache.repos && _csCache.repos.find(r => r.name === _csRecallLastRepo()) && _csRecallLastRepo())
          || (_csCache.repos && _csCache.repos[0] && _csCache.repos[0].name);
        if (picked) _csSelectRepo(picked);
      }).catch((e) => {
        const el = document.getElementById('csRepoList');
        if (el) el.innerHTML = `<div style="padding:14px 12px;color:var(--red);font-size:12px">Failed to load repos: ${csEsc(e.message || e)}</div>`;
      });
    });

    // Open the terminal panel scoped to the selected repo (or none
    // if no repo yet — we'll re-open on selection).
    if (!UI_CHECK && initialRepo) {
      const pid = _csProjectId(initialRepo);
      if (pid && typeof termOpenForProject === 'function') {
        // Hack: set currentProject to a synthetic value so
        // termOpenForProject's stale-response guards line up.
        currentProject = {name: pid, path: '', is_project: true, repos: []};
        afterPageQuiet(() => termOpenForProject(pid));
      }
    }
  }

  // ── Code Search helpers ──────────────────────────────────────────
  function csEsc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  async function _csFetchRepos() {
    const r = await fetch('/api/code-search/repos');
    if (!r.ok) throw new Error(`/api/code-search/repos → ${r.status}`);
    _csCache.repos = await r.json();
  }

  async function _csFetchStats(repo) {
    if (_csCache.stats.has(repo)) return _csCache.stats.get(repo);
    try {
      const r = await fetch(`/api/code-search/repos/${encodeURIComponent(repo)}/stats`);
      if (!r.ok) throw new Error(`stats ${r.status}`);
      const data = await r.json();
      _csCache.stats.set(repo, data);
      return data;
    } catch { return null; }
  }

  function _csRenderRepoList(repos) {
    const el = document.getElementById('csRepoList');
    if (!el) return;
    const filter = (_csState.filter || '').toLowerCase();
    const list = (repos || []).filter(r => !filter || r.name.toLowerCase().includes(filter));
    if (!list.length) {
      el.innerHTML = '<div style="padding:14px 12px;color:var(--text-dim);font-size:12px;font-style:italic">no repos match</div>';
      return;
    }
    el.innerHTML = list.map(r => {
      const last = r.last || {};
      const active = r.name === _csState.repo ? ' active' : '';
      const meta = last.when ? `${csEsc(last.when)} · ${csEsc(last.who || '')}` : 'no commits';
      return `<div class="repo-item${active}" data-repo="${csEsc(r.name)}" title="${csEsc(r.name)} · ${csEsc(last.subj || '')}">
        <div class="repo-name">${csEsc(r.name)}</div>
        <div class="repo-meta">${meta}</div>
      </div>`;
    }).join('');
  }

  function _csSelectRepo(repo) {
    if (!repo) return;
    _csState.repo = repo;
    _csState.openFile = null;
    _csState.fileLines = null;
    _csState.selectedRange = null;
    _csState.rangeScope = false;
    _csState.hitLine = null;
    _csRememberLastRepo(repo);
    // URL: keep repo in the query string so reload restores.
    try {
      const url = new URL(window.location);
      url.searchParams.set('view', 'code-search');
      url.searchParams.set('repo', repo);
      url.searchParams.delete('path');
      history.replaceState(null, '', url);
    } catch {}
    _csRenderRepoList(_csCache.repos);
    _csRenderHeader();
    _csRenderResults({mode: _csState.mode, results: [], truncated: false});
    _csRenderPreview();
    _csRenderGitRail();
    // Kick off background stats fetch (badges).
    _csFetchStats(repo).then(() => _csRenderHeader());
    // Auto-load whole-repo log so the git rail isn't empty.
    _csLoadLog().then(() => _csRenderGitRail());
    // If query was already typed, re-run it for the new repo.
    if (_csState.query) _csRunSearch();
    // Re-scope the terminal panel to this repo.
    if (!UI_CHECK) {
      const pid = _csProjectId(repo);
      currentProject = {name: pid, path: '', is_project: true, repos: []};
      if (typeof termOpenForProject === 'function') termOpenForProject(pid);
    }
  }

  function _csRenderHeader() {
    const repo = _csState.repo;
    if (!repo) {
      document.getElementById('csTitle').textContent = '— pick a repo —';
      document.getElementById('csClone').textContent = '';
      document.getElementById('csBadges').innerHTML = '';
      document.getElementById('csSearchHint').textContent = 'pick a repo';
      return;
    }
    const r = (_csCache.repos || []).find(x => x.name === repo) || {};
    const stats = _csCache.stats.get(repo) || {};
    document.getElementById('csTitle').textContent = repo;
    document.getElementById('csClone').textContent = stats.clone || '';
    const last = r.last || {};
    const badges = [];
    if (r.branch) badges.push(`<span class="h-badge">branch <span class="v">${csEsc(r.branch)}</span></span>`);
    if (typeof stats.commits === 'number') badges.push(`<span class="h-badge">${stats.commits.toLocaleString()} <span class="v">commits</span></span>`);
    if (typeof stats.contribs === 'number') badges.push(`<span class="h-badge">${stats.contribs} <span class="v">contributors</span></span>`);
    if (typeof stats.files === 'number') badges.push(`<span class="h-badge">${stats.files} <span class="v">files</span></span>`);
    if (last.when) badges.push(`<span class="h-badge">last <span class="v">${csEsc(last.when)}</span></span>`);
    document.getElementById('csBadges').innerHTML = badges.join('');
    document.getElementById('csSearchHint').textContent = _csState.query ? 'press Enter to search' : 'type a query, then Enter';
  }

  async function _csRunSearch() {
    const repo = _csState.repo;
    const q = (_csState.query || '').trim();
    const mode = _csState.mode;
    if (!repo) return;
    if (!q) { _csRenderResults({mode, results: [], truncated: false}); return; }
    const cacheKey = `${repo}|${mode}|${q}`;
    if (_csCache.search.has(cacheKey)) {
      _csRenderResults(_csCache.search.get(cacheKey));
      return;
    }
    document.getElementById('csSearchHint').textContent = 'searching…';
    try {
      const r = await fetch(`/api/code-search/repos/${encodeURIComponent(repo)}/search?mode=${mode}&q=${encodeURIComponent(q)}&limit=200`);
      if (!r.ok) throw new Error(`search ${r.status}`);
      const data = await r.json();
      _csCache.search.set(cacheKey, data);
      _csRenderResults(data);
    } catch (e) {
      _csRenderResults({mode, results: [], truncated: false, error: e.message || String(e)});
    }
  }

  function _csRenderResults(data) {
    const list = document.getElementById('csResultsList');
    const label = document.getElementById('csResultsLabel');
    const hint = document.getElementById('csSearchHint');
    if (!list || !label) return;
    const mode = data.mode || _csState.mode;
    const results = data.results || [];
    if (data.error) {
      list.innerHTML = `<div class="res-empty" style="color:var(--red)">${csEsc(data.error)}</div>`;
      label.textContent = 'Error';
      hint.textContent = '';
      return;
    }
    if (!results.length) {
      list.innerHTML = `<div class="res-empty">${_csState.query ? 'no matches' : 'type a query and press Enter'}</div>`;
      label.textContent = mode === 'filenames' ? 'Filenames' : 'Code';
      hint.textContent = _csState.query ? `0 results${data.truncated ? ' (truncated)' : ''}` : 'pick a query';
      return;
    }
    if (mode === 'filenames') {
      list.innerHTML = results.map(f => `
        <div class="res-item" data-path="${csEsc(f.path)}">
          <div class="path">${csEsc(f.path)}</div>
          <div class="meta">${f.size != null ? `${f.size.toLocaleString()} bytes` : ''}</div>
        </div>
      `).join('');
      label.textContent = `Filenames — ${results.length} match${results.length === 1 ? '' : 'es'}`;
    } else {
      list.innerHTML = results.map(c => `
        <div class="res-item" data-path="${csEsc(c.path)}" data-line="${c.line}">
          <div><span class="path">${csEsc(c.path)}</span><span class="line">:${c.line}</span></div>
          <div class="snippet">${csEsc(c.snippet || '')}</div>
        </div>
      `).join('');
      label.textContent = `Code — ${results.length} hit${results.length === 1 ? '' : 's'}`;
    }
    hint.textContent = data.truncated ? `${results.length} (truncated)` : `${results.length} results`;
  }

  // Map extensions → highlight.js language id. Anything not listed
  // falls back to plaintext (no colors, still wraps + line-numbered).
  // Extra packs loaded above include scala, groovy, protobuf so those
  // entries are real here, not no-ops.
  const _CS_LANG_BY_EXT = {
    py: 'python', pyi: 'python', ipynb: 'json',
    scala: 'scala', sc: 'scala',
    java: 'java', kt: 'kotlin', kts: 'kotlin',
    js: 'javascript', mjs: 'javascript', cjs: 'javascript',
    ts: 'typescript', tsx: 'typescript', jsx: 'javascript',
    json: 'json', json5: 'json',
    yml: 'yaml', yaml: 'yaml',
    md: 'markdown', markdown: 'markdown',
    sh: 'bash', bash: 'bash', zsh: 'bash',
    gradle: 'groovy', groovy: 'groovy',
    sql: 'sql', html: 'xml', htm: 'xml', xml: 'xml',
    css: 'css', scss: 'scss',
    toml: 'ini', ini: 'ini', cfg: 'ini',
    avsc: 'json',
    proto: 'protobuf',
    go: 'go', rs: 'rust', rb: 'ruby', php: 'php',
    c: 'c', h: 'c', cpp: 'cpp', cc: 'cpp', hpp: 'cpp',
    dockerfile: 'dockerfile', make: 'makefile', mk: 'makefile',
    drl: 'java',  // Drools .drl files look enough like Java to highlight usefully
    acl: 'json',  // ACL files are JSON-shaped in the LinkedIn repos
  };

  function _csLangForPath(path) {
    if (!path) return 'plaintext';
    const base = path.split('/').pop() || '';
    if (base.toLowerCase() === 'dockerfile') return 'dockerfile';
    if (base.toLowerCase() === 'makefile') return 'makefile';
    const m = /\.([A-Za-z0-9]+)$/.exec(base);
    if (!m) return 'plaintext';
    return _CS_LANG_BY_EXT[m[1].toLowerCase()] || 'plaintext';
  }

  // Either the path's natural language, or — for notebooks — python,
  // since we transform ipynb JSON into Python-shaped source before
  // displaying it.
  function _csEffectiveLang(path) {
    if (path && path.toLowerCase().endsWith('.ipynb')) return 'python';
    return _csLangForPath(path);
  }

  // Transform a Jupyter notebook's JSON into a readable flat source
  // string with per-cell separators. The result reads like one big
  // Python file: markdown / raw cells become `# …` comment blocks,
  // so the python highlighter renders them as dim comments, while
  // code cells render with full syntax highlighting. The user sees
  // code instead of raw ipynb JSON. Returns null on parse failure
  // so the caller falls back to the original content.
  function _csTransformIpynb(content) {
    let nb;
    try { nb = JSON.parse(content); } catch { return null; }
    if (!nb || !Array.isArray(nb.cells)) return null;
    const out = [];
    nb.cells.forEach((cell, i) => {
      const kind = String(cell.cell_type || 'raw');
      let src = cell.source;
      if (Array.isArray(src)) src = src.join('');
      src = String(src == null ? '' : src);
      out.push(`# ─── cell ${i + 1} · ${kind} ───────────────────────────────────────`);
      if (kind === 'markdown' || kind === 'raw') {
        src.split('\n').forEach(line => out.push('# ' + line));
      } else {
        out.push(src);
      }
      out.push('');
    });
    return out.join('\n');
  }

  // Build per-line highlighted rows from a file's source. The whole
  // file is highlighted as one block so multi-line tokens (strings,
  // doc-comments) resolve correctly, then we split the resulting HTML
  // by `\n` and wrap each line in a row with line number + match /
  // current-line classes. Browsers auto-close unbalanced spans at
  // row boundaries, which is visually equivalent for color purposes.
  // Returns the row-HTML join (one string); caller injects.
  function _csHighlightRowsHtml(lines, path, opts) {
    opts = opts || {};
    const lang = _csEffectiveLang(path);
    const raw = lines.join('\n');
    let rows;
    try {
      const out = (window.hljs && window.hljs.getLanguage && window.hljs.getLanguage(lang))
        ? window.hljs.highlight(raw, {language: lang, ignoreIllegals: true}).value
        : csEsc(raw);
      rows = out.split('\n');
    } catch (e) {
      rows = csEsc(raw).split('\n');
    }
    const hits = new Set(opts.hits || []);
    const current = opts.current || null;
    const rowClass = opts.rowClass || 'file-line';
    const lnClass = opts.lnClass || 'ln';
    const srcClass = opts.srcClass || 'src';
    return rows.map((html, i) => {
      const ln = i + 1;
      const cls = rowClass
        + (hits.has(ln) ? ' hit' : '')
        + (ln === current ? ' sel' : '');
      return `<div class="${cls}" data-line="${ln}"><span class="${lnClass}">${ln}</span><span class="${srcClass}">${html || '&nbsp;'}</span></div>`;
    }).join('');
  }

  // Single-click action: inline preview in the workspace's right pane.
  // Fast, scoped, terminal stays visible. Double-click → full modal
  // (_csOpenFileModal below) for the rich syntax-highlighted view.
  async function _csOpenFilePreview(path, line) {
    if (!_csState.repo || !path) return;
    _csState.openFile = path;
    _csState.selectedRange = null;
    _csState.rangeScope = false;
    // ipynb match lines refer to the raw JSON; the rendered view is
    // re-flowed, so the original line number isn't meaningful. Drop
    // the jump-to-line cue for notebooks — the user can still see the
    // hits highlighted via the match-rail rendering in the modal.
    const isIpynb = path.toLowerCase().endsWith('.ipynb');
    _csState.hitLine = (line && !isIpynb) ? line : null;
    document.getElementById('csRangePop')?.classList.remove('on');
    document.getElementById('csPreviewPath').textContent = path;
    document.getElementById('csPreviewHint').textContent = 'loading…';
    const cacheKey = `${_csState.repo}|${path}`;
    let data;
    if (_csCache.file.has(cacheKey)) {
      data = _csCache.file.get(cacheKey);
    } else {
      try {
        const r = await fetch(`/api/code-search/repos/${encodeURIComponent(_csState.repo)}/file?path=${encodeURIComponent(path)}`);
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || `file ${r.status}`);
        }
        data = await r.json();
        _csCache.file.set(cacheKey, data);
      } catch (err) {
        const body = document.getElementById('csFileBody');
        if (body) {
          Array.from(body.children).forEach(el => { if (el.id !== 'csRangePop') el.remove(); });
          body.insertBefore(Object.assign(document.createElement('div'), {
            className: 'preview-empty',
            textContent: `Error loading file: ${err.message || err}`,
          }), document.getElementById('csRangePop'));
        }
        return;
      }
    }
    let content = data.content || '';
    if (isIpynb) {
      const transformed = _csTransformIpynb(content);
      if (transformed != null) content = transformed;
    }
    await ensureHighlight().catch(() => {});
    _csState.fileLines = content.split('\n');
    _csRenderPreview();
    _csState.rangeScope = false;
    _csLoadLog().then(() => _csRenderGitRail());
  }

  function _csRenderPreview() {
    const body = document.getElementById('csFileBody');
    const pop = document.getElementById('csRangePop');
    if (!body) return;
    Array.from(body.children).forEach(el => { if (el.id !== 'csRangePop') el.remove(); });
    const lines = _csState.fileLines;
    if (!_csState.openFile || !lines) {
      const empty = document.createElement('div');
      empty.className = 'preview-empty';
      empty.textContent = _csState.repo
        ? 'Click a result on the left to preview · double-click for the full modal'
        : 'Pick a repo on the far left.';
      body.insertBefore(empty, pop);
      document.getElementById('csPreviewPath').textContent = 'no file open';
      document.getElementById('csPreviewHint').textContent = _csState.repo ? 'click a result to preview · double-click for full modal' : '';
      return;
    }
    const path = _csState.openFile;
    const isIpynb = path.toLowerCase().endsWith('.ipynb');
    document.getElementById('csPreviewPath').textContent = path;
    document.getElementById('csPreviewHint').textContent =
      `${lines.length} lines · ${_csEffectiveLang(path)}${isIpynb ? ' · notebook rendered as code' : ''} · double-click for modal`;
    // ipynb match line numbers refer to the JSON, not the rendered
    // view — skip hit highlighting in that case.
    const matches = isIpynb ? [] : _csMatchesForFile(path);
    const html = _csHighlightRowsHtml(lines, path, {
      hits: matches.map(m => m.line),
      current: _csState.hitLine,
      rowClass: 'file-line',
      lnClass: 'ln',
      srcClass: 'src',
    });
    // Drop the new rows in front of the persistent range-pop element.
    pop.insertAdjacentHTML('beforebegin', html);
    if (_csState.hitLine) {
      requestAnimationFrame(() => {
        const row = body.querySelector(`.file-line[data-line="${_csState.hitLine}"]`);
        if (row) row.scrollIntoView({block: 'center'});
      });
    }
  }

  async function csShowRangeHistory() {
    if (!_csState.selectedRange || !_csState.openFile) return;
    _csState.rangeScope = true;
    document.getElementById('csGitList').innerHTML = '<div class="git-empty">loading git log -L…</div>';
    await _csLoadLog();
    _csRenderGitRail();
  }
  window.csShowRangeHistory = csShowRangeHistory;

  // Double-click action: open the rich modal for `path`, jumping to
  // `line` if provided. The match rail lists every search hit in this
  // same file (pulled from the cached code-search results so we don't
  // re-query the backend).
  async function _csOpenFileModal(path, line) {
    if (!_csState.repo || !path) return;
    _csState.openFile = path;
    _csState.selectedRange = null;
    _csState.rangeScope = false;
    const isIpynb = path.toLowerCase().endsWith('.ipynb');
    _csState.hitLine = (line && !isIpynb) ? line : null;

    const overlay = document.getElementById('csFileModalOverlay');
    overlay.classList.add('on');
    document.getElementById('csFileModalPath').textContent = path;
    document.getElementById('csFileModalLang').textContent = _csEffectiveLang(path) + (isIpynb ? ' (notebook)' : '');
    document.getElementById('csFileModalMatches').textContent = 'loading…';
    document.getElementById('csCodeBlock').innerHTML = '<div style="padding:18px;color:var(--text-dim)">loading file…</div>';
    document.getElementById('csMatchRailList').innerHTML = '';

    const cacheKey = `${_csState.repo}|${path}`;
    let data;
    if (_csCache.file.has(cacheKey)) {
      data = _csCache.file.get(cacheKey);
    } else {
      try {
        const r = await fetch(`/api/code-search/repos/${encodeURIComponent(_csState.repo)}/file?path=${encodeURIComponent(path)}`);
        if (!r.ok) {
          const e = await r.json().catch(() => ({}));
          throw new Error(e.detail || `file ${r.status}`);
        }
        data = await r.json();
        _csCache.file.set(cacheKey, data);
      } catch (err) {
        document.getElementById('csCodeBlock').innerHTML = `<div style="padding:18px;color:var(--red)">Error loading file: ${csEsc(err.message || err)}</div>`;
        document.getElementById('csFileModalMatches').textContent = 'error';
        return;
      }
    }
    let content = data.content || '';
    if (isIpynb) {
      const transformed = _csTransformIpynb(content);
      if (transformed != null) content = transformed;
    }
    await ensureHighlight().catch(() => {});
    _csState.fileLines = content.split('\n');

    // For non-ipynb files, surface the cached search hits in the
    // match rail. For ipynb the hit line numbers refer to the raw
    // JSON, not the rendered view; show a placeholder explaining
    // that and skip the per-line highlighting.
    const rawMatches = _csMatchesForFile(path);
    const matchesInFile = isIpynb ? [] : rawMatches;
    document.getElementById('csFileModalMatches').textContent = isIpynb
      ? `${_csState.fileLines.length} lines · notebook rendered as code${rawMatches.length ? ` · ${rawMatches.length} raw JSON hit${rawMatches.length === 1 ? '' : 's'} (Cmd-F to find)` : ''}`
      : (matchesInFile.length
          ? `${matchesInFile.length} match${matchesInFile.length === 1 ? '' : 'es'} for "${csEsc(_csState.query)}"`
          : `${_csState.fileLines.length} lines · no hits in this file for "${csEsc(_csState.query)}"`);
    _csRenderMatchRail(matchesInFile, line);
    _csRenderCodeWithHighlight(_csState.fileLines, path, matchesInFile, _csState.hitLine);

    _csState.rangeScope = false;
    _csLoadLog().then(() => _csRenderGitRail());
  }

  function _csMatchesForFile(path) {
    // Pull every code-mode hit for this file from the cached search.
    // Falls back to a single synthesized hit so the rail still shows
    // the "jumped-to" line when the user opened from a filename hit.
    const q = (_csState.query || '').trim();
    const blob = _csCache.search.get(`${_csState.repo}|code|${q}`);
    const hits = (blob && blob.results || []).filter(r => r.path === path);
    return hits;
  }

  function _csRenderMatchRail(matches, currentLine) {
    const host = document.getElementById('csMatchRailList');
    const head = document.getElementById('csMatchRailHead');
    if (!host) return;
    if (!matches.length) {
      head.textContent = 'No matches in this file';
      host.innerHTML = '<div class="match-empty">Open from a filename — no code hits to jump to. The whole file is below.</div>';
      return;
    }
    head.textContent = `${matches.length} match${matches.length === 1 ? '' : 'es'}`;
    host.innerHTML = matches.map(m => `
      <div class="match-item${m.line === currentLine ? ' active' : ''}" data-line="${m.line}">
        <span class="ln">L${m.line}</span>
        <div class="snippet">${csEsc(m.snippet || '')}</div>
      </div>
    `).join('');
    host.querySelectorAll('.match-item').forEach(el => {
      el.addEventListener('click', () => {
        const ln = parseInt(el.dataset.line, 10);
        host.querySelectorAll('.match-item').forEach(x => x.classList.toggle('active', x === el));
        _csJumpToLine(ln);
      });
    });
  }

  // Modal-side renderer: same one-block highlight then per-line wrap
  // pipeline as the inline preview (_csHighlightRowsHtml), with the
  // modal's `code-line` / `csln` / `csrc` class names.
  function _csRenderCodeWithHighlight(lines, path, matches, jumpLine) {
    const codeBlock = document.getElementById('csCodeBlock');
    codeBlock.className = 'language-' + _csEffectiveLang(path) + ' hljs';
    codeBlock.innerHTML = _csHighlightRowsHtml(lines, path, {
      hits: (matches || []).map(m => m.line),
      current: jumpLine,
      rowClass: 'code-line',
      lnClass: 'csln',
      srcClass: 'csrc',
    });
    if (jumpLine) {
      requestAnimationFrame(() => {
        const row = codeBlock.querySelector(`.code-line[data-line="${jumpLine}"]`);
        if (row) row.scrollIntoView({block: 'center'});
      });
    }
  }

  function _csJumpToLine(ln) {
    const block = document.getElementById('csCodeBlock');
    if (!block) return;
    block.querySelectorAll('.code-line.current').forEach(el => el.classList.remove('current'));
    const row = block.querySelector(`.code-line[data-line="${ln}"]`);
    if (row) {
      row.classList.add('current');
      row.scrollIntoView({block: 'center', behavior: 'smooth'});
    }
    _csState.hitLine = ln;
  }

  function csCloseFileModal() {
    document.getElementById('csFileModalOverlay')?.classList.remove('on');
  }
  window.csCloseFileModal = csCloseFileModal;

  async function _csLoadLog() {
    const repo = _csState.repo;
    if (!repo) return;
    const path = _csState.openFile;
    const range = (_csState.rangeScope && _csState.selectedRange) ? _csState.selectedRange : null;
    const key = `${repo}|${path || ''}|${range ? range.join(',') : ''}`;
    if (_csCache.log.has(key)) return _csCache.log.get(key);
    let url = `/api/code-search/repos/${encodeURIComponent(repo)}/log?limit=80`;
    if (path) url += `&path=${encodeURIComponent(path)}`;
    if (range) url += `&start=${range[0]}&end=${range[1]}`;
    try {
      const r = await fetch(url);
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || `log ${r.status}`);
      }
      const data = await r.json();
      _csCache.log.set(key, data);
      return data;
    } catch (e) {
      return [{_error: e.message || String(e)}];
    }
  }

  function _csRenderGitRail() {
    const list = document.getElementById('csGitList');
    const scope = document.getElementById('csGitScope');
    if (!list || !scope) return;
    if (!_csState.repo) {
      scope.textContent = '—';
      list.innerHTML = '<div class="git-empty">Pick a repo to see commits.</div>';
      return;
    }
    const path = _csState.openFile;
    const range = (_csState.rangeScope && _csState.selectedRange) ? _csState.selectedRange : null;
    if (range) scope.textContent = `lines ${range[0]}–${range[1]}`;
    else if (path) scope.textContent = path.split('/').pop();
    else scope.textContent = 'whole repo';
    const key = `${_csState.repo}|${path || ''}|${range ? range.join(',') : ''}`;
    const cached = _csCache.log.get(key);
    if (!cached) {
      list.innerHTML = '<div class="git-empty">loading…</div>';
      return;
    }
    if (cached[0] && cached[0]._error) {
      list.innerHTML = `<div class="git-empty" style="color:var(--red)">${csEsc(cached[0]._error)}</div>`;
      return;
    }
    if (!cached.length) {
      list.innerHTML = '<div class="git-empty">No history for this scope.</div>';
      return;
    }
    list.innerHTML = cached.map(c => `
      <div class="git-item${range ? ' range' : ''}" data-sha="${csEsc(c.sha)}">
        <div class="sha">${csEsc(c.sha)}</div>
        <div class="subj">${csEsc(c.subj || '')}</div>
        <div class="who">${csEsc(c.who || '')} · ${csEsc(c.when || '')}</div>
      </div>
    `).join('');
  }

  async function _csOpenCommit(sha) {
    if (!_csState.repo || !sha) return;
    let url = `/api/code-search/repos/${encodeURIComponent(_csState.repo)}/commit/${encodeURIComponent(sha)}`;
    if (_csState.openFile) url += `?path=${encodeURIComponent(_csState.openFile)}`;
    const overlay = document.getElementById('csDrawerOverlay');
    overlay.classList.add('on');
    document.getElementById('csDrawerSha').textContent = sha;
    document.getElementById('csDrawerSubj').textContent = 'loading…';
    document.getElementById('csDrawerMeta').textContent = '';
    document.getElementById('csDrawerBody').textContent = '';
    try {
      const r = await fetch(url);
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        throw new Error(e.detail || `commit ${r.status}`);
      }
      const c = await r.json();
      document.getElementById('csDrawerSha').textContent = c.sha || sha;
      document.getElementById('csDrawerSubj').textContent = c.subj || '';
      const meta = `<b>${csEsc(c.who || '')}</b>${c.email ? ` &lt;${csEsc(c.email)}&gt;` : ''} · ${csEsc(c.when_iso || '')} (${csEsc(c.when || '')})` + (c.body ? `<br><span style="color:var(--text-primary)">${csEsc(c.body)}</span>` : '');
      document.getElementById('csDrawerMeta').innerHTML = meta;
      document.getElementById('csDrawerBody').innerHTML = (c.diff || '').split('\n').map(l => {
        let cls = '';
        if (l.startsWith('+') && !l.startsWith('+++')) cls = 'add';
        else if (l.startsWith('-') && !l.startsWith('---')) cls = 'del';
        else if (l.startsWith('@@')) cls = 'hunk';
        else if (l.startsWith('diff ') || l.startsWith('index ') || l.startsWith('---') || l.startsWith('+++')) cls = 'meta';
        return `<span class="dline ${cls}">${csEsc(l) || '&nbsp;'}</span>`;
      }).join('');
    } catch (e) {
      document.getElementById('csDrawerSubj').textContent = `Error: ${e.message || e}`;
    }
  }

  function csCloseDrawer() {
    document.getElementById('csDrawerOverlay')?.classList.remove('on');
  }
  window.csCloseDrawer = csCloseDrawer;

  function _csWireHandlers() {
    document.getElementById('csRepoFilter').addEventListener('input', (e) => {
      _csState.filter = e.target.value;
      _csRenderRepoList(_csCache.repos);
    });
    document.getElementById('csRepoList').addEventListener('click', (e) => {
      const it = e.target.closest('.repo-item');
      if (!it) return;
      _csSelectRepo(it.dataset.repo);
    });
    document.getElementById('csModes').addEventListener('click', (e) => {
      const btn = e.target.closest('button[data-mode]');
      if (!btn) return;
      _csState.mode = btn.dataset.mode;
      document.querySelectorAll('#csModes button').forEach(b => b.classList.toggle('active', b === btn));
      _csRunSearch();
    });
    const input = document.getElementById('csSearchInput');
    input.addEventListener('input', (e) => { _csState.query = e.target.value; });
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); _csRunSearch(); }
    });
    document.getElementById('csResultsList').addEventListener('click', (e) => {
      const it = e.target.closest('.res-item');
      if (!it) return;
      document.querySelectorAll('#csResultsList .res-item').forEach(el => el.classList.toggle('active', el === it));
      const ln = it.dataset.line ? parseInt(it.dataset.line, 10) : null;
      _csOpenFilePreview(it.dataset.path, ln);
    });
    document.getElementById('csResultsList').addEventListener('dblclick', (e) => {
      const it = e.target.closest('.res-item');
      if (!it) return;
      const ln = it.dataset.line ? parseInt(it.dataset.line, 10) : null;
      _csOpenFileModal(it.dataset.path, ln);
    });
    // Line-range selection on the inline preview body — drag across
    // line numbers to pop the "git log -L" affordance. Mirrors the
    // POC pattern.
    let _csSel = null;
    const fileBody = document.getElementById('csFileBody');
    fileBody.addEventListener('mousedown', (e) => {
      const row = e.target.closest('.file-line');
      if (!row) return;
      _csSel = {a: parseInt(row.dataset.line, 10), b: parseInt(row.dataset.line, 10)};
    });
    fileBody.addEventListener('mousemove', (e) => {
      if (!_csSel) return;
      const row = e.target.closest('.file-line');
      if (!row) return;
      _csSel.b = parseInt(row.dataset.line, 10);
      const lo = Math.min(_csSel.a, _csSel.b), hi = Math.max(_csSel.a, _csSel.b);
      fileBody.querySelectorAll('.file-line').forEach(r => {
        const ln = parseInt(r.dataset.line, 10);
        r.classList.toggle('sel', ln >= lo && ln <= hi);
      });
    });
    document.addEventListener('mouseup', () => {
      if (!_csSel) return;
      const lo = Math.min(_csSel.a, _csSel.b), hi = Math.max(_csSel.a, _csSel.b);
      const pop = document.getElementById('csRangePop');
      if (hi > lo) {
        _csState.selectedRange = [lo, hi];
        document.getElementById('csRangeLines').textContent = `lines ${lo}–${hi}`;
        if (pop) {
          pop.classList.add('on');
          const first = fileBody.querySelector(`.file-line[data-line="${lo}"]`);
          if (first) pop.style.top = (first.offsetTop + 4) + 'px';
        }
      } else {
        _csState.selectedRange = null;
        if (pop) pop.classList.remove('on');
        fileBody.querySelectorAll('.file-line.sel').forEach(r => r.classList.remove('sel'));
      }
      _csSel = null;
    });
    document.getElementById('csGitList').addEventListener('click', (e) => {
      const it = e.target.closest('.git-item');
      if (!it) return;
      _csOpenCommit(it.dataset.sha);
    });
    // File modal controls.
    document.getElementById('csFileModalCopy').addEventListener('click', () => {
      const path = document.getElementById('csFileModalPath').textContent || '';
      try { navigator.clipboard.writeText(path); } catch {}
    });
    document.getElementById('csFileModalHist').addEventListener('click', () => {
      // Already updates the right rail when the file opens — this just
      // closes the modal so the user can see it.
      csCloseFileModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      const overlay = document.getElementById('csFileModalOverlay');
      if (overlay && overlay.classList.contains('on')) csCloseFileModal();
    });
  }

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
      goToProductivity({replace: true});
    } else if (view === 'workspace') {
      goToWorkspace({replace: true});
    } else if (view === 'code-search') {
      goToCodeSearch({replace: true, repo: params.get('repo') || null});
    } else if (view === 'logs') {
      goToLogs({
        replace: true,
        file: params.get('file') || LOGS_DEFAULT_FILE,
        tail: params.get('tail') || LOGS_DEFAULT_TAIL,
      });
    } else if (repo) {
      _swapViewState();
      fetchRepos().then(projects => {
        projectsList = projects;
        const proj = projects.find(p => p.repos.some(r => r.path === repo));
        if (proj) selectRepo(proj.name);
      });
    } else {
      _swapViewState();
      document.body.classList.add('home-active');
      initHome();
      projTabsRender();
    }
  });

  function setHomeTab(tab) {
    homeTab = tab;
    location.hash = '#' + tab;
    for (const name of ['dashboard', 'snoozed', 'timeline', 'search']) {
      const btn = document.getElementById('homeTab' + name[0].toUpperCase() + name.slice(1));
      if (btn) btn.classList.toggle('active', name === tab);
    }
    renderHomePanel();
  }

  async function renderHomePanel() {
    const el = document.getElementById('homePanel');
    const tab = homeTab;
    if (tab !== 'search') paintHomeShell(el, tab);
    if (tab === 'search') {
      renderSearch(el);
      return;
    }
    const fill = async () => {
      if (_homeRendering || homeTab !== tab) return;
      _homeRendering = true;
      try {
        if (tab === 'dashboard') await renderDashboard(el);
        else if (tab === 'snoozed') await renderSnoozed(el);
        else if (tab === 'timeline') await renderTimeline(el);
      } finally {
        _homeRendering = false;
      }
    };
    if (document.readyState !== 'complete' || performance.now() < 2000) {
      afterPageQuiet(fill);
    } else {
      await fill();
    }
  }

  function priorityClass(p) { return p ? 'p-' + p.toLowerCase() : ''; }
  function fmtDate(iso) { return iso ? iso.slice(0, 10) : '—'; }
  function escapeHtml(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function paintHomeShell(el, tab) {
    if (!el) return;
    if (tab === 'dashboard') {
      el.innerHTML = `
        <div class="filter-row">
          <button class="btn-primary" disabled>+ New project</button>
        </div>
        <div class="p-list">
          <div class="p-section">
            <div class="p-section-head">Pinned</div>
            <div class="p-row"><span></span><span></span><span class="p-name" style="color:var(--text-dim)">Loading dashboard...</span><span></span><span></span><span></span><span></span></div>
          </div>
        </div>`;
    } else if (tab === 'snoozed') {
      el.innerHTML = `
        <div class="snooze-section">
          <h3>Ready for review <span class="count">...</span></h3>
          <p class="snooze-empty">Loading snoozed projects...</p>
        </div>`;
    } else if (tab === 'timeline') {
      el.innerHTML = `
        <h2>Timeline</h2>
        <div class="bucket">
          <h3>Open work</h3>
          <p style="color:var(--text-dim)">Loading timeline...</p>
        </div>`;
    }
  }

  async function renderDashboard(el) {
    const [idx, dueRaw, wsData] = await Promise.all([
      fetch('/api/index').then(r => r.json()),
      fetch('/api/tasks/due?days=7').then(r => r.json()),
      // Best-effort: a failure here (network hiccup, old server) must not
      // take down the rest of the dashboard — it only costs the "other
      // workspaces" sections below.
      fetch('/api/workspaces/projects').then(r => r.ok ? r.json() : null).catch(() => null),
    ]);
    const allProjects = idx.projects || [];
    const dueSoon = dueRaw.filter(t => t.status !== 'done');
    if (wsData && wsData.active) currentWorkspaceId = wsData.active;
    // Every OTHER registered workspace (not the one being served right
    // now) — rendered as its own minimal section below so projects on a
    // volume that isn't currently active (e.g. the SSD, when `local` is
    // active) are still visible, not just the active workspace's.
    const otherWorkspaces = ((wsData && wsData.workspaces) || [])
      .filter(w => w.id !== (wsData && wsData.active));
    // The workspace being served right now — its projects (the flat index)
    // render grouped under its own header below. Falls back to `current`
    // (always present in the payload) and, when /api/workspaces/projects
    // failed entirely, to null — which keeps the old ungrouped layout.
    const activeWs = ((wsData && wsData.workspaces) || []).find(w => w.active)
      || (wsData && wsData.current) || null;

    const dueStrip = dueSoon.length === 0 ? '' : `
      <div class="due-strip">
        ${dueSoon.slice(0, 30).map(t => `
          <span class="due-chip" data-pid="${escapeHtml(t.project_id)}" title="${escapeHtml(t.project_id)}  #${t.task_id}">
            <span class="chip ${priorityClass(t.priority)}">${escapeHtml(t.priority || '')}</span>
            <span>${escapeHtml(t.title)}</span>
            <span class="due-date">${fmtDate(t.due)}</span>
          </span>
        `).join('')}
      </div>`;

    // Pinned pseudo-projects: always one click away.
    const pseudoRows = [
      pseudoRowHtml({
        id: LOGS_PROJECT_ID, icon: '$', label: 'logs',
        desc: 'Terminal-style view of errors, backend, and frontend logs.',
        href: '/?view=logs',
      }),
      pseudoRowHtml({
        id: SELF_PROJECT_ID, icon: '🛠️', label: 'productivity',
        desc: 'This monorepo itself — commits on main, uncommitted changes, and repo-level tasks. Excludes repositories/.',
        href: '/?view=productivity',
      }),
      pseudoRowHtml({
        id: CEREBRO_PROJECT_ID, icon: '🧠', label: 'cerebro',
        desc: 'Personal knowledge base — wikis, logs, meetings, roadmaps, and every project\'s docs.',
        href: '/?view=cerebro',
      }),
      pseudoRowHtml({
        id: CODE_SEARCH_PROJECT_ID, icon: '🔍', label: 'code-search',
        desc: 'Search filenames and code across every repo under repositories/. Click a result for an inline preview, double-click for the syntax-highlighted modal.',
        href: '/?view=code-search',
      }),
    ].join('');

    // Split real projects into "Active" (status=active, not held) and "Rest"
    // (everything else, including held/paused/done/archived). Sort each
    // group: priority asc, then id asc.
    const priKey = p => ({P0:0,P1:1,P2:2,P3:3}[p.priority] ?? 9);
    const sortProjects = (arr) => arr.slice().sort((a, b) => {
      const dp = priKey(a) - priKey(b);
      if (dp !== 0) return dp;
      return (a.id || '').localeCompare(b.id || '');
    });
    const active = [];
    const rest = [];
    for (const p of allProjects) {
      const st = holdState(p.hold).state;
      if (p.status === 'active' && st !== 'held') active.push(p);
      else rest.push(p);
    }
    const activeRows = sortProjects(active).map(p => projectRowHtml(p)).join('');
    const restRows = sortProjects(rest).map(p => projectRowHtml(p)).join('');

    const activeSection = `
      <div class="p-section">
        <div class="p-section-head">Active <span class="count">${active.length}</span></div>
        ${activeRows || '<div class="p-row"><span></span><span></span><span class="p-name" style="color:var(--text-dim);font-style:italic">No active projects.</span><span></span><span></span><span></span><span></span></div>'}
      </div>`;
    const restSection = rest.length === 0 ? '' : `
      <div class="p-section">
        <div class="p-section-head">Paused / Done / Archived / Snoozed <span class="count">${rest.length}</span></div>
        ${restRows}
      </div>`;
    const otherWorkspaceSections = otherWorkspaces.map(otherWorkspaceSectionHtml).join('');

    // Group the active workspace's projects (Active + Paused/Done/...)
    // under a workspace header, mirroring the per-workspace sections that
    // follow. Rows, sub-sections, and click behavior inside are unchanged.
    const activeWsGroup = activeWs
      ? `<div class="ws-group ws-group-current" data-ws="${escapeHtml(activeWs.id)}">
          ${wsGroupHeadHtml(activeWs, {isActive: true, count: allProjects.length})}
          ${activeSection}
          ${restSection}
        </div>`
      : activeSection + restSection;

    el.innerHTML = `
      <div class="filter-row">
        <button class="btn-primary" id="dashNewBtn">+ New project</button>
      </div>
      ${dueStrip}
      <div class="p-list">
        <div class="p-section" id="dashKpis"></div>
        <div class="p-section" id="dashServers">
          <div class="p-section-head">Servers <span class="count">…</span></div>
          <div class="srv-empty">Loading servers…</div>
        </div>
        <div class="p-section" id="dashTerms">
          <div class="p-section-head">Terminals <span class="count">…</span></div>
          <div class="term-empty">Loading terminal sessions…</div>
        </div>
        <div class="p-section">
          <div class="p-section-head">Pinned</div>
          ${pseudoRows}
        </div>
        ${activeWsGroup}
        ${otherWorkspaceSections}
      </div>
    `;

    el.querySelector('#dashNewBtn').addEventListener('click', onHomeNewProject);
    el.querySelector('#dashServers').addEventListener('click', dashServersOnClick);
    el.querySelector('#dashTerms').addEventListener('click', dashTermsOnClick);
    // Independent poll loop for the two sections above — see dashStartPolling.
    // Stopped/restarted here (not just at first mount) so navigating back to
    // the dashboard never stacks a second interval. Under UI_CHECK persistent
    // timers stay off (check-ui.sh contract); the one-shot tick still fills
    // the sections for the smoke test.
    if (!UI_CHECK) dashStartPolling();
    dashPollTick();
    el.querySelectorAll('.due-chip').forEach(chip => {
      chip.addEventListener('click', () => {
        const pid = chip.getAttribute('data-pid');
        if (pid) goToProjectById(pid);
      });
    });

    // Build a pid → project lookup once so edit handlers don't have to
    // re-query the index on every chip click.
    const projByPid = Object.fromEntries(allProjects.map(p => [p.id, p]));

    // Row interactions: click anywhere on a row to toggle expand, UNLESS the
    // target was an editable chip/button (those open their own popover).
    el.querySelectorAll('.p-row').forEach(row => {
      row.addEventListener('click', (e) => {
        if (e.target.closest('[data-edit]')) return;      // chip clicks → popover
        if (e.target.closest('[data-act]')) return;       // detail buttons handle themselves
        if (e.target.closest('.p-detail')) return;        // bubbled from detail
        if (row.classList.contains('ws-other')) {
          // Project from a non-active workspace: switch to it, then open.
          const pid = row.getAttribute('data-pid');
          const wsId = row.getAttribute('data-ws');
          const ws = otherWorkspaces.find(w => w.id === wsId);
          if (pid && ws) openProjectInWorkspace(pid, ws);
          return;
        }
        const href = row.getAttribute('data-href');
        if (href) {
          // Pseudo-rows (productivity, cerebro, code-search). Route
          // in-page so the dashboard → pseudo-project click doesn't
          // full-reload.
          if (href === '/?view=logs') goToLogs();
          else if (href === '/?view=productivity') goToProductivity();
          else if (href === '/?view=cerebro') goToCerebro();
          else if (href === '/?view=code-search') goToCodeSearch();
          else window.location.href = href;  // unknown — full reload
          return;
        }
        row.classList.toggle('expanded');
      });
    });

    // Chip click-to-edit (priority, due, LOE, description).
    el.querySelectorAll('[data-edit]').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        // Find the owning row → project id → project record.
        const row = chip.closest('.p-row') || chip.closest('.p-detail')?.previousElementSibling;
        const pid = row?.getAttribute('data-pid');
        const proj = pid && projByPid[pid];
        if (!proj) return;
        const field = chip.getAttribute('data-edit');
        editProjectField(chip, proj, field, () => {
          // After save: re-render the whole dashboard (cheapest + keeps
          // the other derived fields — due-soon strip, sort order — in
          // sync with the project's new state).
          renderDashboard(el);
        });
      });
    });

    el.querySelectorAll('.p-detail [data-act]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const pid = btn.getAttribute('data-pid');
        const act = btn.getAttribute('data-act');
        if (act === 'open' && pid) goToProjectById(pid);
        else if (act === 'snooze' && pid) openSnoozeModal(pid);
        else if (act === 'unhold' && pid) clearProjectHold(pid);
      });
    });
    updateSnoozedBadge(allProjects);
  }

  // ─── Dashboard: Servers section ─────────────────────────────────────────
  // GET /api/servers → {"servers": [{project_id, workspace, path, port,
  // state: "running"|"starting"|"unhealthy"|"stopped", desired, healthy,
  // session_name, attach_command, session_created, restarts, has_stop,
  // health_url}]}. Rows come from every registered workspace, sorted
  // (workspace, project_id) — a project id can repeat across workspaces, so
  // every lookup/action below is keyed on the (workspace, project_id) pair,
  // never project_id alone. Renders into #dashServers only — never touches
  // the rest of renderDashboard's output. If the endpoint 404s (backend not
  // deployed yet in this environment) the section hides itself; polling
  // keeps retrying quietly so it appears without a reload once the backend
  // ships. Start/stop/restart post to
  // /api/servers/{workspace}/{project_id}/{start|stop|restart}.

  // All three dashboard sections (#dashKpis, #dashServers, #dashTerms)
  // render in two hosts: the home dashboard (`.p-section`s inside `.p-list`
  // → `.p-section-head` header) and the productivity workbench (`.s-section`
  // cards in `.s-workbench-grid` → `<h2>` header, matching the
  // Attention/Open-tasks cards around them). Same ids, same render/poll
  // code — only the header markup differs (see dashSectionHeadHtml).
  //
  // The ids are shared, but in-page view swaps (_swapViewState) hide the
  // previous view WITHOUT clearing its DOM — so after home → productivity
  // a stale hidden #dashServers can still sit in #homePanel (which comes
  // before #content in document order and would win getElementById). Always
  // resolve the container through the ACTIVE view's host instead.
  function dashSectionEl(id) {
    const host = document.body.classList.contains('self-active')
      ? document.getElementById('content')
      : document.body.classList.contains('home-active')
        ? document.getElementById('homePanel')
        : null;
    return host ? host.querySelector('#' + id) : null;
  }

  function dashSectionHeadHtml(el, label, count) {
    const countHtml = count == null ? '' : `<span class="count">${count}</span>`;
    return el.classList.contains('s-section')
      ? `<h2>${label} ${countHtml}</h2>`
      : `<div class="p-section-head">${label} ${countHtml}</div>`;
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

  function pseudoRowHtml({id, icon, label, desc, href}) {
    return `
      <div class="p-row pseudo" data-pid="${escapeHtml(id)}" data-href="${escapeHtml(href)}" role="button" tabindex="0" title="${escapeHtml(desc)}">
        <span class="p-status pseudo"></span>
        <span class="p-pri none">—</span>
        <span class="p-name"><span class="icon">${icon}</span>${escapeHtml(label)}</span>
        <span class="p-repos"></span>
        <span class="p-tasks empty">pinned</span>
        <span class="p-prs"></span>
        <span class="p-loe empty">—</span>
        <span class="p-due empty">—</span>
        <span></span>
        <span class="p-caret">›</span>
      </div>`;
  }

  function projectRowHtml(p) {
    const counts = p.task_counts || {};
    const openCount = (counts.todo || 0) + (counts.in_progress || 0) + (counts.blocked || 0);
    const hasBlocked = (counts.blocked || 0) > 0;
    const info = holdState(p.hold);
    const statusCls = info.state === 'held' ? 'held'
                   : info.state === 'ready' ? 'ready'
                   : (p.status || 'active');
    const statusTitle = info.state === 'held' ? `snoozed until ${fmtDate((p.hold||{}).until) || '?'}`
                   : info.state === 'ready' ? 'snooze expired — ready for review'
                   : (p.status || 'active');
    const priHtml = p.priority
      ? `<span class="chip editable ${priorityClass(p.priority)}" data-edit="priority" title="click to change">${escapeHtml(p.priority)}</span>`
      : `<span class="p-pri none editable" data-edit="priority" title="set priority">—</span>`;
    const labels = p.labels || [];
    const repoChips = labels.slice(0, 3)
      .map(l => `<span class="repo-chip">@${escapeHtml(l)}</span>`).join('');
    const repoMore = labels.length > 3 ? `<span class="repo-more">+${labels.length - 3}</span>` : '';
    const tasksCls = openCount === 0 ? 'empty' : (hasBlocked ? 'has-blocked' : '');
    const tasksText = openCount === 0 ? '—'
                   : (hasBlocked ? `${openCount} open · ${counts.blocked} blocked` : `${openCount} open`);
    const prCounts = p.pr_counts || {};
    const prOpen = prCounts.open || 0;
    const prMerged = prCounts.merged || 0;
    const prChip = (prOpen || prMerged)
      ? `<span class="p-prs" title="${prOpen} open · ${prMerged} merged PRs">${prOpen ? `<span class="pr-pill pr-open">${prOpen} open</span>` : ''}${prMerged ? `<span class="pr-pill pr-merged">${prMerged}✓</span>` : ''}</span>`
      : '<span class="p-prs"></span>';
    const dueCls = p.due && Date.parse(p.due) < Date.now() ? 'overdue' : (p.due ? '' : 'empty');
    const dueText = p.due ? 'due ' + fmtDate(p.due) : '—';
    const loeCls = (p.loe == null || p.loe === '') ? 'empty' : '';
    const loeText = (p.loe == null || p.loe === '') ? '—' : `${p.loe}d`;

    const missing = projectMissingFields(p);
    const rowExtraCls = missing.length ? ' missing-required' : '';
    const missingChip = missing.length
      ? `<span class="chip missing" data-edit="${escapeHtml(missing[0])}" title="click to set ${escapeHtml(missing[0])}">⚠ missing: ${missing.join(', ')}</span>`
      : '<span></span>';

    const desc = (p.description || '').trim();
    const tags = (p.tags || []).map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('');
    const labelChips = (p.labels || []).map(l => `<span class="chip">@${escapeHtml(l)}</span>`).join('');
    const holdBadge = holdBadgeHtml(p.hold, info);
    const editBtns = `
      <button type="button" class="mini-btn" data-edit="priority" title="Edit priority">P: ${escapeHtml(p.priority || '—')}</button>
      <button type="button" class="mini-btn" data-edit="due" title="Edit due date">Due: ${p.due ? escapeHtml(fmtDate(p.due)) : '—'}</button>
      <button type="button" class="mini-btn" data-edit="loe" title="Edit LOE (days)">LOE: ${(p.loe == null || p.loe === '') ? '—' : escapeHtml(String(p.loe)) + 'd'}</button>
      <button type="button" class="mini-btn" data-edit="description" title="Edit description">&#x270E; Description</button>`;
    const actions = `
      <div class="p-actions">
        <button type="button" class="mini-btn primary" data-act="open" data-pid="${escapeHtml(p.id)}">Open →</button>
        ${editBtns}
        ${info.state === 'none' ? `<button type="button" class="mini-btn" data-act="snooze" data-pid="${escapeHtml(p.id)}">&#x1F4A4; Snooze</button>` : ''}
        ${info.state !== 'none' ? `<button type="button" class="mini-btn" data-act="snooze" data-pid="${escapeHtml(p.id)}">Reschedule</button>` : ''}
        ${info.state !== 'none' ? `<button type="button" class="mini-btn danger" data-act="unhold" data-pid="${escapeHtml(p.id)}">Clear hold</button>` : ''}
      </div>`;
    const prsHtml = prSectionHtml(p);
    const detail = `
      <div class="p-detail">
        <p class="p-desc${desc ? '' : ' empty'}">${desc ? escapeHtml(desc) : 'No description.'}</p>
        ${holdBadge}
        ${(tags || labelChips) ? `<div class="p-chips">${tags}${labelChips}</div>` : ''}
        <div class="counts">
          <span class="todo">todo ${counts.todo || 0}</span> ·
          <span class="in_progress">in_progress ${counts.in_progress || 0}</span> ·
          <span class="blocked">blocked ${counts.blocked || 0}</span> ·
          <span class="done">done ${counts.done || 0}</span>
        </div>
        ${prsHtml}
        ${actions}
      </div>`;

    // Every real project on the dashboard belongs to the workspace the
    // server is currently serving — badge it so it reads the same as the
    // "other workspace" sections below, even though here it's constant.
    const wsBadge = currentWorkspaceId
      ? `<span class="ws-badge" title="workspace: ${escapeHtml(currentWorkspaceId)}">${escapeHtml(currentWorkspaceId)}</span>`
      : '';

    return `
      <div class="p-row${rowExtraCls}" data-pid="${escapeHtml(p.id)}" role="button" tabindex="0" title="${escapeHtml(statusTitle)}">
        <span class="p-status ${statusCls}" title="${escapeHtml(statusTitle)}"></span>
        ${priHtml}
        <span class="p-name">${escapeHtml(p.id)}${wsBadge}</span>
        <span class="p-repos">${repoChips}${repoMore}</span>
        <span class="p-tasks ${tasksCls}">${tasksText}</span>
        ${prChip}
        <span class="p-loe editable ${loeCls}" data-edit="loe" title="click to edit LOE">${loeText}</span>
        <span class="p-due editable ${dueCls}" data-edit="due" title="click to edit due date">${dueText}</span>
        ${missingChip}
        <span class="p-caret">›</span>
      </div>
      ${detail}`;
  }

  // ─── Other-workspace dashboard rows ─────────────────────────────────────
  // The server only ever serves ONE workspace's full project metadata
  // (task counts, priority, due dates, ...). For every OTHER registered
  // workspace all we have is a directory listing of project ids (from
  // /api/workspaces/projects), so these rows are intentionally minimal —
  // just the id and a badge — with a click that switches workspace then
  // opens the project.
  function otherWorkspaceRowHtml(pid, wsId) {
    return `
      <div class="p-row ws-other" data-pid="${escapeHtml(pid)}" data-ws="${escapeHtml(wsId)}" role="button" tabindex="0" title="Open ${escapeHtml(pid)} (switches to workspace ${escapeHtml(wsId)})">
        <span class="p-status"></span>
        <span class="p-pri none">—</span>
        <span class="p-name">${escapeHtml(pid)}<span class="ws-badge" title="workspace: ${escapeHtml(wsId)}">${escapeHtml(wsId)}</span></span>
        <span class="p-repos"></span>
        <span class="p-tasks empty">—</span>
        <span class="p-prs"></span>
        <span class="p-loe empty">—</span>
        <span class="p-due empty">—</span>
        <span></span>
        <span class="p-caret">›</span>
      </div>`;
  }

  // Workspace group header for the Home dashboard: workspace name, id
  // badge, project count, and the workspace path as a right-aligned muted
  // subtitle. The active (currently served) workspace gets an accent
  // highlight + "active" pill. Shared by the active group and every
  // other-workspace section so all of Home reads as one grouped list.
  function wsGroupHeadHtml(w, {isActive = false, count = null} = {}) {
    const label = escapeHtml(w.name || w.id);
    const badge = `<span class="ws-badge" title="workspace: ${escapeHtml(w.id)}">${escapeHtml(w.id)}</span>`;
    const pill = isActive ? '<span class="ws-active-pill">active</span>' : '';
    const cnt = count == null ? '' : `<span class="count">${count}</span>`;
    const path = w.path ? `<span class="ws-group-path" title="${escapeHtml(w.path)}">${escapeHtml(w.path)}</span>` : '';
    return `<div class="p-section-head ws-group-head${isActive ? ' ws-group-head-active' : ''}">${label} ${badge} ${pill} ${cnt} ${path}</div>`;
  }

  // One dashboard section per NON-active registered workspace. `unavailable`
  // comes straight from /api/workspaces/projects — set when that
  // workspace's own directory scan hit fsguard's 503 (stalled volume) — and
  // greys the section out with the same message fsguard would show
  // elsewhere, rather than silently dropping it from the dashboard.
  function otherWorkspaceSectionHtml(w) {
    if (w.unavailable) {
      const msg = w.detail || `resource is not available for workspace ${w.id}`;
      return `
        <div class="p-section ws-section ws-group ws-unavailable" data-ws="${escapeHtml(w.id)}">
          ${wsGroupHeadHtml(w)}
          <div class="p-row"><span></span><span></span><span class="p-name" style="color:var(--text-dim);font-style:italic">${escapeHtml(msg)}</span><span></span><span></span><span></span><span></span></div>
        </div>`;
    }
    const projects = w.projects || [];
    const rows = projects.map(pid => otherWorkspaceRowHtml(pid, w.id)).join('');
    return `
      <div class="p-section ws-section ws-group" data-ws="${escapeHtml(w.id)}">
        ${wsGroupHeadHtml(w, {count: projects.length})}
        ${rows || '<div class="p-row"><span></span><span></span><span class="p-name" style="color:var(--text-dim);font-style:italic">No projects.</span><span></span><span></span><span></span><span></span></div>'}
      </div>`;
  }

  // Open a project that belongs to `ws` (a row from /api/workspaces/projects
  // or /api/workspaces — needs `.id` and `.path`). If it's not the active
  // workspace, switch first (the server only ever serves one workspace's
  // project.json/tasks.json at a time, so there's no way to read the
  // target project's data without switching to it), then land straight on
  // it — full reload is unavoidable here since switching workspace replaces
  // the entire served index.
  async function openProjectInWorkspace(pid, ws) {
    if (!pid || !ws || !ws.id) return;
    if (ws.id === currentWorkspaceId) { goToProjectById(pid); return; }
    try {
      const r = await fetch('/api/workspaces/use', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: ws.id}),
      });
      if (!r.ok) throw new Error(await r.text());
      const wsPath = (ws.path || '').replace(/\/+$/, '');
      location.href = '/?project=' + encodeURIComponent(wsPath + '/projects/' + pid);
    } catch (e) {
      console.error('failed to open project in workspace', ws.id, e);
    }
  }

  // Keep the "Snoozed" tab badge in sync with current project data. Counts
  // expired holds (ready-for-review) and falls back to total holds if none
  // are ready yet.
  function updateSnoozedBadge(projects) {
    const badge = document.getElementById('snoozedBadge');
    if (!badge) return;
    let ready = 0, held = 0;
    (projects || []).forEach(p => {
      const s = holdState(p.hold).state;
      if (s === 'ready') ready++;
      else if (s === 'held') held++;
    });
    if (ready > 0) {
      badge.textContent = ready;
      badge.classList.add('ready');
      badge.style.display = '';
    } else if (held > 0) {
      badge.textContent = held;
      badge.classList.remove('ready');
      badge.style.display = '';
    } else {
      badge.style.display = 'none';
    }
  }

  async function renderSnoozed(el) {
    const idx = await fetch('/api/index').then(r => r.json());
    const all = idx.projects || [];
    const ready = [];
    const held = [];
    all.forEach(p => {
      const s = holdState(p.hold);
      if (s.state === 'ready') ready.push({ p, info: s });
      else if (s.state === 'held') held.push({ p, info: s });
    });
    // Soonest first — ready-to-review items first (longest past), then
    // held items sorted by how soon they resurface.
    ready.sort((a, b) => a.info.ms - b.info.ms);          // most-negative (longest past) first
    held.sort((a, b) => a.info.ms - b.info.ms);           // soonest resurface first

    const readyCards = ready.map(({p, info}) => snoozedCardHtml(p, info)).join('');
    const heldCards = held.map(({p, info}) => snoozedCardHtml(p, info)).join('');

    el.innerHTML = `
      <div class="snooze-section">
        <h3>&#x23F0; Ready for review <span class="count">${ready.length}</span></h3>
        ${ready.length === 0 ? '<p class="snooze-empty">Nothing is ready to re-check yet. Snoozed projects will show here when their timer expires.</p>' : `<div class="project-grid">${readyCards}</div>`}
      </div>
      <div class="snooze-section">
        <h3>&#x1F4A4; Snoozed <span class="count">${held.length}</span></h3>
        ${held.length === 0 ? '<p class="snooze-empty">No active snoozes. Open any project card on the Dashboard and click "Snooze" to park it.</p>' : `<div class="project-grid">${heldCards}</div>`}
      </div>
    `;
    el.querySelectorAll('.card[data-pid]').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('a')) return;
        if (e.target.closest('.mini-btn')) return;
        const pid = card.getAttribute('data-pid');
        if (pid) goToProjectById(pid);
      });
    });
    el.querySelectorAll('.mini-btn[data-act]').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const pid = btn.getAttribute('data-pid');
        const act = btn.getAttribute('data-act');
        if (act === 'snooze') openSnoozeModal(pid);
        else if (act === 'unhold') clearProjectHold(pid);
      });
    });
    updateSnoozedBadge(all);
  }

  // Card variant for the Snoozed tab — reuses projectCardHtml so the layout
  // stays consistent, but we rely on the shared hold badge + action buttons
  // already rendered by projectCardHtml.
  function snoozedCardHtml(p, _info) {
    return projectCardHtml(p);
  }

  function projectCardHtml(p) {
    const counts = p.task_counts || {};
    const priorityChip = p.priority ? `<span class="chip ${priorityClass(p.priority)}">${escapeHtml(p.priority)}</span>` : '';
    const dueChip = p.due ? `<span class="chip">due ${fmtDate(p.due)}</span>` : '';
    const tags = (p.tags || []).map(t => `<span class="chip">${escapeHtml(t)}</span>`).join('');
    const labels = (p.labels || []).map(t => `<span class="chip">@${escapeHtml(t)}</span>`).join('');
    const desc = p.description ? `<p class="desc">${escapeHtml(p.description)}</p>` : '';
    const holdInfo = holdState(p.hold);
    const cardCls = holdInfo.state === 'held' ? ' held' : holdInfo.state === 'ready' ? ' ready-review' : '';
    const holdBadge = holdBadgeHtml(p.hold, holdInfo);
    const prs = prSectionHtml(p);
    const actions = `
      <div class="card-actions">
        ${holdInfo.state === 'none' ? `<button type="button" class="mini-btn" data-act="snooze" data-pid="${escapeHtml(p.id)}">&#x1F4A4; Snooze</button>` : ''}
        ${holdInfo.state !== 'none' ? `<button type="button" class="mini-btn primary" data-act="snooze" data-pid="${escapeHtml(p.id)}">Reschedule</button>` : ''}
        ${holdInfo.state !== 'none' ? `<button type="button" class="mini-btn danger" data-act="unhold" data-pid="${escapeHtml(p.id)}">Clear hold</button>` : ''}
      </div>`;
    return `
      <div class="card${cardCls}" data-pid="${escapeHtml(p.id)}" tabindex="0" role="button">
        <h3>${escapeHtml(p.id)}</h3>
        ${desc}
        <div>${priorityChip}${dueChip}${tags}${labels}</div>
        ${holdBadge}
        <div class="counts" style="margin-top:8px">
          <span class="todo">todo ${counts.todo || 0}</span>
          <span class="in_progress">in_progress ${counts.in_progress || 0}</span>
          <span class="blocked">blocked ${counts.blocked || 0}</span>
          <span class="done">done ${counts.done || 0}</span>
        </div>
        ${prs}
        ${actions}
      </div>`;
  }

  // Render the PR section for a project (used by both the dashboard row's
  // expanded detail and the snoozed-tab card). Returns an empty string if
  // the project has no PRs registered. Sorts open first, then closed, then
  // merged; truncates to a few visible items with a "+N more" footer.
  function prSectionHtml(p) {
    const prs = p.prs || [];
    if (prs.length === 0) return '';
    const counts = p.pr_counts || {};
    const statRank = (s) => {
      const v = (s || '').toLowerCase();
      if (v === 'open') return 0;
      if (v === 'closed') return 1;
      if (v === 'merged') return 2;
      return 3;
    };
    const statCls = (s) => {
      const v = (s || '').toLowerCase();
      if (v === 'open') return 'pr-open';
      if (v === 'merged') return 'pr-merged';
      if (v === 'closed') return 'pr-closed';
      return 'pr-other';
    };
    const ordered = prs.slice().sort((a, b) => statRank(a.status) - statRank(b.status));
    const visible = ordered.slice(0, 5);
    const hidden = ordered.length - visible.length;
    const items = visible.map(pr => {
      const cls = statCls(pr.status);
      const status = `<span class="pr-status ${cls}">${escapeHtml(pr.status || '?')}</span>`;
      const title = escapeHtml(pr.title || pr.url || '(no title)');
      const tip = escapeHtml(pr.title || pr.url || '');
      const body = pr.url
        ? `<a class="pr-title" href="${escapeHtml(pr.url)}" target="_blank" rel="noopener" title="${tip}" onclick="event.stopPropagation()">${title}</a>`
        : `<span class="pr-title" title="${tip}">${title}</span>`;
      return `<li class="pr-item">${status}${body}</li>`;
    }).join('');
    const moreItem = hidden > 0 ? `<li class="pr-more">+${hidden} more</li>` : '';
    const stats = [];
    if (counts.open)   stats.push(`<span class="pr-stat pr-open">${counts.open} open</span>`);
    if (counts.merged) stats.push(`<span class="pr-stat pr-merged">${counts.merged} merged</span>`);
    if (counts.closed) stats.push(`<span class="pr-stat pr-closed">${counts.closed} closed</span>`);
    return `
      <div class="pr-section">
        <div class="pr-header">
          <span class="pr-label">PRs (${prs.length})</span>
          ${stats.join('')}
        </div>
        <ul class="pr-list">${items}${moreItem}</ul>
      </div>`;
  }

  // Hold helpers: classify a project's `hold` field and format badges.
  // `state`:
  //   'none'  — no hold set
  //   'held'  — hold.until still in the future
  //   'ready' — hold.until has passed; project is waiting for review
  function holdState(hold) {
    if (!hold || !hold.until) return { state: 'none', ms: 0 };
    const until = Date.parse(hold.until);
    if (Number.isNaN(until)) return { state: 'none', ms: 0 };
    const now = Date.now();
    return { state: until <= now ? 'ready' : 'held', ms: until - now, until };
  }

  function fmtRelative(ms) {
    const absMs = Math.abs(ms);
    const mins = Math.round(absMs / 60000);
    if (mins < 60) return mins + 'm';
    const hrs = Math.round(mins / 60);
    if (hrs < 48) return hrs + 'h';
    const days = Math.round(hrs / 24);
    if (days < 14) return days + 'd';
    return Math.round(days / 7) + 'w';
  }

  function holdBadgeHtml(hold, info) {
    if (!hold || info.state === 'none') return '';
    const reason = hold.reason ? `<span class="hold-reason">${escapeHtml(hold.reason)}</span>` : '';
    const url = hold.url ? `<a href="${escapeHtml(hold.url)}" target="_blank" onclick="event.stopPropagation()">&#x1F517; link</a>` : '';
    const when = info.state === 'ready'
      ? `<span class="hold-time">ready ${fmtRelative(info.ms)} ago</span>`
      : `<span class="hold-time">in ${fmtRelative(info.ms)}</span>`;
    const icon = info.state === 'ready' ? '&#x23F0;' : '&#x1F4A4;';
    return `<div class="hold-badge ${info.state === 'ready' ? 'ready' : ''}">${icon} ${when}${reason ? ' · ' + reason : ''}${url ? ' · ' + url : ''}</div>`;
  }

  // ─── Inline field edit (priority / due / LOE / description) ───
  // Shared by the dashboard rows, the attributes bar on the project view,
  // and anywhere else we show editable project metadata. Writes go through
  // /api/projects/<id>/field which wraps `lab project set`. Callers pass a
  // `onSaved` hook so the local UI can refresh without a full page reload.

  // Required fields that trigger the "⚠ missing" warning when null.
  const PROJECT_REQUIRED_FIELDS = ['priority', 'due', 'loe'];

  function projectMissingFields(p) {
    const missing = [];
    for (const f of PROJECT_REQUIRED_FIELDS) {
      const v = p[f];
      if (v === null || v === undefined || v === '') missing.push(f);
    }
    return missing;
  }

  function positionFieldPopover(anchor) {
    const pop = document.getElementById('fieldPopover');
    if (!pop || !anchor) return;
    const rect = anchor.getBoundingClientRect();
    // Open below the anchor; flip up if it would overflow the viewport.
    const desiredTop = rect.bottom + window.scrollY + 4;
    const desiredLeft = rect.left + window.scrollX;
    pop.style.top = `${desiredTop}px`;
    pop.style.left = `${desiredLeft}px`;
    // After content renders we can also correct right-overflow.
    requestAnimationFrame(() => {
      const pr = pop.getBoundingClientRect();
      const vw = window.innerWidth;
      if (pr.right > vw - 8) {
        pop.style.left = `${Math.max(8, vw - pr.width - 8) + window.scrollX}px`;
      }
    });
  }

  let _fieldPopoverCloser = null;
  function openFieldPopover(anchor, title, innerHtml, onBind) {
    closeFieldPopover();
    const pop = document.getElementById('fieldPopover');
    if (!pop) return;
    pop.innerHTML = `<div class="fp-title">${escapeHtml(title)}</div>${innerHtml}<div class="fp-err" data-err></div>`;
    pop.classList.add('open');
    positionFieldPopover(anchor);
    if (onBind) onBind(pop);
    // Close on outside click (next tick so the opening click doesn't close it).
    _fieldPopoverCloser = (e) => {
      if (!pop.contains(e.target)) closeFieldPopover();
    };
    setTimeout(() => document.addEventListener('click', _fieldPopoverCloser), 0);
  }

  function closeFieldPopover() {
    const pop = document.getElementById('fieldPopover');
    if (!pop) return;
    pop.classList.remove('open');
    pop.innerHTML = '';
    if (_fieldPopoverCloser) {
      document.removeEventListener('click', _fieldPopoverCloser);
      _fieldPopoverCloser = null;
    }
  }

  async function saveProjectField(pid, field, value, errEl) {
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(pid)}/field`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({field, value}),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        const msg = body.detail || r.statusText;
        if (errEl) errEl.textContent = msg; else alert(`Failed to save ${field}: ${msg}`);
        return null;
      }
      return await r.json();
    } catch (e) {
      const msg = e && e.message || String(e);
      if (errEl) errEl.textContent = msg; else alert(`Failed to save ${field}: ${msg}`);
      return null;
    }
  }

  function openPriorityPopover(anchor, pid, current, onSaved) {
    const opts = ['P0','P1','P2','P3'];
    const buttons = opts.map(p => {
      const sel = current === p ? ' selected' : '';
      return `<button type="button" class="fp-opt${sel}" data-val="${p}">${p}</button>`;
    }).join('');
    const inner = `
      <div class="fp-opts">${buttons}</div>
      <div class="fp-row"><button type="button" class="secondary" data-val="">Clear</button></div>`;
    openFieldPopover(anchor, 'Priority', inner, (pop) => {
      pop.querySelectorAll('[data-val]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const val = btn.getAttribute('data-val');
          const err = pop.querySelector('[data-err]');
          const updated = await saveProjectField(pid, 'priority', val, err);
          if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
        });
      });
    });
  }

  function openDuePopover(anchor, pid, current, onSaved) {
    const val = current || '';
    const inner = `
      <input type="date" id="fpDue" value="${escapeHtml(val)}" />
      <div class="fp-row">
        <button type="button" class="secondary" data-act="clear">Clear</button>
        <button type="button" data-act="save">Save</button>
      </div>`;
    openFieldPopover(anchor, 'Due date', inner, (pop) => {
      const input = pop.querySelector('#fpDue');
      input.focus();
      const err = pop.querySelector('[data-err]');
      pop.querySelector('[data-act="save"]').addEventListener('click', async () => {
        const v = input.value || '';
        if (!v) { err.textContent = 'pick a date or click Clear'; return; }
        const updated = await saveProjectField(pid, 'due', v, err);
        if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
      });
      pop.querySelector('[data-act="clear"]').addEventListener('click', async () => {
        const updated = await saveProjectField(pid, 'due', '', err);
        if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') pop.querySelector('[data-act="save"]').click();
        if (e.key === 'Escape') closeFieldPopover();
      });
    });
  }

  function openLoePopover(anchor, pid, current, onSaved) {
    const val = (current == null) ? '' : String(current);
    const inner = `
      <input type="number" id="fpLoe" min="0" step="0.5" value="${escapeHtml(val)}" placeholder="e.g. 3" />
      <div class="fp-title" style="margin: 4px 2px 0; font-size: 10px; text-transform: none; letter-spacing: 0;">Level of effort (days)</div>
      <div class="fp-row">
        <button type="button" class="secondary" data-act="clear">Clear</button>
        <button type="button" data-act="save">Save</button>
      </div>`;
    openFieldPopover(anchor, 'LOE', inner, (pop) => {
      const input = pop.querySelector('#fpLoe');
      input.focus();
      input.select();
      const err = pop.querySelector('[data-err]');
      pop.querySelector('[data-act="save"]').addEventListener('click', async () => {
        const v = input.value;
        if (v === '') { err.textContent = 'enter a number or click Clear'; return; }
        const updated = await saveProjectField(pid, 'loe', v, err);
        if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
      });
      pop.querySelector('[data-act="clear"]').addEventListener('click', async () => {
        const updated = await saveProjectField(pid, 'loe', '', err);
        if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
      });
      input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') pop.querySelector('[data-act="save"]').click();
        if (e.key === 'Escape') closeFieldPopover();
      });
    });
  }

  function openStatusPopover(anchor, pid, current, onSaved) {
    const opts = ['active','paused','done','archived'];
    const buttons = opts.map(s => {
      const sel = current === s ? ' selected' : '';
      return `<button type="button" class="fp-opt${sel}" data-val="${s}">${s}</button>`;
    }).join('');
    openFieldPopover(anchor, 'Status', `<div class="fp-opts">${buttons}</div>`, (pop) => {
      pop.querySelectorAll('[data-val]').forEach(btn => {
        btn.addEventListener('click', async () => {
          const err = pop.querySelector('[data-err]');
          const updated = await saveProjectField(pid, 'status', btn.getAttribute('data-val'), err);
          if (updated) { closeFieldPopover(); if (onSaved) onSaved(updated); }
        });
      });
    });
  }

  // Routing entry point: pick the right popover for a field. `anchor` is the
  // DOM node we attach to; `p` is the project (read from /api/index).
  function editProjectField(anchor, p, field, onSaved) {
    if (field === 'priority') return openPriorityPopover(anchor, p.id, p.priority, onSaved);
    if (field === 'due')      return openDuePopover(anchor, p.id, p.due, onSaved);
    if (field === 'loe')      return openLoePopover(anchor, p.id, p.loe, onSaved);
    if (field === 'status')   return openStatusPopover(anchor, p.id, p.status, onSaved);
    if (field === 'description') return openDescModal(p);
  }

  // ─── Project attributes bar (below top tabs, above diff tabs) ───
  // Fetches the current project's metadata and renders editable chips
  // (status · priority · due · LOE · snooze · description ✎) + a missing
  // warning. Called on project-open and after every successful field save.

  async function refreshAttrsBar() {
    const bar = document.getElementById('projectAttrsBar');
    if (!bar) return;
    if (!currentProject || !currentProject.is_project) {
      bar.innerHTML = '';
      document.body.classList.remove('project-active');
      return;
    }
    const pid = currentProject.name;

    // Warm switch: paint synchronously from the last-known project
    // record so the bar (status / P:N / Due / LOE / description /
    // Snooze) shows instantly. Background reconcile re-paints only on
    // change. Cache miss falls through to the foreground fetch below.
    const cached = _projectAttrsCache.get(pid);
    if (cached) {
      _renderAttrsBarFromRecord(bar, pid, cached);
      Promise.resolve().then(async () => {
        try {
          const r = await fetch(`/api/projects/${encodeURIComponent(pid)}`);
          if (!r.ok) return;
          const fresh = await r.json();
          const prev = _projectAttrsCache.get(pid);
          _projectAttrsCache.set(pid, fresh);
          if (prev && JSON.stringify(prev) === JSON.stringify(fresh)) return;
          if (!currentProject || currentProject.name !== pid) return;
          _renderAttrsBarFromRecord(bar, pid, fresh);
        } catch {}
      });
      return;
    }

    let p = null;
    try {
      const r = await fetch(`/api/projects/${encodeURIComponent(pid)}`);
      if (r.ok) p = await r.json();
    } catch {}
    if (!p) { bar.innerHTML = ''; return; }
    _projectAttrsCache.set(pid, p);
    _renderAttrsBarFromRecord(bar, pid, p);
  }

  // Extracted from refreshAttrsBar so both the cold and warm-switch
  // paths share one render. Pure DOM write — no network, no state
  // mutation. Reads only what's on the project record `p` plus the
  // global `holdState` / `projectMissingFields` helpers.
  function _renderAttrsBarFromRecord(bar, pid, p) {
    const info = holdState(p.hold);
    const statusCls = p.status || 'active';
    const dueText = p.due ? fmtDate(p.due) : 'set due';
    const dueCls = p.due ? '' : 'empty';
    const loeText = (p.loe == null || p.loe === '') ? 'set LOE' : `${p.loe}d`;
    const loeCls = (p.loe == null || p.loe === '') ? 'empty' : '';
    const priText = p.priority || 'set priority';
    const priCls = p.priority ? '' : 'empty';
    const descShort = (p.description || '').trim();
    const descPreview = descShort ? (descShort.length > 50 ? descShort.slice(0, 50) + '…' : descShort) : 'set description';
    const descCls = descShort ? '' : 'empty';
    const holdHtml = info.state === 'held'
      ? `<span class="ab-hold">&#x1F4A4; snoozed · ${escapeHtml(fmtRelative(info.ms))}</span>`
      : info.state === 'ready'
        ? `<span class="ab-hold ready">&#x23F0; ready for review</span>`
        : '';
    const missing = projectMissingFields(p);
    const missingChip = missing.length
      ? `<span class="ab-chip missing" data-edit="${escapeHtml(missing[0])}" title="click to set ${escapeHtml(missing[0])}">⚠ missing: ${missing.join(', ')}</span>`
      : '';

    const proxyCount = Array.isArray(p.proxies) ? p.proxies.length : 0;
    const proxiesLabel = proxyCount ? `${proxyCount} server${proxyCount === 1 ? '' : 's'}` : 'add server';
    const proxiesCls = proxyCount ? '' : 'empty';

    bar.innerHTML = `
      <span class="ab-label">${escapeHtml(p.id)}</span>
      <span class="ab-chip status ${statusCls}" data-edit="status" title="status: click to change"><span class="v">${escapeHtml(p.status || 'active')}</span></span>
      <span class="ab-chip" data-edit="priority" title="priority: click to change">P: <span class="v ${priCls}">${escapeHtml(priText)}</span></span>
      <span class="ab-chip" data-edit="due" title="due date: click to change">Due: <span class="v ${dueCls}">${escapeHtml(dueText)}</span></span>
      <span class="ab-chip" data-edit="loe" title="level of effort (days): click to change">LOE: <span class="v ${loeCls}">${escapeHtml(loeText)}</span></span>
      <span class="ab-chip" data-edit="description" title="edit description">&#x270E; <span class="v ${descCls}">${escapeHtml(descPreview)}</span></span>
      <span class="ab-chip" data-act="proxies" title="manage proxied local servers for this project">&#x1F310; <span class="v ${proxiesCls}">${escapeHtml(proxiesLabel)}</span></span>
      ${info.state === 'none'
        ? `<span class="ab-chip" data-act="snooze" title="snooze this project">&#x1F4A4; Snooze</span>`
        : `<span class="ab-chip" data-act="snooze" title="reschedule">Reschedule</span>
           <span class="ab-chip" data-act="unhold" title="clear snooze">Clear hold</span>`}
      ${holdHtml}
      <span class="ab-spacer"></span>
      ${missingChip}
    `;

    bar.querySelectorAll('[data-edit]').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const field = chip.getAttribute('data-edit');
        editProjectField(chip, p, field, () => refreshAttrsBar());
      });
    });
    bar.querySelectorAll('[data-act]').forEach(chip => {
      chip.addEventListener('click', (e) => {
        e.stopPropagation();
        const act = chip.getAttribute('data-act');
        if (act === 'snooze') openSnoozeModal(pid);
        else if (act === 'unhold') clearProjectHold(pid);
        else if (act === 'proxies') openProxiesModal();
      });
    });
  }

  // ─── Proxies modal (manage project.json proxies[] from the UI) ───
  // Opened from the attrs-bar "Servers" chip. Lists current proxies as
  // editable rows, lets the user add/remove entries, and PUTs the
  // updated project.json back via /api/project-info. On success it
  // refreshes the attrs bar (chip count), reloads the sidebar (Servers
  // section), and invalidates the sidebar payload cache so the next
  // warm switch sees the new list.
  let _proxiesEscHandler = null;
  let _proxiesRowSeq = 0;

  function openProxiesModal() {
    if (!currentProject || !currentProject.is_project) return;
    const overlay = document.getElementById('proxiesModal');
    if (!overlay) return;
    const err = document.getElementById('proxiesError');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    // Seed rows from the cached sidebar payload (already loaded for the
    // Servers list). Falls back to a single empty row if there are no
    // proxies yet.
    const cached = _projectSidebarCache.get(currentProject.path);
    const proxies = (cached && Array.isArray(cached.proxies)) ? cached.proxies : [];
    _renderProxiesRows(proxies);
    overlay.classList.add('active');
    _proxiesEscHandler = (ev) => { if (ev.key === 'Escape') closeProxiesModal(); };
    document.addEventListener('keydown', _proxiesEscHandler);
    setTimeout(() => {
      const first = document.querySelector('#proxiesRows input[data-field="name"]');
      if (first) first.focus();
    }, 30);
  }

  function closeProxiesModal() {
    const overlay = document.getElementById('proxiesModal');
    if (overlay) overlay.classList.remove('active');
    if (_proxiesEscHandler) {
      document.removeEventListener('keydown', _proxiesEscHandler);
      _proxiesEscHandler = null;
    }
  }

  function _renderProxiesRows(proxies) {
    const host = document.getElementById('proxiesRows');
    if (!host) return;
    let html = `
      <div class="proxies-row proxies-head">
        <span>Name</span><span>Host</span><span>Port</span><span>Path</span><span>Label</span><span title="Iframe directly to host:port instead of via the lab proxy. Faster but the browser needs direct network access to the port (so it bypasses any SSH-tunnel setup where only the lab port is exposed).">Direct</span><span></span>
      </div>`;
    if (!proxies || proxies.length === 0) {
      html += `<div class="proxies-empty">No servers yet. Click <b>+ Add server</b> below to declare one.</div>`;
    } else {
      proxies.forEach(p => { html += _proxyRowHtml(p || {}); });
    }
    host.innerHTML = html;
  }

  function _proxyRowHtml(p) {
    const id = 'pr-' + (++_proxiesRowSeq);
    const directChecked = (p.mode === 'direct') ? 'checked' : '';
    return `
      <div class="proxies-row" data-row-id="${id}">
        <input type="text" data-field="name"  value="${escapeHtml(String(p.name  || ''))}" placeholder="frontend" />
        <input type="text" data-field="host"  value="${escapeHtml(String(p.host  || ''))}" placeholder="localhost" />
        <input type="text" data-field="port"  value="${escapeHtml(String(p.port == null ? '' : p.port))}" placeholder="3000" inputmode="numeric" />
        <input type="text" data-field="path"  value="${escapeHtml(String(p.path  || ''))}" placeholder="/" />
        <input type="text" data-field="label" value="${escapeHtml(String(p.label || ''))}" placeholder="(optional)" />
        <label class="proxies-direct" title="Iframe directly to host:port — skips the lab proxy."><input type="checkbox" data-field="direct" ${directChecked} /></label>
        <button type="button" class="proxies-del" title="Remove this server" onclick="removeProxyRow('${id}')">&times;</button>
      </div>`;
  }

  function addProxyRow() {
    const host = document.getElementById('proxiesRows');
    if (!host) return;
    // Clear the "no servers yet" placeholder on first add.
    const empty = host.querySelector('.proxies-empty');
    if (empty) empty.remove();
    host.insertAdjacentHTML('beforeend', _proxyRowHtml({}));
    const rows = host.querySelectorAll('.proxies-row[data-row-id]');
    const last = rows[rows.length - 1];
    if (last) {
      const nameInput = last.querySelector('input[data-field="name"]');
      if (nameInput) nameInput.focus();
    }
  }

  function removeProxyRow(rowId) {
    const row = document.querySelector(`#proxiesRows .proxies-row[data-row-id="${rowId}"]`);
    if (row) row.remove();
    // Restore the "no servers yet" hint if we just emptied the list.
    const host = document.getElementById('proxiesRows');
    if (host && !host.querySelector('.proxies-row[data-row-id]')) {
      host.insertAdjacentHTML('beforeend', `<div class="proxies-empty">No servers yet. Click <b>+ Add server</b> below to declare one.</div>`);
    }
  }

  function _collectProxiesFromRows() {
    const rows = document.querySelectorAll('#proxiesRows .proxies-row[data-row-id]');
    const out = [];
    const errors = [];
    const seenNames = new Set();
    rows.forEach((row, idx) => {
      const v = (sel) => (row.querySelector(`input[data-field="${sel}"]`) || {}).value || '';
      const name = v('name').trim();
      const host = v('host').trim();
      const portRaw = v('port').trim();
      const path = v('path').trim();
      const label = v('label').trim();
      const directEl = row.querySelector('input[data-field="direct"]');
      const direct = !!(directEl && directEl.checked);
      // Skip wholly-empty rows silently.
      if (!name && !host && !portRaw && !path && !label && !direct) return;
      if (!name) { errors.push(`Row ${idx + 1}: name is required.`); return; }
      if (!/^[A-Za-z0-9_-]+$/.test(name)) {
        errors.push(`Row ${idx + 1}: name "${name}" — letters, digits, _, - only.`); return;
      }
      if (seenNames.has(name)) {
        errors.push(`Duplicate name "${name}".`); return;
      }
      seenNames.add(name);
      if (!portRaw) { errors.push(`Row ${idx + 1}: port is required.`); return; }
      const port = parseInt(portRaw, 10);
      if (!Number.isInteger(port) || port <= 0 || port > 65535) {
        errors.push(`Row ${idx + 1}: port "${portRaw}" — must be 1..65535.`); return;
      }
      const entry = {name, port};
      if (host) entry.host = host;
      if (path) entry.path = path;
      if (label) entry.label = label;
      if (direct) entry.mode = 'direct';
      out.push(entry);
    });
    return {proxies: out, errors};
  }

  async function submitProxies(ev) {
    ev.preventDefault();
    const err = document.getElementById('proxiesError');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    const {proxies, errors} = _collectProxiesFromRows();
    if (errors.length) {
      if (err) { err.textContent = errors.join(' · '); err.classList.add('on'); }
      return;
    }
    if (!currentProject || !currentProject.is_project) { closeProxiesModal(); return; }
    // Read current project.json, swap proxies, write back. We have to
    // PUT the full document via /api/project-info; the mutation route
    // (PATCH-style) doesn't know about arbitrary array fields.
    try {
      const r = await fetch(`/api/project-info?path=${encodeURIComponent(currentProject.path)}`);
      if (!r.ok) throw new Error(`GET project-info → ${r.status}`);
      const info = await r.json();
      if (proxies.length === 0) {
        delete info.proxies;
      } else {
        info.proxies = proxies;
      }
      const put = await fetch('/api/project-info', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: currentProject.path, data: info}),
      });
      if (!put.ok) {
        const detail = await put.json().catch(() => ({}));
        throw new Error(detail.detail || `PUT project-info → ${put.status}`);
      }
    } catch (e) {
      if (err) { err.textContent = `Save failed: ${e.message || e}`; err.classList.add('on'); }
      return;
    }
    // Invalidate caches that hold the stale proxies list, then refresh.
    _projectSidebarCache.delete(currentProject.path);
    _projectAttrsCache.delete(currentProject.name);
    closeProxiesModal();
    if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
    if (typeof _refreshProjectSidebar === 'function') _refreshProjectSidebar({preserveScroll: true});
  }

  // ─── Description modal (larger than a popover — multiline) ───
  let _descSaved = null;
  function openDescModal(p) {
    _descSaved = null;
    const modal = document.getElementById('descModal');
    document.getElementById('descProjectId').value = p.id;
    document.getElementById('descText').value = p.description || '';
    document.getElementById('descError').textContent = '';
    modal.classList.add('active');
    setTimeout(() => document.getElementById('descText').focus(), 30);
  }

  function closeDescModal() {
    document.getElementById('descModal').classList.remove('active');
  }

  async function submitDesc(ev) {
    ev.preventDefault();
    const pid = document.getElementById('descProjectId').value;
    const text = document.getElementById('descText').value;
    const err = document.getElementById('descError');
    err.textContent = '';
    const updated = await saveProjectField(pid, 'description', text, err);
    if (!updated) return;
    closeDescModal();
    // Refresh whichever view is visible.
    const home = document.getElementById('homeView');
    if (home && home.offsetParent !== null) {
      const panel = document.getElementById('homePanel');
      if (panel) renderDashboard(panel);
    }
    if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
  }

  // ─── Snooze (hold) modal ───
  // Opened by the "Snooze" button on any project card. Collects duration +
  // reason + optional URL, POSTs to /api/projects/<id>/hold, and reruns the
  // home panel so the card moves to the Snoozed tab.

  let _snoozeEscHandler = null;

  function openSnoozeModal(projectId, prefill) {
    const overlay = document.getElementById('snoozeModal');
    if (!overlay) return;
    const idEl = document.getElementById('snProjectId');
    if (idEl) idEl.value = projectId;
    // Reset form
    document.getElementById('snReason').value = (prefill && prefill.reason) || '';
    document.getElementById('snUrl').value = (prefill && prefill.url) || '';
    document.getElementById('snUntilDate').value = '';
    // If caller didn't pass prefill, fetch the project's current hold so
    // reschedules keep the existing reason + URL (user almost never wants to
    // retype them).
    if (!prefill && projectId) {
      fetch('/api/projects/' + encodeURIComponent(projectId))
        .then(r => r.ok ? r.json() : null)
        .then(p => {
          if (!p || !p.hold) return;
          if (p.hold.reason) document.getElementById('snReason').value = p.hold.reason;
          if (p.hold.url) document.getElementById('snUrl').value = p.hold.url;
        })
        .catch(() => {});
    }
    const err = document.getElementById('snError');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    // Default quick-pick = 2d; wire once.
    _snoozeSetDuration('2d');
    const quick = document.getElementById('snQuick');
    if (quick && !quick._wired) {
      quick.querySelectorAll('button[data-dur]').forEach(btn => {
        btn.addEventListener('click', () => _snoozeSetDuration(btn.getAttribute('data-dur')));
      });
      quick._wired = true;
    }
    const dateInput = document.getElementById('snUntilDate');
    if (dateInput && !dateInput._wired) {
      dateInput.addEventListener('input', () => {
        if (dateInput.value) {
          // Clear quick-pick highlight to make the override explicit.
          document.getElementById('snQuick').querySelectorAll('button').forEach(b => b.classList.remove('selected'));
          _snoozeUpdateResurfaceLabel();
        }
      });
      dateInput._wired = true;
    }
    overlay.classList.add('active');
    setTimeout(() => document.getElementById('snReason')?.focus(), 30);
    _snoozeEscHandler = (e) => { if (e.key === 'Escape') closeSnoozeModal(); };
    document.addEventListener('keydown', _snoozeEscHandler);
  }

  function closeSnoozeModal() {
    const overlay = document.getElementById('snoozeModal');
    if (overlay) overlay.classList.remove('active');
    if (_snoozeEscHandler) {
      document.removeEventListener('keydown', _snoozeEscHandler);
      _snoozeEscHandler = null;
    }
  }

  function _snoozeSetDuration(dur) {
    const hidden = document.getElementById('snDuration');
    if (hidden) hidden.value = dur;
    const dateInput = document.getElementById('snUntilDate');
    if (dateInput) dateInput.value = '';
    const quick = document.getElementById('snQuick');
    if (quick) {
      quick.querySelectorAll('button').forEach(b => {
        b.classList.toggle('selected', b.getAttribute('data-dur') === dur);
      });
    }
    _snoozeUpdateResurfaceLabel();
  }

  function _snoozeUpdateResurfaceLabel() {
    const label = document.getElementById('snResurface');
    if (!label) return;
    const dateVal = document.getElementById('snUntilDate')?.value;
    let when;
    if (dateVal) {
      // End-of-day that date, local tz — matches the server's normalization.
      const d = new Date(dateVal + 'T23:59:00');
      when = d;
    } else {
      const dur = document.getElementById('snDuration')?.value || '2d';
      const m = dur.match(/^(\d+)([mhdw])$/);
      if (!m) { label.textContent = ''; return; }
      const qty = parseInt(m[1], 10);
      const unit = m[2];
      const secs = ({m: 60, h: 3600, d: 86400, w: 604800}[unit]) * qty;
      when = new Date(Date.now() + secs * 1000);
    }
    label.textContent = 'Resurfaces ' + when.toLocaleString(undefined, {
      weekday: 'short', month: 'short', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
  }

  async function submitSnooze(ev) {
    ev.preventDefault();
    const pid = document.getElementById('snProjectId').value.trim();
    const reason = document.getElementById('snReason').value.trim();
    const url = document.getElementById('snUrl').value.trim();
    const dateVal = document.getElementById('snUntilDate').value;
    const dur = document.getElementById('snDuration').value;
    const err = document.getElementById('snError');
    const body = { reason, url };
    if (dateVal) body.until = dateVal;
    else body.duration = dur;
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(pid) + '/hold', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const j = await r.json().catch(() => ({}));
        err.textContent = j.detail || ('Error ' + r.status);
        err.classList.add('on');
        return;
      }
      closeSnoozeModal();
      // Refresh whichever home panel we're on so the card moves, and the
      // project attrs bar (if we're inside a project) so the snooze chip
      // reflects the new state.
      renderHomePanel();
      if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
    } catch (e) {
      err.textContent = e.message;
      err.classList.add('on');
    }
  }

  async function clearProjectHold(pid) {
    if (!pid) return;
    try {
      const r = await fetch('/api/projects/' + encodeURIComponent(pid) + '/hold', {method: 'DELETE'});
      if (!r.ok) return;
      renderHomePanel();
      if (typeof refreshAttrsBar === 'function') refreshAttrsBar();
    } catch {}
  }

  // Open the "New project" modal from the dashboard button. Kept separate
  // from submitNewProject/closeNewProjectModal so other callers (e.g. a
  // future "+ project" tab) can reuse.
  function onHomeNewProject() { openNewProjectModal(); }

  function openNewProjectModal() {
    const overlay = document.getElementById('newProjectModal');
    if (!overlay) return;
    // Reset the form every open so stale fields from a cancelled attempt
    // don't resurface.
    ['npId','npDesc','npDue','npTags','npLabels'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const pri = document.getElementById('npPriority');
    if (pri) pri.value = 'P2';
    const err = document.getElementById('npError');
    if (err) { err.textContent = ''; err.classList.remove('on'); }
    // Reset the submit button too: a successful create leaves it disabled
    // saying "Creating…" (only the failure path restored it), so every
    // subsequent open showed a permanently-loading button.
    const submit = document.getElementById('npSubmit');
    if (submit) { submit.disabled = false; submit.textContent = 'Create'; }
    overlay.classList.add('active');
    setTimeout(() => { document.getElementById('npId')?.focus(); }, 30);
    document.addEventListener('keydown', _newProjectEscHandler);
    _calInit();
    _npPopulateWorkspaces();
  }

  // Populate the "Workspace" select with every registered workspace,
  // defaulting to the one currently active. Stores each option's resolved
  // root path in a data attribute so submitNewProject can build the
  // `?project=` deep link after switching + creating in a non-active one.
  async function _npPopulateWorkspaces() {
    const sel = document.getElementById('npWorkspace');
    if (!sel) return;
    try {
      const r = await fetch('/api/workspaces');
      if (!r.ok) return;
      const data = await r.json();
      const rows = Array.isArray(data.workspaces) ? data.workspaces : [];
      sel.innerHTML = '';
      rows.forEach(row => {
        const opt = document.createElement('option');
        opt.value = row.id;
        opt.textContent = row.name || row.id;
        opt.dataset.path = row.path || '';
        opt.disabled = row.exists === false;
        opt.selected = row.active === true || row.id === data.active;
        sel.appendChild(opt);
      });
    } catch {}
  }

  // ─── Due-date calendar (inline, no native popup) ───
  let _calViewYear = new Date().getFullYear();
  let _calViewMonth = new Date().getMonth();  // 0-11
  let _calSelectedIso = '';  // "YYYY-MM-DD" or ''

  function _calInit() {
    const now = new Date();
    _calViewYear = now.getFullYear();
    _calViewMonth = now.getMonth();
    _calSelectedIso = '';
    _calRender();
    // Wire nav + quick-pick buttons once (guard with a marker so we don't
    // stack duplicate listeners on every re-open).
    const cal = document.getElementById('npCal');
    if (cal && !cal._wired) {
      document.getElementById('npCalPrev').addEventListener('click', () => _calShift(-1));
      document.getElementById('npCalNext').addEventListener('click', () => _calShift(1));
      cal.querySelectorAll('.cal-quick button').forEach(btn => {
        btn.addEventListener('click', () => {
          if (btn.dataset.clear) { _calSetDate(''); return; }
          const n = parseInt(btn.dataset.offset || '0', 10);
          const d = new Date();
          d.setDate(d.getDate() + n);
          _calSetDate(_calIso(d));
          // Jump the view to whatever month the quick-pick landed in.
          _calViewYear = d.getFullYear();
          _calViewMonth = d.getMonth();
          _calRender();
        });
      });
      cal._wired = true;
    }
  }

  function _calShift(delta) {
    _calViewMonth += delta;
    while (_calViewMonth < 0) { _calViewMonth += 12; _calViewYear--; }
    while (_calViewMonth > 11) { _calViewMonth -= 12; _calViewYear++; }
    _calRender();
  }

  function _calIso(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  }

  function _calSetDate(iso) {
    _calSelectedIso = iso || '';
    const hidden = document.getElementById('npDue');
    if (hidden) hidden.value = _calSelectedIso;
    const sel = document.getElementById('npCalSelected');
    if (sel) {
      if (_calSelectedIso) {
        sel.textContent = 'selected: ' + _calSelectedIso;
        sel.classList.add('set');
      } else {
        sel.textContent = 'no date';
        sel.classList.remove('set');
      }
    }
    _calRender();
  }

  function _calRender() {
    const label = document.getElementById('npCalLabel');
    const grid = document.getElementById('npCalGrid');
    if (!label || !grid) return;
    const months = ['January','February','March','April','May','June',
                    'July','August','September','October','November','December'];
    label.textContent = `${months[_calViewMonth]} ${_calViewYear}`;

    const firstOfMonth = new Date(_calViewYear, _calViewMonth, 1);
    const startDow = firstOfMonth.getDay();             // 0=Sun
    const daysInMonth = new Date(_calViewYear, _calViewMonth + 1, 0).getDate();
    const todayIso = _calIso(new Date());

    // Render 6 rows × 7 cols = 42 cells starting from the Sunday before
    // (or on) the 1st of the month.
    const start = new Date(_calViewYear, _calViewMonth, 1 - startDow);
    const cells = [];
    for (let i = 0; i < 42; i++) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      const iso = _calIso(d);
      const outOfMonth = d.getMonth() !== _calViewMonth;
      const classes = ['cal-day'];
      if (outOfMonth) classes.push('out');
      if (iso === todayIso) classes.push('today');
      if (iso === _calSelectedIso) classes.push('selected');
      cells.push(`<button type="button" class="${classes.join(' ')}" data-iso="${iso}">${d.getDate()}</button>`);
    }
    grid.innerHTML = cells.join('');
    grid.querySelectorAll('.cal-day').forEach(btn => {
      btn.addEventListener('click', () => _calSetDate(btn.dataset.iso));
    });
  }

  function closeNewProjectModal() {
    const overlay = document.getElementById('newProjectModal');
    if (overlay) overlay.classList.remove('active');
    document.removeEventListener('keydown', _newProjectEscHandler);
  }

  function _newProjectEscHandler(e) {
    if (e.key === 'Escape') closeNewProjectModal();
  }

  async function submitNewProject(event) {
    event.preventDefault();
    const id = (document.getElementById('npId').value || '').trim();
    const description = (document.getElementById('npDesc').value || '').trim();
    const priority = document.getElementById('npPriority').value || null;
    const due = document.getElementById('npDue').value || null;  // <input type="date"> → YYYY-MM-DD
    const tags = (document.getElementById('npTags').value || '')
                   .split(',').map(s => s.trim()).filter(Boolean);
    const labels = (document.getElementById('npLabels').value || '')
                   .split(',').map(s => s.trim()).filter(Boolean);
    const errEl = document.getElementById('npError');
    const submitBtn = document.getElementById('npSubmit');

    if (!id) {
      errEl.textContent = 'Project ID is required.';
      errEl.classList.add('on');
      return;
    }

    // The create endpoint always writes into whichever workspace the
    // server is currently serving — there's no per-request workspace
    // param — so creating in a non-active one means switching first.
    const wsSel = document.getElementById('npWorkspace');
    const wsOpt = wsSel && wsSel.selectedOptions && wsSel.selectedOptions[0];
    const targetWsId = wsOpt ? wsOpt.value : '';
    const targetWsPath = wsOpt ? (wsOpt.dataset.path || '') : '';
    const switchingWorkspace = !!targetWsId && targetWsId !== currentWorkspaceId;

    submitBtn.disabled = true;
    submitBtn.textContent = 'Creating…';
    try {
      if (switchingWorkspace) {
        const swRes = await fetch('/api/workspaces/use', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({id: targetWsId}),
        });
        if (!swRes.ok) {
          const j = await swRes.json().catch(() => ({}));
          throw new Error(j.detail || swRes.statusText);
        }
        currentWorkspaceId = targetWsId;
      }
      const res = await fetch('/api/projects', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ id, description, priority, due, tags, labels }),
      });
      if (!res.ok) {
        const j = await res.json().catch(() => ({}));
        throw new Error(j.detail || res.statusText);
      }
      const p = await res.json();
      closeNewProjectModal();
      if (switchingWorkspace) {
        // Workspace just changed under us — the whole served index/tab
        // state is different now, so land via a full reload instead of
        // in-page nav (same as opening an other-workspace dashboard row).
        const wsPath = targetWsPath.replace(/\/+$/, '');
        location.href = '/?project=' + encodeURIComponent(wsPath + '/projects/' + p.id);
        return;
      }
      // Refresh repos so the just-created project's path is in projectsList,
      // then in-page nav. goToProjectById falls back to /p/<id> if missing.
      try { projectsList = await fetchRepos(); } catch {}
      goToProjectById(p.id);
    } catch (e) {
      errEl.textContent = 'Failed: ' + e.message;
      errEl.classList.add('on');
      submitBtn.disabled = false;
      submitBtn.textContent = 'Create';
    }
  }

  async function renderTimeline(el) {
    const idx = await fetch('/api/index').then(r => r.json());
    el.innerHTML = `
      <h2>Timeline</h2>
      <div class="view-toggle" style="margin-bottom:12px">
        <button class="pill ${homeTimelineMode === 'list' ? 'active' : ''}" id="tlList">List</button>
        <button class="pill ${homeTimelineMode === 'gantt' ? 'active' : ''}" id="tlGantt">Gantt</button>
      </div>
      <div id="tlBody"></div>
    `;
    el.querySelector('#tlList').addEventListener('click', () => { homeTimelineMode = 'list'; renderTimeline(el); });
    el.querySelector('#tlGantt').addEventListener('click', () => { homeTimelineMode = 'gantt'; renderTimeline(el); });
    el.querySelector('#tlBody').innerHTML = homeTimelineMode === 'list' ? timelineListHtml(idx) : timelineGanttHtml(idx);
  }

  function timelineListHtml(idx) {
    const tasks = (idx.tasks || []).filter(t => t.status !== 'done').slice();
    tasks.sort((a, b) => {
      if (a.due && b.due) return a.due.localeCompare(b.due);
      if (a.due) return -1;
      if (b.due) return 1;
      return 0;
    });
    const today = new Date().toISOString().slice(0, 10);
    const inDays = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
    const buckets = { 'Overdue': [], 'Today / this week': [], 'Next week': [], 'This month': [], 'Later': [], 'No due date': [] };
    const thisWeek = inDays(7), nextWeek = inDays(14), thisMonth = inDays(30);
    for (const t of tasks) {
      if (!t.due) { buckets['No due date'].push(t); continue; }
      if (t.due < today) { buckets['Overdue'].push(t); continue; }
      if (t.due <= thisWeek) { buckets['Today / this week'].push(t); continue; }
      if (t.due <= nextWeek) { buckets['Next week'].push(t); continue; }
      if (t.due <= thisMonth) { buckets['This month'].push(t); continue; }
      buckets['Later'].push(t);
    }
    return Object.entries(buckets)
      .filter(([, rows]) => rows.length > 0)
      .map(([name, rows]) => `
        <div class="bucket">
          <h3>${escapeHtml(name)} (${rows.length})</h3>
          <table>
            <thead><tr><th>Due</th><th>P</th><th>Project</th><th>Title</th></tr></thead>
            <tbody>
              ${rows.map(t => `
                <tr>
                  <td>${fmtDate(t.due)}</td>
                  <td><span class="chip ${priorityClass(t.priority)}">${escapeHtml(t.priority || '')}</span></td>
                  <td><a href="/p/${encodeURIComponent(t.project_id)}">${escapeHtml(t.project_id)}</a></td>
                  <td>${escapeHtml(t.title)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>`).join('') || '<p>No open tasks.</p>';
  }

  function timelineGanttHtml(idx) {
    const projects = (idx.projects || []).filter(p => p.status === 'active');
    if (!projects.length) return '<p>No active projects.</p>';
    const today = new Date();
    const minD = projects.reduce((m, p) => {
      const d = p.created ? new Date(p.created) : today;
      return d < m ? d : m;
    }, today);
    const maxD = projects.reduce((m, p) => {
      const candidate = p.due ? new Date(p.due) : (p.earliest_task_due ? new Date(p.earliest_task_due) : today);
      return candidate > m ? candidate : m;
    }, new Date(today.getTime() + 14 * 86400000));
    const spanMs = Math.max(maxD - minD, 86400000);
    const pct = (d) => ((new Date(d) - minD) / spanMs) * 100;
    const rows = projects.map(p => {
      const startD = p.created || today.toISOString().slice(0, 10);
      const endD = p.due || p.earliest_task_due || new Date(today.getTime() + 7 * 86400000).toISOString().slice(0, 10);
      const left = Math.max(0, pct(startD));
      const width = Math.max(1, pct(endD) - left);
      const cls = priorityClass(p.priority) + (p.status === 'archived' ? ' archived' : '');
      return `
        <div class="gantt-row">
          <div class="gantt-label"><a href="/p/${encodeURIComponent(p.id)}">${escapeHtml(p.id)}</a></div>
          <div class="gantt-lane">
            <div class="gantt-bar ${cls}" style="left:${left}%; width:${width}%" title="${startD} → ${endD}"></div>
          </div>
        </div>`;
    }).join('');
    return `<div class="gantt">${rows}<p style="color:var(--text-secondary); font-size:12px; margin-top:10px">${fmtDate(minD.toISOString())} → ${fmtDate(maxD.toISOString())}</p></div>`;
  }

  function renderSearch(el) {
    // Use cached query + results so switching tabs doesn't lose state.
    el.innerHTML = `
      <h2>Search</h2>
      <input type="text" class="search-input" id="searchInput"
             placeholder="Search projects, tasks, and docs…"
             value="${escapeHtml(homeSearchQuery)}" />
      <p class="search-status" id="searchStatus">${homeSearchQuery ? '' : 'Type a query and press Enter.'}</p>
      <div id="searchResults"></div>
    `;
    const input = el.querySelector('#searchInput');
    input.focus();
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') runHomeSearch(input.value);
    });
    if (homeSearchResults) renderHomeSearchResults(homeSearchResults);
  }

  async function runHomeSearch(q) {
    homeSearchQuery = q;
    if (!q) return;
    const status = document.getElementById('searchStatus');
    if (status) status.textContent = 'searching…';
    try {
      const r = await fetch('/api/search?q=' + encodeURIComponent(q)).then(r => r.json());
      homeSearchResults = r;
      renderHomeSearchResults(r);
    } catch (e) {
      if (status) status.textContent = 'Error: ' + e.message;
    }
  }

  function renderHomeSearchResults(r) {
    const results = document.getElementById('searchResults');
    const status = document.getElementById('searchStatus');
    if (!results) return;
    const total = (r.projects?.length || 0) + (r.tasks?.length || 0) + (r.docs?.length || 0);
    if (status) status.textContent = `${total} result${total === 1 ? '' : 's'} for "${r.query}"`;
    const sections = [];
    if (r.projects?.length) {
      sections.push(`<section class="search-section"><h3>Projects (${r.projects.length})</h3><ul>${
        r.projects.map(p => `<li><a href="/p/${encodeURIComponent(p.id)}">${escapeHtml(p.id)}</a><span class="meta">[${escapeHtml(p.status)}]</span>${p.description ? `<span class="meta">${escapeHtml(p.description.slice(0, 80))}</span>` : ''}</li>`).join('')
      }</ul></section>`);
    }
    if (r.tasks?.length) {
      sections.push(`<section class="search-section"><h3>Tasks (${r.tasks.length})</h3><ul>${
        r.tasks.map(t => `<li><a href="/p/${encodeURIComponent(t.project_id)}">${escapeHtml(t.project_id)}#${t.task_id}</a><span class="meta">[${escapeHtml(t.status)}] ${escapeHtml(t.priority || '')}</span><span class="meta">${escapeHtml(t.title)}</span></li>`).join('')
      }</ul></section>`);
    }
    if (r.docs?.length) {
      sections.push(`<section class="search-section"><h3>Docs (${r.docs.length})</h3><ul>${
        r.docs.map(d => `<li><a href="/view?path=${encodeURIComponent(d.path)}">${escapeHtml(d.path)}</a><div class="snippet">${escapeHtml(d.snippet || '')}</div></li>`).join('')
      }</ul></section>`);
    }
    results.innerHTML = sections.length ? sections.join('') : '<p>No matches.</p>';
  }

  // ─── Cerebro view (mdview-style sidebar + markdown pane) ───

  // ─── Productivity self-view (file tree sidebar + Lab framework workbench) ───

  async function initSelf() {
    document.body.classList.add('self-active');
    document.title = 'Productivity';
    // Set up a synthetic currentProject so openProjectDoc(), the sidebar, and
    // the terminal panel all work exactly like a real project tab.
    currentProject = {
      name: '__self__',
      path: SELF_REPO_PATH,
      is_project: true,
      repos: [],
    };
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
    const {scope, autoOpen, activePath} = opts;
    let html = '';
    treeFolderNames(node).forEach(folder => {
      const fid = 'sf-' + Math.random().toString(36).substr(2, 6);
      const fullPath = parentPath ? `${parentPath}/${folder}` : folder;
      const d = treeFolderEntry(node, folder, fullPath);
      const autoOpenHere = depth === 0 && autoOpen && autoOpen.has(folder);
      const open = _treeIsOpen(scope, fullPath, autoOpenHere);
      const arrowCls = open ? ' open' : '';
      const childrenCls = open ? ' open' : '';
      html += `<div class="sidebar-folder${symlinkClass(d)}" data-tree-scope="${escAttr(scope)}" data-tree-path="${escAttr(fullPath)}" data-tree-target="${fid}"${symlinkTitle(d)} onclick="_treeToggleFolder(this)"><span class="folder-arrow${arrowCls}">▶</span>${symlinkMarker(d)}${esc(folder)}/</div>`;
      html += `<div class="sidebar-folder-children${childrenCls}" id="${fid}">`;
      html += renderSidebarFileTree(node[folder], depth + 1, fullPath, opts);
      html += '</div>';
    });
    treeFiles(node).forEach(f => {
      const safePath = f.path.replace(/'/g, "\\'");
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
        dotHtml = `<span class="nb-unseen-dot" title="Click to jump to the first new cell" onclick="event.stopPropagation();openProjectDocAndJumpToUnseen('${safePath}')"></span>`;
      }
      html += `<a class="sidebar-file${activeCls}${symlinkClass(f)}" data-filepath="${esc(f.path)}"${symlinkTitle(f)} onclick="openProjectDoc('${safePath}')" ondblclick="event.stopPropagation();openProjectDocModal('${safePath}')"><span class="sidebar-fname">${dotHtml}${symlinkMarker(f)}${icon}${fname}</span></a>`;
    });
    return html;
  }

  // Populate #sidebar with a file tree rooted at SELF_REPO_PATH.
  // Mirrors the pattern used by showProjectInfo() for real projects.
  async function selfPopulateSidebar() {
    const sidebar = document.getElementById('sidebar');
    try {
      const res = await fetch(`/api/project-files?path=${encodeURIComponent(SELF_REPO_PATH)}&include_dotfiles=${showProjectDotFiles}`);
      const files = await res.json();

      // Bake .active onto the rendered HTML (data-filepath + class) so any
      // future sidebar rebuild — mtime poll, WS index-updated — keeps the
      // current file highlighted. Without this the active class is only
      // applied imperatively after rebuild and the selection flickers.
      const activePath = _projDocPath || null;
      const workbenchActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${workbenchActive}" data-workbench="1" onclick="selfShowWorkbench()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Workbench</span></a>`;
      sbHtml += '<div style="padding:4px 16px"><label style="font-size:11px;color:var(--text-secondary);cursor:pointer;user-select:none"><input type="checkbox" id="projectDotFiles" onchange="selfToggleDotFiles(this.checked)" ' + (showProjectDotFiles ? 'checked' : '') + ' style="margin-right:4px">Show hidden files</label></div>';
      sbHtml += symlinkLegendHtml();
      sbHtml += '<div class="sidebar-title">Files</div>';

      const tree = buildSidebarTree(files);

      sbHtml += renderSidebarFileTree(tree, 0, '', {scope: 'self', autoOpen: _AUTO_OPEN_SELF, activePath});

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
      sidebar.innerHTML = '<div class="sidebar-title">Productivity</div>';
    }
  }

  // Render the Productivity workbench scaffold into #content. The refresh
  // functions look for element IDs inside here.
  function selfPaintWorkbench() {
    _projDocPath = null;
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
          <div class="s-section" id="dashKpis"></div>
          <div class="s-section" id="dashServers">
            <h2>Servers <span class="count">…</span></h2>
            <div class="srv-empty">Loading servers…</div>
          </div>
          <div class="s-section" id="dashTerms">
            <h2>Terminals <span class="count">…</span></h2>
            <div class="term-empty">Loading terminal sessions…</div>
          </div>
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
    // Servers / Terminals cards share their ids + render/poll machinery
    // with the home dashboard (only the ACTIVE view's copy is ever
    // resolved — see dashSectionEl). Scope the queries to #content: a
    // hidden stale copy can linger in #homePanel after an in-page switch.
    // dashStartPolling clears any previous interval, and dashPollTick
    // self-cleans when the container leaves the active view, so
    // home ↔ productivity navigation never stacks intervals.
    content.querySelector('#dashServers').addEventListener('click', dashServersOnClick);
    content.querySelector('#dashTerms').addEventListener('click', dashTermsOnClick);
    if (!UI_CHECK) dashStartPolling();
    dashPollTick();
  }

  // Return to the workbench from a doc view.
  function selfShowWorkbench() {
    _projDocPath = null;
    document.querySelectorAll('#sidebar .sidebar-file').forEach(el => el.classList.remove('active'));
    selfPaintWorkbench();
    afterFirstPaint(() => selfRefreshWorkbench());
  }

  // Compatibility for older inline handlers or cached pages.
  function selfShowDashboard() { return selfShowWorkbench(); }

  // Toggle hidden-files visibility for the productivity sidebar.
  // Mirrors toggleProjectDotFiles() but re-renders via selfPopulateSidebar()
  // instead of showProjectInfo().
  function selfToggleDotFiles(checked) {
    showProjectDotFiles = checked;
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
      termStartStatusPolling();
      return;
    }
    await _termRestoreSessionsForProject(SELF_PROJECT_ID);
    // Same live-status polling as real projects: pills pulse, attention flag fires.
    termStartPeriodicRefresh();
    termStartStatusPolling();
  }

  // ─── Workspace view (active-workspace management surface) ───
  // Always-pinned pseudo-tab, mirrors initSelf(): synthetic currentProject
  // rooted at the ACTIVE workspace root so openProjectDoc, the sidebar,
  // git decorations, and the mtime/WS live refreshes all behave like a
  // real project. Content always reflects the workspace selected in the
  // top-left dropdown; switching workspaces re-runs this init.

  async function initWorkspaceView() {
    // On a full page load the server's INITIAL_BODY_CLASS doesn't know
    // this view (main.py defaults unknown ?view= values to home-active),
    // and the initial `?view=…` dispatch calls us directly — without
    // _swapViewState. Strip the stale view classes ourselves so the home
    // shell can't sit under (or fight) the workspace layout.
    document.body.classList.remove(
      'home-active', 'cerebro-active', 'self-active', 'project-active',
      'code-search-active', 'logs-active',
    );
    document.body.classList.add('workspace-active');
    document.title = 'Workspace';
    // No terminal panel in this view for now — the server has no cwd
    // mapping for a workspace pseudo-project (term.py would resolve
    // `__workspace__` to projects/__workspace__, which doesn't exist).
    // Hide any panel carried over from the previous view by dropping the
    // body classes only: _swapViewState already soft-parked the active
    // session, and the terminal poll loops self-clean on their next tick
    // once `term-open` is gone. (Deliberately NOT termClose() here — this
    // runs during the initial `?view=…` dispatch, before the terminal
    // state block is evaluated, so touching its lets would hit the TDZ.)
    document.body.classList.remove('term-open');
    document.body.classList.remove('term-collapsed');
    const dt = document.getElementById('diffTabs');
    if (dt) dt.style.display = 'none';
    document.body.classList.remove('has-diff-tabs');
    // Re-render the tab strip so the workspace tab flips to `.active`
    // immediately (same first-load caveat as initSelf: projTabsRefresh
    // repaints with the full list once it returns).
    if (typeof projTabsRender === 'function') projTabsRender();
    _projDocPath = null;

    // Scaffold synchronously; the fetch below fills in the real content.
    const content = document.getElementById('content');
    if (content) content.innerHTML = '<div class="s-inner ws-overview"><div class="loading">Loading workspace…</div></div>';

    let data = null;
    try {
      const r = await fetch('/api/workspaces');
      if (r.ok) data = await r.json();
    } catch {}
    // The user may have navigated away while the fetch was in flight.
    if (!document.body.classList.contains('workspace-active')) return;
    const current = (data && data.current) || null;
    _workspaceCurrent = current;
    if (!current || !current.path) {
      if (content) content.innerHTML = '<div class="s-inner ws-overview"><div class="loading">Could not load the active workspace.</div></div>';
      return;
    }
    if (data.active) currentWorkspaceId = data.active;
    document.title = 'Workspace — ' + (current.name || current.id);
    // Synthetic project rooted at the workspace root (same trick as the
    // self view) so the doc pane, sidebar, and pollers treat it like a
    // real project.
    currentProject = {
      name: WORKSPACE_PROJECT_ID,
      path: current.path,
      is_project: true,
      repos: [],
    };
    _sidebarApplyForView();
    workspacePaintOverview(current);
    afterPageQuiet(() => {
      workspacePopulateSidebar();
      workspaceRefreshCards();
    });
  }

  // Overview scaffold: header (name + id badge + active pill + path) and
  // the three cards. Reuses the productivity workbench's .s-inner /
  // .s-workbench-grid / .s-section card classes so it reads like the
  // existing dashboards. workspaceRefreshCards() fills the card bodies.
  function workspacePaintOverview(current) {
    _projDocPath = null;
    const content = document.getElementById('content');
    if (!content) return;
    content.innerHTML = `
      <div class="s-inner ws-overview">
        <div class="s-head ws-ov-head">
          <h1>${selfEsc(current.name || current.id)}
            <span class="ws-badge" title="workspace id">${selfEsc(current.id)}</span>
            <span class="ws-active-pill">active</span></h1>
        </div>
        <div class="ws-ov-path" title="${escAttr(current.path)}">${selfEsc(current.path)}</div>
        <div class="s-workbench-grid ws-ov-grid">
          <div class="s-section" id="wsConfigCard">
            <h2>Configuration</h2>
            <div class="ws-card-body" id="wsConfigBody"><div class="ws-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="wsAgentsCard">
            <h2>Agents</h2>
            <div class="ws-card-body" id="wsAgentsBody"><div class="ws-muted">Loading…</div></div>
          </div>
          <div class="s-section" id="wsProjectsCard">
            <h2>Projects <span class="count" id="wsProjectsCount"></span></h2>
            <ul class="ws-proj-list" id="wsProjectsList"><li class="s-empty">Loading…</li></ul>
          </div>
        </div>
      </div>`;
  }

  // Return to the overview from a doc view (sidebar "Overview" link).
  function workspaceShowOverview() {
    _projDocPath = null;
    document.querySelectorAll('#sidebar .sidebar-file').forEach(el => el.classList.remove('active'));
    if (_workspaceCurrent && currentProject && currentProject.name === WORKSPACE_PROJECT_ID) {
      workspacePaintOverview(_workspaceCurrent);
      afterFirstPaint(() => workspaceRefreshCards());
    } else {
      initWorkspaceView();
    }
  }

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
      const r = await fetch('/api/workspace/config');
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
      '4. Verify when done: ' + location.origin + '/api/workspace/config must show',
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
      const r = await fetch('/api/workspace/config/init', { method: 'POST' });
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

  // "Agents" card: read-only display of the default agent and per-agent
  // autopilot state from /api/settings. Editing happens in Settings.
  async function workspaceRenderAgentsCard() {
    const body = document.getElementById('wsAgentsBody');
    if (!body) return;
    let s = _settings;
    try {
      const r = await fetch('/api/settings');
      if (r.ok) { s = await r.json(); _settings = s; }
    } catch {}
    if (!body.isConnected) return;
    const autopilot = s.autopilot || {};
    const flags = s.autopilotFlags || {};
    const defaultAgent = s.defaultAgent || 'claude';
    const rows = Object.keys(AGENT_LABELS).map(a => {
      const on = !!autopilot[a];
      const flag = on && flags[a] ? ` (${flags[a]})` : '';
      return `<div class="ws-agent-row">
        <span class="ws-agent-name">${selfEsc(AGENT_LABELS[a])}</span>
        ${a === defaultAgent ? '<span class="ws-agent-default">default</span>' : ''}
        <span class="ws-agent-auto${on ? ' on' : ''}">autopilot ${on ? 'on' : 'off'}${selfEsc(flag)}</span>
      </div>`;
    });
    rows.push('<div class="ws-card-actions"><button class="refresh-btn" onclick="openSettings()">Edit in Settings</button></div>');
    body.innerHTML = rows.join('');
  }

  // "Projects" card: the ACTIVE workspace's project ids from
  // /api/workspaces/projects. Rows open the project the same way Home's
  // active-workspace rows do (goToProjectById → in-page nav).
  async function workspaceRenderProjectsCard() {
    const list = document.getElementById('wsProjectsList');
    const count = document.getElementById('wsProjectsCount');
    if (!list) return;
    let data = null;
    try {
      const r = await fetch('/api/workspaces/projects');
      if (r.ok) data = await r.json();
    } catch {}
    if (!list.isConnected) return;
    const ws = ((data && data.workspaces) || []).find(w => w.active) || null;
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
    const ids = ws.projects || [];
    if (count) count.textContent = ids.length ? String(ids.length) : '';
    if (!ids.length) {
      list.innerHTML = '<li class="s-empty">No projects yet.</li>';
      return;
    }
    list.innerHTML = ids.map(pid => `
      <li class="ws-proj-row" data-pid="${escAttr(pid)}" role="button" tabindex="0" title="Open ${escAttr(pid)}">
        <span class="ws-proj-name">${selfEsc(pid)}</span>
        <span class="p-caret">›</span>
      </li>`).join('');
    list.querySelectorAll('.ws-proj-row').forEach(row => {
      row.addEventListener('click', () => goToProjectById(row.getAttribute('data-pid')));
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
      const res = await fetch(`/api/project-files?path=${encodeURIComponent(rootPath)}&include_dotfiles=${showProjectDotFiles}`);
      const files = await res.json();
      if (!document.body.classList.contains('workspace-active')) return;
      if (!currentProject || currentProject.path !== rootPath) return;

      const activePath = _projDocPath || null;
      const overviewActive = !activePath ? ' active' : '';
      let sbHtml = `<a class="sidebar-file${overviewActive}" data-ws-overview="1" onclick="workspaceShowOverview()" style="font-weight:600;padding:8px 16px;font-size:13px"><span class="sidebar-fname">Overview</span></a>`;
      sbHtml += '<div style="padding:4px 16px"><label style="font-size:11px;color:var(--text-secondary);cursor:pointer;user-select:none"><input type="checkbox" id="projectDotFiles" onchange="workspaceToggleDotFiles(this.checked)" ' + (showProjectDotFiles ? 'checked' : '') + ' style="margin-right:4px">Show hidden files</label></div>';
      sbHtml += symlinkLegendHtml();
      sbHtml += '<div class="sidebar-title">Files</div>';
      sbHtml += renderSidebarFileTree(buildSidebarTree(files), 0, '', {scope: 'workspace', autoOpen: _AUTO_OPEN_WORKSPACE, activePath});
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

  // Terminal panel for the Logs pseudo-project: sessions rooted at logs/.
  async function termOpenForLogs() {
    if (!_termIsScopeActive(LOGS_PROJECT_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(LOGS_PROJECT_ID)) {
      termStartPeriodicRefresh();
      termStartStatusPolling();
      return;
    }
    await _termRestoreSessionsForProject(LOGS_PROJECT_ID);
    termStartPeriodicRefresh();
    termStartStatusPolling();
  }

  // Terminal panel for the Knowledge pseudo-project: claude session rooted at knowledge/.
  async function termOpenForCerebro() {
    // Mirror termOpenForProject, but wired to the __cerebro__ pseudo-project.
    if (!_termIsScopeActive(CEREBRO_PROJECT_ID)) return;
    document.body.classList.add('term-open');
    _termApplyRememberedVisibility();
    if (await _termTryWarmOpen(CEREBRO_PROJECT_ID)) {
      termStartPeriodicRefresh();
      termStartStatusPolling();
      return;
    }
    await _termRestoreSessionsForProject(CEREBRO_PROJECT_ID);
    // Cerebro's terminal panel gets the same live-status polling as real
    // projects — pills pulse + the cerebro tab flags attention if idle.
    termStartPeriodicRefresh();
    termStartStatusPolling();
  }

  async function termRefreshSessionsByProjectId(pid) {
    // Fetches the live session list and re-renders the pill row.
    let fresh = [];
    let ok = false;
    try {
      const r = await fetch('/api/term/sessions?project_id=' + encodeURIComponent(pid));
      ok = r.ok;
      fresh = r.ok ? await r.json() : [];
    } catch { fresh = []; ok = false; }
    if (ok) _termSessionsCache.set(pid, fresh);
    // Stale-response guard — see termRefreshSessions for why.
    if (pid !== _termActiveProjectId()) return ok;
    // Failed fetch → keep the last-known list (see termRefreshSessions).
    termSessions = ok ? fresh : (_termSessionsCache.get(pid) || []);
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
    const MAX_DELAY = 30000;
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${proto}//${location.host}/ws`);
      ws.onopen = () => { delay = 1000; try { ws.send('hello'); } catch {} };
      ws.onmessage = (ev) => {
        try {
          const event = JSON.parse(ev.data);
          if (event.type !== 'index-updated') return;
          if (event.ts && event.ts === lastTs) return;
          lastTs = event.ts;
          if (document.body.classList.contains('home-active')) {
            renderHomePanel();
          } else if (document.body.classList.contains('self-active')
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
            if (_projDocPath) openProjectDoc(_projDocPath, {preserveScroll: true});
            else if (!document.body.classList.contains('self-active')) showProjectInfo({preserveScroll: true});
          }
        } catch {}
      };
      ws.onclose = () => { setTimeout(connect, delay); delay = Math.min(delay * 2, MAX_DELAY); };
      ws.onerror = () => { try { ws.close(); } catch {} };
    };
    connect();
  }
  if (!UI_CHECK) subscribeLiveWS();
