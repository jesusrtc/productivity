# Asset links automatically dock with a safe fallback

The user now wants ordinary asset clicks to align their real autonomous Chrome
window over Lab's central work area. This supersedes the demo-only/default-popout
constraint for external Objective, task, sublink and folder assets. Keep the
sidebar and terminal usable and retain the underlying document and drafts.

If permission, helper setup or any docking attempt fails, open the requested
site as an ordinary popup and show a closable alert with actionable Settings
access. Never close the requested website on a docking failure. Settings has an
immediate per-browser disable switch and explicit permission/check actions.
Command/Ctrl-click and explicit Open in Chrome retain their existing behavior.

Keep this follow-up in its own specifically named, independently revertible
commit. Native geometry/focus validation remains separate from browser tests;
report missing macOS Accessibility permission honestly.
