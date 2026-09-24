# Background document refresh respects the active editor

Checking `_workspaceDocEditing` only when the mtime poll starts is insufficient:
the user can open Edit while the filesystem request is pending. Check again
after the response and scope validation, before advancing `_lastWorkspaceMtime`.
Keep the old baseline so polling catches the same change after editing ends.

`openWorkspaceDoc(..., {preserveScroll:true})` is a background refresh and must
return before resetting editor/navigation state if editing is active. Also
recheck editing before publishing a delayed text refresh or its error. The
fresh cache may still update, but the current draft and displayed source stay
owned by the editor. Explicit navigation retains its existing behavior.

The isolated document-edit workload caught this as an editor-reopen timeout:
a delayed mtime callback cleared the editing flag, then a WebSocket refresh
also ran. Deferred-response regression tests reproduce the old failures and
check the post-edit catch-up for both workspace and selected-worktree roots.
