# Workspace external links open in the middle panel

The user wants ordinary clicks on folder/worktree external link chips to open the
URL inside Lab's middle content panel. Keep Files at its selected visibility and
the existing workspace terminal usable, with drafts and connection intact. This
supersedes the browser-only ordinary click in
`folder-external-links-open-on-client.md`; browser fallback and modified clicks
still open on the clicking client using `{clientOnly:true}`.

`LabScopeLinks.openExternal` mounts a direct, sandboxed iframe beside `#content`,
temporarily hides content without destroying its editor, and supplies reload,
browser-open, and red close controls. Repeated clicks retain the live frame.
Document lifecycle and terminal navigation guards cancel older asynchronous
opens; document, file, scope, workspace, dashboard and repository navigation
clear the external view. Only internal documents use their existing expanded
default. Do not proxy external sites or bypass their framing/login restrictions;
the visible browser button provides the fallback.

Native browser regressions in `test_frontend_scope_external_view.py` verify the
real cross-origin embed, center geometry, narrow panels, preserved drafts,
reload with URL fragments, client-only fallback and cancellation.
