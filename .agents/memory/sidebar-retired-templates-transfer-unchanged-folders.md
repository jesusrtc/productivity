# Transfer unchanged folders from retired sidebar templates

When replacing a cached scope, remove its old cache entry and use placeholders
for exactly equal source ranges. Reconcile live rows while the old pristine
template is still complete. Only afterward move its unchanged detached folders
into the new pristine template. The mounted-state map stores markup and live
boundary identities, not old template objects, so no other retained cache entry
needs the retired tree. Never transfer decorated live nodes into a template.

If reconciliation clones a new/mismatched parent, expand any placeholders in that
live clone from the still-intact old sources. Whole-sidebar fallback clones the
fully assembled new template. Count expanded elements before reconciliation to
skip it for oversized trees; those remain complete but uncached. Keep the existing
four-scope/60,000-element bounds and release all temporary source mappings.

Tests must cover changed ancestors, moved folders, external live-DOM edits,
new parents containing reused children, exact full-parse equivalence, focus/Git
state, explicit navigation, literal placeholder-like content, and cache accounting.
A common background refresh should neither reparse nor deep-clone equal folders.
