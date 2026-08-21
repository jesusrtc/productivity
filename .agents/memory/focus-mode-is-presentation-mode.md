---
name: focus-mode-is-presentation-mode
description: "Lab Focus mode is also presentation mode: fullscreen plus a screen wake lock"
metadata:
  type: project
---

The user expects Lab's existing **Focus mode** control to behave like video
presentation mode: request browser fullscreen and prevent the Mac display from
sleeping while Focus mode is active.

The implementation uses the Screen Wake Lock API, reacquires the lock when the
visible app returns to the foreground, and releases it when Focus mode ends.
Exiting browser fullscreen also exits Focus mode so the layout preference and
wake-lock lifetime stay in sync. Browsers without these APIs retain the original
chrome-hiding Focus mode behavior.
