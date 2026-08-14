# Lab navigation is cross-workspace

The Lab top bar is a persistent, cross-workspace surface. Home is the
permanent framework home. Workspace and project tabs can remain open together
even when their roots belong to different registered workspaces, so navigating
or operating a terminal must pass the owning workspace id/path explicitly and
must not call the global workspace-switch endpoint.

Workspace display name and `#RRGGBB` color live under `display` in that
workspace's `workspace.json`. Use the color as a subtle tab cue rather than a
space-consuming workspace badge. Home Admin owns consolidated servers,
terminals, and logs; Code Search is a scoped inner tab on Home,
workspace, and project views.
