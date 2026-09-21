# Assistant dashboard and one entry per series

The September 18, 2026 request makes Documents open on an editable dashboard.
Users add, rename, filter, reorder, and remove sections. Default Priority matches
open P1 work OR due within two local calendar days (including overdue work and
tracked subtabs). Settings persist separately in `.assistant/dashboard.json`
with validation, atomic writes, and revision conflicts; preserve editor drafts
and focus during polling.

A series appears once within each list or dashboard section. Sections match
independently: an item can appear in Starred, Documents and other matching
sections at the same time. Section order never claims or removes items. Always open its latest dated note even when
an older note caused the match. Never discard older pending actions or starred
notes to deduplicate the list. The list star targets the series; the modal
header star targets the individual note. Use distinct note, meeting, and
recurring meeting icons.

Previous dates belong inside the modal's More in this series menu, with date /
title search and starred-note / open-task filters. Membership uses the full
index independently of outer filters. Keep document tabs separate and preserve
menu state, query, keyboard focus, and text selection through refreshes.
