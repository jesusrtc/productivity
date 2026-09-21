# Dashboard sections match independently

The client explicitly corrected the previous first-match rule: starring an item
must add it to Starred while it remains in Documents and every other matching
section. Exclusion belongs only in that section's filter, e.g.
`source = 'active' AND starred = false`. Do not infer mutually exclusive lists
or remove duplicates across sections. Each series is still collapsed to one
latest entry inside each section or list.

Section order is visual only; limits and counts are local to each section.
The global dashboard count counts unique displayed items. Repeated series rows
need distinct star-menu IDs scoped to their section; all copies reflect the
same underlying note/series stars when changed from any copy.
