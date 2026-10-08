# Child terminals merge with their parent

The user clarified on October 8, 2026: replace **Set as main** / display swaps
with **Merge with parent**. Combine the immediate parent and selected child into
one displayed tab that keeps the parent's current name, icon and color while
opening the selected child's actual console. Keep ancestor positions, session
IDs, real parent relationships, task associations and process ownership intact.
Do not show a swapped copy of the parent under the child. Preserve the child's
descendants, and retain the parent's console through **Open parent terminal**.
**Unmerge from parent** restores separate rows. Existing browser-scoped display
preferences now use the merge presentation without changing their saved owners.

The merged tab's explicit **Renew connections** action reruns all eligible
automation descendants of the real parent, including running connections. Keep
the parent console untouched, child identities stable and old output archived.
This is an explicit exception to stopped-only recovery. Ordinary recovery still
skips running work; passive polling and browser reconnect never replay commands.
Both modes retain workspace/vault ownership, single-pane checks, launch cooldown,
generation checks and request deduplication. Reconnecting a nested tmux client
keeps the inner session running.

This supersedes the swapping presentation in
[Child terminal main is display only](child-terminal-main-is-display-only.md)
and [Set as main swaps with the immediate parent](child-main-swaps-immediate-parent.md).
