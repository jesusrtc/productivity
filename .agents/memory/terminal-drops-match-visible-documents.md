# Terminal drops match the visible document

Assistant series cards display the series title while ordinary opens follow the
latest dated note. Terminal drops and document drag payloads must use the
series document's ID/path, not the latest note's identity. Mixing them made a
terminal appear to rename to a different document after a drop.

Carry the displayed Assistant root and canonical document path into terminal
metadata writes. Reject stale roots/paths with a conflict before saving or
transferring links. Disable header drops while document navigation is busy and
clear the previous drop identity on close. Preserve custom labels, process
identity, conversation, and independent code links.

Verify this with a trusted browser drag from the terminal rail, plus backend
identity/conflict tests.
