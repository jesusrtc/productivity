# Terminal tabs activate their Home sections

Clicking a terminal in the shared Home pool also navigates to its associated
Overview, vault, or Logs section. Remember the exact clicked logical session
before section restoration so another session with the same badge cannot win.
Use the existing warm attach path to retain its pane, socket, and progress.
Even clicking the mounted terminal must invalidate an older pending attach.

Vault navigation publishes its destination before awaiting the catalog and
ignores older catalog responses. Deferred Home/vault initialization checks the
owning workspace object before updating the sidebar or restoring a terminal.
