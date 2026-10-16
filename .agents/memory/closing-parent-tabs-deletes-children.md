# Closing parent tabs deletes children

Closing a terminal group's parent requires one confirmation that explicitly
warns all child terminals will also be deleted and gives their count. Cancel
must leave every session and saved layout untouched. Confirm recursively closes
all descendants, including folded/nested children, before their parent and
purges their saved tabs and browser layout so they stay removed after reload.

Apply this to automation groups, ordinary subterminals, merged parent displays,
selected/named groups and the current-terminal close action. Closing a child
with its own descendants affects only that branch. Capture workspace/vault and
targets before async work, preserve unrelated groups, keep shared-document and
fixed-main restrictions, and surface partial failures. The CLI uses the same
menu and explicit confirmation through lab ui.
