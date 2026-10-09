# Resource windows cascade and reuse exact URLs

The user wants pop-outs almost as wide as Lab, with each subsequent title bar
36px lower and 12px to the right so prior activation/close controls remain
visible. Clicking the same complete URL must activate its resource window
without creating or reloading one. Lab owns the URL registry per browser window,
and the topbar ⧉ control lists/activates/closes those resources.

The user explicitly requested a macOS script to restore resources above Lab
after switching apps, replacing their Alfred workflow. The integrated native
helper source is core/src/core/native/ResourceWindows.swift; resource_windows.py
builds a stable Lab Resource Windows.app under framework .lab/native and invokes
it in the background through a local/admin/same-origin endpoint. macOS
Accessibility permission is required. Grant through ⧉ → Enable window control,
then reopen resources to register them. Do not silently grant OS permission.
Chrome Apple-event window queries were still hanging, so the helper uses public
Accessibility/CoreGraphics APIs. It registers a unique blank-page marker before
external navigation and keeps exact URL → process/window identities across site
redirects and backend/page reloads. Match native frames uniquely; uncertain
ownership must fail rather than raise another window. Installed PWA native titles
may stay Cerebro, so inspect the blank page's accessible WebArea title too.
Return-focus/topbar-click raising verifies that the owning Lab window is still
frontmost, then raises registered children oldest first. Never steal focus from
Slack after a delayed request. Closed/stale process identities are pruned.
Launch the short-lived app in the background without open -W: that flag raced
the helper's exit and failed its initial kevent call despite a valid result.
Wait for the helper's atomic response file with a bounded deadline instead.

Blank client pop-ups open synchronously during the click. Immediately set
opener=null before any external content loads; retain only the parent's proxy
for click-time focus. Navigate with a no-referrer anchor inside the blank window:
meta policy plus parent-driven location.replace did not suppress the referrer in
real Chrome. COOP can report a live window proxy as closed, so check captured
native identity before reopening and never interpret a severed proxy as definite
closure. Native operations are serialized, bounded, and back off after failure.
This supersedes the centering/no-handle and unimplemented attachment parts of
resource-links-default-to-popouts.md. Resource links still avoid iframes and keep
Lab's document/terminal drafts intact. The explicit demo trial calls the same
manager through a source-validated, user-activation-checked parent message.
