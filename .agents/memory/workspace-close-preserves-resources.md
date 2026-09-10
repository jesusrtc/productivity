# Closing workspace tabs preserves resources

Closing a workspace tab must only update its persisted `tab_open` flag and
return to its vault. Never kill terminal sessions, servers, or notebook kernels
from that action, and never reopen a tab just because it has live terminals.

The vault workspace list shows live terminal, managed/external server, and
notebook-kernel counts. Poll only while the list is mounted, keep requests
single-flight, scope counts to the owning vault, and exclude server tmux
sessions from terminal counts. Explicit terminal kill and permanent workspace
delete actions retain their separate lifecycle behavior.
