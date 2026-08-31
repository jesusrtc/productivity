# Terminal attach picker groups live sessions

The Terminal **+ New → Attach tmux session…** flow uses a modal instead of a
free-text session-name field. It lists accessible live sessions across Lab's
rolling tmux sockets, groups them by workspace/project, and separates sessions
with and without attached tmux clients. The project from which the picker was
opened is pinned first, with its unattached sessions first. The target scope is
captured when the modal opens so later navigation cannot redirect the attach.

Admins may also import otherwise-unregistered host tmux sessions, shown under
**Unassigned**. Selecting any row must continue using the grouped-session alias
endpoint so the source session remains independently alive.
