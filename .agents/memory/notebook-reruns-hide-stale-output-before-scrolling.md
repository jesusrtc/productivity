---
title: Notebook reruns hide stale output before scrolling
date: 2026-08-28
---

On the idle-to-running transition, hide a notebook cell's previous rich output
before moving the viewport and focus the cell header/code with `block: start`.
Centering the whole cell while a tall chart remains mounted scrolls into that
stale output, making a correctly streaming execution look as if it skipped
straight to the finished result. Preserve the hidden DOM until the server
accepts the run so request failures can restore its controls unchanged.
