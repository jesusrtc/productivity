---
title: Notebook hide-code uses fixed pin slots
date: 2026-09-02
---

In notebook hide-code mode, every pinned code cell and every current execution
must remain visible. Pins are persistent, workspace/notebook-scoped fixed slots.
Unpinned inactive cells share one transient accordion slot, so opening one
closes the previous transient cell; adding a pin adds another visible fixed
slot without consuming that transient slot.
