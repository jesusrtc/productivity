# Markdown and asset links use windows

The user wants links in Markdown and Objective/task assets to open immediately
in client pop-out windows. Command-click opens a browser tab; Ctrl-click is the
cross-platform equivalent. Preserve exact URLs, including local Markdown
document routes and sublink identities, and use the existing window geometry.

Capture editable Markdown link mousedown before CodeMirror replaces the anchor
with editable syntax, and handle its click once without changing or saving the
draft. Keep in-page anchors and downloads on their existing handlers. General
links outside Markdown retain their existing opening policy.

This replaces Objective Cmd/Ctrl-click opening editable link metadata from
resource-links-default-to-popouts.md. Link details remain reachable through the
asset context menu's Edit link details action, including individual sublinks.
