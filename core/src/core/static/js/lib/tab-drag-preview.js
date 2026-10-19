/* Animate layout changes during native tab drags without changing saved order. */
(() => {
  const running = new WeakMap(), motions = new WeakMap();

  function cancel(container) {
    const animations = running.get(container);
    running.delete(container);
    for (const [node, animation] of animations || []) {
      if (motions.get(node) === animation) motions.delete(node);
      animation.cancel();
    }
  }

  function capture(container, selector) {
    // Sample the current visual position before interrupting an earlier move.
    const positions = new Map();
    for (const node of container.querySelectorAll(selector)) {
      if (node.matches('.dragging,[aria-hidden="true"]')) continue;
      const rect = node.getBoundingClientRect();
      if (rect.width && rect.height) positions.set(node, rect);
    }
    cancel(container);
    return positions;
  }

  function play(container, positions) {
    if (!positions || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    const animations = new Map();
    running.set(container, animations);
    for (const [node, before] of positions) {
      if (!node.isConnected || node.matches('.dragging,[aria-hidden="true"]') || !node.animate) continue;
      const after = node.getBoundingClientRect();
      if (!after.width || !after.height) continue;
      const x = before.left - after.left, y = before.top - after.top;
      if (Math.abs(x) < .5 && Math.abs(y) < .5) continue;
      const animation = node.animate([{translate:`${x}px ${y}px`}, {translate:'0px 0px'}],
        {duration:180, easing:'cubic-bezier(.2,.8,.2,1)'});
      animation.id = 'lab-tab-drag-shift';
      animations.set(node, animation); motions.set(node, animation);
      animation.onfinish = animation.oncancel = () => {
        animations.delete(node);
        if (motions.get(node) === animation) motions.delete(node);
        if (!animations.size && running.get(container) === animations) running.delete(container);
      };
    }
    if (!animations.size) running.delete(container);
  }

  function rect(node) {
    const box = node.getBoundingClientRect();
    if (!motions.has(node)) return box;
    // Drop thresholds use the final layout, not a neighbour sliding past it.
    const [x, y] = getComputedStyle(node).translate.split(/\s+/).map(value => parseFloat(value) || 0);
    return {left:box.left-x, right:box.right-x, top:box.top-(y||0), bottom:box.bottom-(y||0), width:box.width, height:box.height};
  }

  window.LabTabDragPreview = {capture, play, rect, cancel};
})();
