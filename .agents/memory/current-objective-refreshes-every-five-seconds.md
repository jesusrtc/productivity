# Current Objective refreshes every five seconds

Tasks, links, subtabs and other registered assets created through Lab or edited
outside an open browser must appear without a page reload. Poll the current
visible workspace's Objective payload every five seconds and on window focus
or visibility restoration. Compare complete payloads, since document/subtab
content can change without the manifest revision changing. Unchanged reads
must not rebuild UI rows. Refresh task/overview/library projections on change
and retain unsaved document/link drafts and terminal hover state.

Deduplicate in-flight reads, skip queued saves, and discard a background read
when a newer save or cache publication overtakes it. Outgoing scope responses
may update only their own cache. Retry transient polling failures silently.

The existing five-second Files timer previously honored a one-minute browser
cache. Active Objective directory reads now use a five-second maxAge; other
scopes and expensive Git/recent projections retain their existing caching.
Directory membership is already keyed by folder mtime on the server. Read only
visible/open directories, and preserve their live nodes and expansion state.
