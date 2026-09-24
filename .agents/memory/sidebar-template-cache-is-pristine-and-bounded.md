# Sidebar template reuse preserves clean DOM state

The workspace sidebar reuses parsed, detached templates only when the complete
rendered markup matches. Folder IDs are deterministic by scope/path so identical
trees can match. Mount a clone, never the template or a previous live tree: file
selection, Git badges, input state, and listeners can change after rendering.

Keep both retention limits (four scopes and 60,000 aggregate elements). Evict
least-recently-used scopes; render oversized trees completely without caching
them. Changes to files, scope, folder expansion, configuration, and activity
must change markup and rebuild the template. Existing decorations and agent
context still refresh after mounting. Browser tests verify clone behavior and
both limits. This improves large warm switches; it does not solve cold rendering.
