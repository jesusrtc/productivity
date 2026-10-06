/* A new workspace terminal chooses its launch folder once. */
(() => {
  const esc = value => String(value || '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let cancel = null;

  function choices(base, label, config, configScope, objective) {
    const paths = [...new Set([base, ...(config.pinnedScopes || [])])];
    const rows = paths.map(path => {
      const row = (config.folderScopes || []).find(row => row.path === path);
      const worktree = row?.kind === 'worktree';
      const name = path === base ? label : row?.label || path.split('/').pop() || path;
      return {name, kind: path === base ? 'Workspace' : worktree ? 'Worktree' : 'Folder', scope: {
        base_root: base, project_root: worktree ? row.projectPath || path : path,
        root: path, worktree: worktree ? path : null, label: name,
        color: row?.color || config.worktreeColors?.[path] || config.rootScopeColors?.[base] || '#6e7681',
        config_scope: configScope,
      }};
    });
    if (!objective) return rows;
    const association = {context: objective.context, objective_id: objective.id};
    const scope = (path, name, color, repo = base, worktree = null) => ({
      base_root: base, project_root: repo, root: path, worktree, label: name,
      color: color || '#8b949e', config_scope: configScope,
    });
    const worktrees = objective.worktrees.map(tree => ({
      name: tree.label || tree.path.split('/').pop(), kind: tree.kind === 'worktree' ? 'Worktree' : 'Folder',
      scope: scope(tree.path, tree.label, tree.color, tree.repo || tree.path,
        tree.kind === 'worktree' ? tree.path : null),
      association: {...association, folder: {root: tree.path, path: '.'}},
    }));
    return [
      ...(objective.task?[{name:'Current task (recommended)',description:objective.task.title,kind:'Task',
        scope:scope(objective.path,objective.name),association:{...association,task_id:objective.task.id,rename_to_task:true}}]:[]),
      {...rows[0], name: 'Current workflow', description: label, kind: 'Workflow'},
      {name: 'Current Objective', description: objective.name, kind: 'Objective',
        scope: scope(objective.path, objective.name), association},
      {name: 'Specific worktree', description: 'Choose a worktree in ' + objective.name,
        kind: 'Worktree', children: worktrees},
    ];
  }

  function choose(rows, current, {selection = false} = {}) {
    cancel?.();
    if (!current()) return Promise.resolve(null);
    return new Promise(resolve => {
      const previous = document.activeElement;
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay active term-folder-overlay';
      overlay.innerHTML = `<div class="form-modal term-folder-modal" role="dialog" aria-modal="true" aria-labelledby="termFolderTitle" aria-describedby="termFolderHint">
        <div class="fm-header"><span class="fm-title" id="termFolderTitle">Where should this terminal start?</span><button type="button" class="fm-close" data-cancel aria-label="Cancel">×</button></div>
        <p id="termFolderHint">Choose a folder for this new terminal. Its folder stays fixed after it opens.</p>
        <div class="term-folder-list"></div>
        <div class="term-folder-footer"><button type="button" data-cancel>Cancel</button></div>
      </div>`;
      let timer, finished = false;
      const finish = choice => {
        if (finished) return;
        finished = true;
        clearInterval(timer);
        document.removeEventListener('keydown', keydown, true);
        overlay.remove();
        if (cancel === dismiss) cancel = null;
        if (current() && previous?.isConnected) previous.focus({preventScroll:true});
        resolve(selection ? choice : choice?.scope || null);
      };
      const dismiss = () => finish(null);
      const keydown = event => {
        if (event.key === 'Escape') {
          event.preventDefault(); event.stopImmediatePropagation(); dismiss();
        } else if (event.key === 'Tab') {
          const buttons = [...overlay.querySelectorAll('button:not(:disabled)')];
          const index = buttons.indexOf(document.activeElement);
          event.preventDefault(); event.stopImmediatePropagation();
          buttons[(index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus();
        }
      };
      cancel = dismiss;
      let visibleRows = rows;
      const render = (entries, parent = null) => {
        visibleRows = entries;
        overlay.querySelector('.term-folder-list').innerHTML = (parent
          ? `<button type="button" class="term-folder-back" data-folder-back>← All launch options</button><h3>${esc(parent.description)}</h3>` : '')
          + entries.map((row, i) => `<button type="button" class="term-folder-choice" data-folder-choice="${i}" ${row.children?.length === 0 ? 'disabled' : ''} style="--folder-color:${esc(row.scope?.color || '#8b949e')}"><span><strong>${esc(row.name)}</strong>${row.description ? `<small>${esc(row.description)}</small>` : ''}<small>${esc(row.scope?.root || (row.children?.length ? row.children.length + ' available' : 'No worktrees associated yet'))}</small></span><span class="term-folder-kind">${esc(row.kind)}${row.children ? ' ›' : ''}</span></button>`).join('');
      };
      overlay.addEventListener('click', event => {
        if (event.target === overlay || event.target.closest('[data-cancel]')) return dismiss();
        if (event.target.closest('[data-folder-back]')) {
          render(rows);overlay.querySelector(`[data-folder-choice="${rows.findIndex(row=>row.children)}"]`)?.focus({preventScroll:true});return;
        }
        const button = event.target.closest('[data-folder-choice]');
        if (!button || button.disabled) return;
        if (!current()) return dismiss();
        const row = visibleRows[Number(button.dataset.folderChoice)];
        if (row?.children) {
          render(row.children, row);overlay.querySelector('[data-folder-choice]')?.focus({preventScroll:true});
        } else finish(row || null);
      });
      render(rows);
      document.body.appendChild(overlay);
      document.addEventListener('keydown', keydown, true);
      // Navigation cancels the captured request, including when no choice is clicked.
      timer = setInterval(() => { if (!current()) dismiss(); }, 150);
      overlay.querySelector('[data-folder-choice]')?.focus({preventScroll:true});
    });
  }

  window.LabTerminalFolder = {choices, choose};
})();
