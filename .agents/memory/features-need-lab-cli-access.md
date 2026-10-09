# Features need Lab CLI access

The user expects Lab features to be available through the `lab` CLI as well as
the UI. Verify the command path when adding framework metadata operations and
keep its help and context documentation discoverable.

Objective asset groups use `lab objective ls` and `lab objective apply` with
`asset-group-create`, `asset-group-member` (including removal with a null group),
`asset-group-rename`, `asset-group-ungroup` and `asset-order`. The CLI and UI share
the locked Objective store and its revision checks.
