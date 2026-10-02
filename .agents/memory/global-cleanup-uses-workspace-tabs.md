# Global Cleanup uses workspace tabs

Cleanup belongs in the global header beside Logs, not in workspace subtabs.
Its existing inactivity-review modal now has one tab per known workspace,
including workspaces with no eligible sessions. Open on the current workspace;
keep exact session names, counts and reviewed candidate IDs. Show only the
selected workspace's candidates and scope the kill button/confirmation to that
workspace. Preserve the backend's inactivity rechecks, exclusions, exact-target
stops and saved-conversation behavior. Keyboard arrows/Home/End navigate tabs.
Moving this control does not authorize stopping any user terminals in tests.
