# Git decorations index path prefixes and avoid no-op DOM writes

Large changed-file sets must not be scanned once per sidebar row. Build fresh,
request-local indexes for added/untracked directory inheritance, folder change
rollups and ignored path prefixes. Exact truthy statuses still win; overlapping
added/untracked ancestors retain original Object.keys order precedence. Modified,
deleted or renamed descendants dominate folder rollups. Preserve literal path
component boundaries and ignored-prefix trailing-slash handling.

Repeated status application must leave existing badges in place and avoid writing
an unchanged title. A clean response only needs decorated rows, including orphan
badges/dots. Keep the existing workspace/worktree, instruction-root and proxy
guards; newly mounted pristine rows still receive cached decorations.

The disposable latency fixture's --git-changes option creates and commits only
its own temporary repositories, then modifies a chosen subset of extra files.
Validate fetched statuses and both normal/recent row decorations so a missing Git
response cannot look like a performance improvement.
