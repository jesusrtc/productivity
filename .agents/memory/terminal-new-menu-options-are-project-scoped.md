# Terminal New menu options are project-scoped

Terminal settings includes checkboxes for Claude Code, Codex, Copilot, Terminal,
and Attach tmux session. Persist the selected subset in browser storage under
`labTermNewOptions-v1:` plus the workspace/project terminal scope. Defaults keep
all options; a user's selection only narrows workspace-supported agents and
does not enable unavailable CLIs. Selecting just Codex and Terminal must also
hide Attach. An empty menu offers a route back to settings.

Capture the settings panel's scope when it opens, and discard a pending menu
open when navigation changes its target scope.
