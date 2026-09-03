---
title: Notebook hide-code uses fixed pin slots
date: 2026-09-02
---

In notebook hide-code mode, every pinned code cell and every current execution
must remain visible. Pins are persistent, workspace/notebook-scoped fixed slots.
The clicked or focused code cell (including a click anywhere in its output) owns
one transient active slot, so activating another cell closes the prior transient
cell without affecting pins or running cells. Do not render per-cell Show code
buttons. Keep the active cell stable across live notebook re-renders by cell id.
