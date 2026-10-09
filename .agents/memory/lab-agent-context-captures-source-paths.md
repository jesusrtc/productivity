# Lab agent context captures source paths

The user wants the Lab agent context shortcut to instantiate a packaged
template with the owning vault, workspace and Objective instruction paths,
relative to the Files folder/worktree it was pulled from. Include the absolute
source folder as the base and existing instruction files at each scope; do not
generate instruction files. Resolve Objective roots from workspace metadata.

Capture source identities in the sidebar row, reader and drag payload. Cache
rendered guides by source path, vault, workspace and Objective rather than one
global guide. A source selection change must not retarget a pending drag or a
reader's context; switching the destination terminal during a fetch still
cancels its paste. The reader drag carries the exact displayed content.
