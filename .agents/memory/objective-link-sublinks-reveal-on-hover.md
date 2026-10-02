# Objective link sublinks reveal on hover

The user wants one external link to contain a hierarchy of sublinks, such as
Google Docs tab destinations, instead of duplicate top-level resources. Add
children with + Sublink in the details view; each child has its own details and
may have children. Sidebar children reveal only after hovering over the parent
link for one second. Normal clicks show details; Cmd/Ctrl-click opens directly.

Nested children have stable IDs within the parent resource. Dragging a child
into a console pastes its exact URL; terminal associations store sub_link_id
and reopen that child's details. Removing a child subtree keeps the parent
resource association. The same renderer serves shared and worktree resources.
