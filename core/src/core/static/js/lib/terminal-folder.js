/* A new workspace terminal chooses its launch folder once. */
(() => {
  const esc = value => String(value || '').replace(/[&<>"']/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let cancel = null;

  function choices(base, label, config, configScope) {
    const paths = [...new Set([base, ...(config.pinnedScopes || [])])];
    return paths.map(path => {
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
  }

  function choose(rows, current) {
    cancel?.();
    if (!current()) return Promise.resolve(null);
    return new Promise(resolve => {
      const previous = document.activeElement;
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay active term-folder-overlay';
      overlay.innerHTML = `<div class="form-modal term-folder-modal" role="dialog" aria-modal="true" aria-labelledby="termFolderTitle" aria-describedby="termFolderHint">
        <div class="fm-header"><span class="fm-title" id="termFolderTitle">Where should this terminal start?</span><button type="button" class="fm-close" data-cancel aria-label="Cancel">×</button></div>
        <p id="termFolderHint">Choose a folder for this new terminal. Its folder stays fixed after it opens.</p>
        <div class="term-folder-list">${rows.map((row, i) => `<button type="button" class="term-folder-choice" data-folder-choice="${i}" style="--folder-color:${esc(row.scope.color)}"><span><strong>${esc(row.name)}</strong><small>${esc(row.scope.root)}</small></span><span class="term-folder-kind">${esc(row.kind)}</span></button>`).join('')}</div>
        <div class="term-folder-footer"><button type="button" data-cancel>Cancel</button></div>
      </div>`;
      let timer, finished = false;
      const finish = scope => {
        if (finished) return;
        finished = true;
        clearInterval(timer);
        document.removeEventListener('keydown', keydown, true);
        overlay.remove();
        if (cancel === dismiss) cancel = null;
        if (current() && previous?.isConnected) previous.focus({preventScroll:true});
        resolve(scope);
      };
      const dismiss = () => finish(null);
      const keydown = event => {
        if (event.key === 'Escape') {
          event.preventDefault(); event.stopImmediatePropagation(); dismiss();
        } else if (event.key === 'Tab') {
          const buttons = [...overlay.querySelectorAll('button')];
          const index = buttons.indexOf(document.activeElement);
          event.preventDefault(); event.stopImmediatePropagation();
          buttons[(index + (event.shiftKey ? -1 : 1) + buttons.length) % buttons.length].focus();
        }
      };
      cancel = dismiss;
      overlay.addEventListener('click', event => {
        if (event.target === overlay || event.target.closest('[data-cancel]')) return dismiss();
        const button = event.target.closest('[data-folder-choice]');
        if (button) finish(current() ? rows[Number(button.dataset.folderChoice)]?.scope || null : null);
      });
      document.body.appendChild(overlay);
      document.addEventListener('keydown', keydown, true);
      // Navigation cancels the captured request, including when no choice is clicked.
      timer = setInterval(() => { if (!current()) dismiss(); }, 150);
      overlay.querySelector('[data-folder-choice]')?.focus({preventScroll:true});
    });
  }

  window.LabTerminalFolder = {choices, choose};
})();
