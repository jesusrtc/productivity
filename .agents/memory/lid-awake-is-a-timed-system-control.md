---
name: lid-awake-is-a-timed-system-control
description: Lid Awake is the admin-only macOS pmset timer beside browser-only Keep Alive and Focus mode
metadata:
  type: project
---

Lab's **Lid Awake** control is distinct from browser **Keep Alive**. It uses
`/api/power/lid-awake` and a privileged macOS helper so the computer can keep
running after its lid closes. The helper watches a per-user deadline file,
restores `pmset -a disablesleep 0` on expiry, and survives the Lab page or
server closing. Renewals replace the deadline; cancellation removes it so the
helper restores normal sleep within one second. Keep the duration choices at
15, 30, and 60 minutes unless the product requirement changes.
