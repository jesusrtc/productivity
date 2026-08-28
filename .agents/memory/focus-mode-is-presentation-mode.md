---
name: focus-mode-and-keep-alive
description: "Lab Focus mode is presentation mode, while Keep Alive exposes its screen wake lock independently"
metadata:
  type: project
---

The user expects Lab's existing **Focus mode** control to behave like video
presentation mode: request browser fullscreen and prevent the Mac display from
sleeping while Focus mode is active.

The adjacent **Keep Alive** switch owns the same Screen Wake Lock API without
changing the layout or entering fullscreen. Both settings persist independently.
The shared wake lock remains active while either Focus mode or Keep Alive is on,
reacquires when the visible app returns to the foreground, and releases only
when both are off. Exiting browser fullscreen still exits Focus mode; Keep Alive,
if enabled, continues preventing sleep. Browsers without the Wake Lock API keep
the original UI behavior and fail gracefully.
