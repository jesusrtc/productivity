# Window docking trial is opt-in and independently revertible

The user requested simulating an embedded site using a real autonomous Chrome
window aligned over Lab, and explicitly asked for a very specific commit that
can be reverted independently. The prototype belongs in Home → Objectives demo
as Try docked window (Mac), preserving ordinary resource pop-outs. It uses a
local native helper with explicit macOS Accessibility permission; no iframe,
proxy, profile change or autostart service. Dock/Detach/Close/Exit are explicit.

Keep this experiment and its documentation in its own commit. Do not include
unrelated working-tree changes. Browser/API regressions do not prove native
movement, stacking or focus: report which live Mac behaviors were actually
verified. This supersedes the prior no-helper preference only for this opt-in
trial, not the default link-opening behavior.
