# Worktrees follow task asset buckets

The user wants each associated worktree to be an asset: Unassigned until it is
attached to a task, then visible in that selected task's assets. Shared Objective
stars and Archive work as for other assets. Only the gray Root and Objective
scope rows stay in the fixed navigation list; keep them visible in the demo too,
outside its collapsible Files explorer. Worktrees remain easy to create or
associate from the existing + chooser, then appear in Unassigned.

Derive live worktree assets from Objective membership using existing folder
references (root/path), including canonical alias matching. No registry format
change or data migration is needed. Preserve resource scoping when dropping a
resource onto a worktree row, source paths, terminal associations, launch
folders and original Assistant ownership.

Native explorer files/folders and recent files must not have asset stars or
classification controls; the worktree itself is the asset. Files explicitly
linked into a task/Objective bucket still have asset controls there, and plain
explorer file drags can still attach a reference. Do not automatically classify
every file in a checkout as an asset. This supersedes the earlier native file
star decoration in live-objectives-use-task-asset-buckets.md.
