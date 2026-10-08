/* The first column uses the terminal rail's deliberate-open behavior.
   Keep its live rows mounted: expanding overlays the work area rather than
   changing the document or terminal grid. */
(function () {
  'use strict';
  const sidebar = document.getElementById('sidebar');
  const resizer = document.getElementById('sidebarResizer');
  const toggle = document.getElementById('sidebarToggle');
  if (!sidebar || !resizer || !toggle) return;
  const surfaces = [sidebar, resizer, toggle];
  const desktop = matchMedia('(min-width: 761px)');
  const body = document.body;
  let adapter = null, scope = null, enabled = false;
  let hovered = false, enteredAt = 0, timer = null;
  const contains = target => target && surfaces.some(el => el === target || el.contains(target));
  const clearTimer = () => { clearTimeout(timer); timer = null; };
  const isOpen = () => body.classList.contains('sidebar-drawer-open');
  const pinned = () => body.classList.contains('sidebar-drawer-pinned');
  function setOpen(open) {
    if (isOpen() !== open) {
      adapter?.beforeWidthChange();
      body.classList.toggle('sidebar-drawer-open', open);
      requestAnimationFrame(() => adapter?.afterWidthChange());
    }
    toggle.setAttribute('aria-expanded', String(open));
    toggle.title = open ? 'Show compact sidebar' : 'Show full sidebar';
  }
  function pin() {
    if (!enabled) return;
    clearTimer();
    body.classList.add('sidebar-drawer-pinned');
    setOpen(true);
  }
  function close(force = false) {
    clearTimer();
    if (!force && (pinned() || body.classList.contains('sidebar-resizing'))) return;
    body.classList.remove('sidebar-drawer-pinned');
    setOpen(false);
  }
  function refreshHoverDelay() {
    clearTimer();
    if (!enabled || !hovered || pinned()) return;
    const seconds = adapter?.hoverSeconds() ?? 3;
    timer = setTimeout(() => { if (enabled && hovered) pin(); },
      Math.max(0, seconds * 1000 - (performance.now() - enteredAt)));
  }
  function enter() {
    if (!enabled) return;
    if (!hovered) { hovered = true; enteredAt = performance.now(); refreshHoverDelay(); }
    setOpen(true);
  }
  function applyForView(nextScope) {
    const wasEnabled = enabled;
    enabled = desktop.matches && ['workspace-active', 'self-active', 'vault-active', 'assistant-active']
      .some(name => body.classList.contains(name));
    if (!enabled || nextScope !== scope && !surfaces.some(el => el.matches(':hover'))) {
      hovered = false;
      close(true);
    }
    scope = nextScope;
    if (enabled) body.classList.remove('sidebar-collapsed');
    if (enabled !== wasEnabled) adapter?.beforeWidthChange();
    body.classList.toggle('sidebar-drawer-enabled', enabled);
    if (enabled !== wasEnabled) requestAnimationFrame(() => adapter?.afterWidthChange());
    if (!enabled) {
      toggle.title = 'Show/hide files sidebar (remembered per workspace)';
      toggle.setAttribute('aria-expanded', String(!body.classList.contains('sidebar-collapsed')));
    }
  }
  for (const surface of surfaces) {
    surface.addEventListener('pointerenter', enter);
    surface.addEventListener('pointermove', enter, {passive: true});
    surface.addEventListener('pointerleave', event => {
      if (contains(event.relatedTarget)) return;
      hovered = false;
      close();
    });
    // The toggle manages its own click, including collapsing an open drawer.
    if (surface !== toggle) {
      surface.addEventListener('pointerdown', pin, {capture: true});
      surface.addEventListener('click', pin, {capture: true});
    }
    surface.addEventListener('focusin', event => {
      if (!enabled) return;
      if (event.target.matches?.('.sidebar-section-shortcut')) {
        // The compact button disappears on expansion. Move keyboard focus
        // into its full section so hiding that button cannot close the drawer.
        pin();
        const section = event.target.nextElementSibling;
        section?.setAttribute('tabindex', '-1');
        section?.focus({preventScroll: true});
      } else setOpen(true);
    });
    surface.addEventListener('focusout', event => {
      if (!contains(event.relatedTarget) && !hovered) close();
    });
    surface.addEventListener('keydown', event => {
      if (!enabled || event.key !== 'Escape') return;
      hovered = false;
      close(true);
      if (contains(document.activeElement)) document.activeElement.blur();
      event.stopPropagation();
    });
  }
  toggle.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); toggle.click(); }
  });
  document.addEventListener('pointerdown', event => {
    if (enabled && event.target.closest?.('#content, .term-console')) {
      hovered = false;
      close(true);
    }
  }, {capture: true});
  // Pointer events inside a proxied app do not bubble into the Lab document.
  window.addEventListener('blur', () => requestAnimationFrame(() => {
    const active = document.activeElement;
    if (enabled && active?.tagName === 'IFRAME' && active.closest('#content') && active.matches(':hover')) {
      hovered = false;
      close(true);
    }
  }));
  desktop.addEventListener('change', () => adapter?.applyView());
  window.LabSidebarDrawer = {
    connect(value) { adapter = value; },
    applyForView,
    refreshHoverDelay,
    layoutWidth() { return enabled ? 62 : null; },
    toggle() {
      if (!enabled) return false;
      if (isOpen()) { hovered = false; close(true); }
      else pin();
      return true;
    },
  };
})();
