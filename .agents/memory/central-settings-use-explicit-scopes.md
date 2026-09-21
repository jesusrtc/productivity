# Central settings use explicit scopes

The client wants one settings center on Cmd/Ctrl+, with Global and individual
workspaces, while retaining local gear buttons as shortcuts. Show installed
agents and the effective default: hiding Claude from + New does not select Codex.
Global agent/model/theme/autopilot and document policy are explicitly persisted
through lab.settings.update_global to $LAB_HOME/settings.json. Legacy vault
config remains a read-only fallback on reads; workspace overrides still win.

When editing an inactive workspace, pass its vault ID on API calls and use its
absolute path for sidebar storage. Never switch currentWorkspace or borrow the
active sidebar config. Browser terminal menu options retain vault::workspace
keys. Existing conversations keep their provider; only failed first launches
without a process/conversation reselect a corrected default on retry.
