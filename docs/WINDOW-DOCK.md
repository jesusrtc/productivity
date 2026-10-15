# Window docking

This experiment positions a real Chrome popup over a reserved rectangle in
Lab's central work area. External Objective, task and folder asset links try
this automatically by default. The site remains autonomous and is never embedded,
proxied or intercepted. Native alignment requires Chrome on the Mac running Lab.

## Use it and configure it

1. Reload Lab after installing this frontend change and click an external asset.
2. If setup is needed, the site opens normally and a closable alert provides a
   **Window docking settings** shortcut. The same controls live under
   **Settings → Global → Window docking**.
3. Choose **Enable window control**, enable **Lab Window Dock** in macOS System
   Settings → Privacy & Security → Accessibility, then **Check permission**.
   Install Xcode Command Line Tools if the helper cannot build. Allow pop-ups for
   your Lab address in Chrome. Asset clicks never request OS permission themselves.
4. Click the asset again. Its independent Chrome window occupies the central
   column, with Lab's sidebar and terminal outside the reserved rectangle.
5. **Detach** or **Back to Lab** keeps the site open independently; **Close popup**
   closes only that registered window. Another asset click or navigation detaches
   the previous window. The underlying draft and terminal stay mounted.

**Automatically dock asset links** is on by default and saved immediately per
browser (`labAutoDockAssets-v1`). Turn it off for ordinary pop-outs without setup
alerts. Command/Ctrl-click remains a normal tab, and explicit **Open in Chrome**
retains its existing behavior. The manual **Home → Objectives demo → Try docked
window (Mac)** trial still provides a URL field and a Dock button.

Permission denial, unavailable native support, helper/connection failures and
insufficient room all preserve the requested site as an ordinary popup with a
closable setup alert. Initial setup has an eight-second frontend deadline. Slow
status checks never proceed to attach after cancellation, and late attach
responses explicitly detach their original owner. Blocked pop-ups instead show
an **Open site** retry and instructions to allow them. No failure closes the site.

Chrome's frame is still visible. Focus, stacking, full screen, Spaces and multiple
monitors require manual validation. There is no extension or autostart service.

## How it works

`window-dock.js` opens a blank popup during the click, immediately clears its
opener, and marks both documents with unique temporary titles. The helper
matches the two Chrome accessibility WebAreas unambiguously, retaining their
window references instead of searching by a changing URL. Only after registration
does the blank popup navigate via a no-referrer link to the requested URL. Any
failure or cancellation also navigates that same popup to the requested site. This
works independently of the destination's framing and opener policies.

The browser measures the central content column, including expanded sidebars
and terminal margins, and reports its reserved rectangle once per second. It
keeps Lab dialogs usable by temporarily hiding the popup. The Swift
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
behavior against a fake native controller. Automatic-flow cases cover permission
fallback, setup settings and disablement, popup blocking, slow status/attach races,
connection failure, unsupported clients, narrow layouts, modified clicks and
navigation cleanup. The browser fixture serves a page
with framing denied and COOP enabled, checks exact URL/opener/referrer behavior,
and verifies retained drafts plus Detach leaving the page open. These tests do
not establish native alignment or focus behavior; that needs the live Mac trial.

After granting Accessibility permission, the opt-in
`test_window_dock_native_geometry` test can run with `LAB_TEST_NATIVE_DOCK=1`.
It opens an isolated Chrome profile, docks a framing-blocked page, moves/resizes
its parent window, compares actual native geometry, detaches and closes only its
test browser. Keyboard focus and app-switching comfort still need manual review.

Automatic asset docking is isolated in a follow-up commit titled
`feat(window-dock): auto-dock asset links with safe pop-out fallback`.
Use **Detach/Back to Lab**, then revert that commit and reload Lab to restore the
manual-only trial. This does not modify asset data or browser profiles.

The original experiment is isolated in a commit titled
`feat(window-dock): add opt-in macOS popup docking trial`.
Use **Detach/Exit trial**, then `git revert <that-commit>` and restart/reload Lab
to remove it. Generated helper files are untracked and inert after detach; the
Accessibility grant can also be removed in System Settings. No browser profile
cleanup or task-data migration is required.
