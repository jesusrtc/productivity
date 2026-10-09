# Resource links default to pop-outs

The user tried Pop-out over Lab in the Objectives demo, said it worked perfectly,
and chose it for resource links. Objective links, their sublinks and task assets,
the details editor's Open action, and folder/worktree external links now use the
shared LabExternalLinks.open option popup:true. Request a separate window centered
over Lab with size/position features and noopener,noreferrer, synchronously during
the click and on the clicking device. Avoid iframes and native tab-reuse delays.
Keep document drafts, pending navigation, terminals and original URLs intact.
Folder modified clicks retain normal client tabs; Objective Cmd/Ctrl-click still
opens editable details. Existing general document/terminal/browser actions retain
their shared handler behavior.

The user also wants an open resource to return above Lab after switching to Slack
and selecting Lab in Alfred. The web popup API cannot reliably attach native
windows or guarantee foreground restoration; noopener intentionally supplies no
window handle. Do not claim this behavior is implemented or silently weaken that
boundary. Exact parent/child stacking needs a native macOS helper or desktop
shell. This supersedes workspace-external-links-open-in-center.md,
workspace-link-framing-fallback.md and resource-specific native tab reuse, while
the explicit demo controls retain their comparison options.
