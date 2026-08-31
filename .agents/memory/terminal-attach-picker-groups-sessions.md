# Terminal attach picker groups live sessions

The Terminal **+ New → Attach tmux session…** flow uses a modal instead of a
free-text session-name field. It lists accessible live sessions across Lab's
rolling tmux sockets, groups them by workspace/project, and separates sessions
that already have a Lab terminal tab from sessions available to add. Tmux's
live-client count is deliberately not used for this state. The project from
which the picker was opened is pinned first, with available sessions first.
Rows that already have a Lab tab are labeled **attached** and cannot create a
duplicate tab. The target scope is captured when the modal opens so later
navigation cannot redirect the attach.

Admins may also import otherwise-unregistered host tmux sessions, shown under
**Unassigned**. Lab-created grouped aliases are omitted as duplicate picker
rows; their original source carries the existing-tab state. Selecting an
available row must continue using the grouped-session alias endpoint so the
source session remains independently alive.
