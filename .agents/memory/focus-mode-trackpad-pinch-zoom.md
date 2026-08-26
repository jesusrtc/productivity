---
name: focus-mode-trackpad-pinch-zoom
description: "Focus mode reproduces Chrome trackpad pinch zoom while browser fullscreen suppresses native page zoom"
metadata:
  type: project
---

Chrome exposes macOS trackpad pinch as a cancelable `Ctrl+wheel` gesture, but
native page zoom is suppressed while Lab is in Fullscreen API presentation
mode. Lab handles that gesture only while `body.focus-mode` is active and uses
CSS `zoom` (clamped to 50–300%) so fixed panels and scrollable layout continue
to reflow. Normal two-finger scrolling and all gestures outside Focus mode keep
their browser-native behavior. Same-origin iframe documents are wired on load
because wheel events do not bubble across iframe boundaries.
