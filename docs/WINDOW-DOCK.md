# Window docking prototype

This experiment positions a real Chrome popup over a reserved rectangle in
Lab's Objectives demo. It does not embed, proxy or intercept the external site.
The initial trial is macOS/source-checkout only and leaves normal links alone.

## Try it

1. Restart the Lab backend after installing this change and reload Lab.
2. Open **Home → Objectives demo → Try docked window (Mac)**.
3. Choose **Enable window control**. Enable **Lab Window Dock** in System
   Settings → Privacy & Security → Accessibility, then **Check permission**.
4. Enter an HTTP(S) URL and click **Dock**. Allow popups for Lab if prompted.
5. Move/resize Lab, click its exposed controls, and switch to another app and
   back. Check whether the popup stays aligned and focus remains usable.
6. **Detach** keeps the site open independently. **Close popup** closes only
   that registered popup. **Exit trial** detaches and removes the trial panel.

The experiment does not change task data, documents, terminal processes,
Chrome profiles, or normal resource-link behavior. There is no autostart agent.
The prototype still has Chrome's frame and may show transient displacement or
focus/stacking differences. Full screen, Spaces and multiple monitors require
manual validation before considering production use.

## How it works

`window-dock.js` opens a blank popup during the click, immediately clears its
opener, and marks both documents with unique temporary titles. The helper
matches the two Chrome accessibility WebAreas unambiguously, retaining their
window references instead of searching by a changing URL. Only after registration
does the blank popup navigate via a no-referrer link to the requested URL. This
works independently of the destination's framing and opener policies.

The browser reports a normalized viewport rectangle once per second. The Swift
helper reads the parent window and WebArea frames every 100 ms and moves/resizes
the popup to match. It does not query Chrome through Apple events. It raises the
child once when focus changes into the specific parent; it never activates a
browser over another application or targets unrelated Chrome windows. Inactive
Lab tabs and minimized parents cause the popup to minimize. A helper-minimized
popup is restored on detach. A twelve-second lease bounds orphan controllers.

`POST /api/ui/window-dock` accepts `status`, `permission`, `attach`, `update`,
`detach` and `close`. It requires a local administrator, localhost and the exact
Lab origin. Owner IDs are random per view; screen rectangles are bounded to the
viewport. There are at most four controllers, one popup per view. IPC directories
are private temporary directories; files contain geometry/control state, not
browser history or external-site content. Backend restarts drop session tracking
and the old helper detaches after its lease expires.

The signed helper is built on demand from
`core/src/core/native/WindowDock.swift`. Its generated app is under the resolved
framework checkout at `.lab/native/window-dock/Lab Window Dock.app`. This requires
Xcode Command Line Tools and an explicit macOS Accessibility grant.

## Validation and rollback

The focused tests cover local-owner/origin enforcement, geometry validation,
session ownership, duplicate-controller rejection, cleanup, and real Chrome UI
behavior against a fake native controller. The browser fixture serves a page
with framing denied and COOP enabled, checks exact URL/opener/referrer behavior,
and verifies retained drafts plus Detach leaving the page open. These tests do
not establish native alignment or focus behavior; that needs the live Mac trial.

After granting Accessibility permission, the opt-in
`test_window_dock_native_geometry` test can run with `LAB_TEST_NATIVE_DOCK=1`.
It opens an isolated Chrome profile, docks a framing-blocked page, moves/resizes
its parent window, compares actual native geometry, detaches and closes only its
test browser. Keyboard focus and app-switching comfort still need manual review.

This experiment is isolated in a commit titled
`feat(window-dock): add opt-in macOS popup docking trial`.
Use **Detach/Exit trial**, then `git revert <that-commit>` and restart/reload Lab
to remove it. Generated helper files are untracked and inert after detach; the
Accessibility grant can also be removed in System Settings. No browser profile
cleanup or task-data migration is required.
