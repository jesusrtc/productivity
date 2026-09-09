/* One-time migration of Lab-owned browser preferences. User paths and text stay intact. */
(function migrateLabNaming() {
  const marker = 'labVaultNaming-v2';
  if (typeof location !== 'undefined' && /^#\/p\//.test(location.hash)) {
    history.replaceState(null, '', location.pathname + location.search + location.hash.replace(/^#\/p\//, '#/w/'));
  }
  function scope(key) {
    return key.replace(/^workspace(?=:|$)/, 'vault').replace(/^project(?=:|$)/, 'workspace')
      .replace(/(^|::)__workspace__(?=::|$)/g, '$1__vault__');
  }
  function remapKeys(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [scope(key), item]));
  }
  try {
    if (localStorage.getItem(marker) !== '1') {
      const copies = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (!key) continue;
        let target = key;
        if (key === 'labOpenWorkspaces-v1') target = 'labOpenVaults-v1';
        if (key === 'projDocCommentsCollapsed') target = 'workspaceDocCommentsCollapsed';
        for (const prefix of ['labTermShown:', 'labSidebarShown:', 'labSidebarPct:', 'labTermNewOptions-v1:']) {
          if (key.startsWith(prefix)) target = prefix + scope(key.slice(prefix.length));
        }
        if (target !== key && localStorage.getItem(target) === null) copies.push([target, localStorage.getItem(key)]);
      }
      for (const [key, value] of copies) localStorage.setItem(key, value);
      for (const key of ['labTreeExpanded', 'labTermGroups-v1', 'labTermRecentActivity-v1', 'labTermLastSession']) {
        const raw = localStorage.getItem(key);
        if (!raw) continue;
        try { localStorage.setItem(key, JSON.stringify(remapKeys(JSON.parse(raw)))); } catch {}
      }
      localStorage.setItem(marker, '1');
    }
  } catch { /* Storage can be disabled; navigation must still work. */ }
})();
