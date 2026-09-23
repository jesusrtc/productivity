# Polling watcher does not follow nested links

Use PollingObserverVFS with os.lstat for the default macOS index watcher. Watchdog's
normal os.stat recursively follows links; docs/back pointing at an ancestor plus
another linked alias reproduced runaway traversal and hung watcher shutdown.
Observe nested symlinks themselves instead. Explicit watch roots remain resolved,
and the separate workspace Files walker preserves linked-folder browsing with
ancestor inode checks. Test the watcher and API walker independently.
