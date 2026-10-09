# Asset groups are client-defined

Objective assets can be manually grouped under a named header, with one flat
level of children revealed after a one-second hover. Leaving cancels the delay;
click and keyboard actions also open the group. The client chooses grouping,
membership and ordering through asset/group menus or a drop onto a group header.
Never infer grouping from matching URLs or document names.

`asset_groups` and `asset_order` are Objective presentation metadata maintained
through Lab's locked mutation API. Each asset belongs to at most one group in an
Objective; its existing IDs, URL fragments, assignments, stars and terminal
associations remain intact. Each task/bucket view shows its own applicable
members. Ungrouping releases references without deleting original assets.
