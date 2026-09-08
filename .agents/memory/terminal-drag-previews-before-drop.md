# Terminal drag previews before drop

Terminal tab dragging must make space for a visible preview at the prospective
position and highlight/name the destination group before release. Group headers,
including collapsed groups, accept drops; temporarily open a collapsed group
to reveal the insertion point. Leaving or canceling restores its previous view.

Use the same `_termPlanItemMove` helper for preview and commit. Hover must never
write browser state or send reorder requests. Keep the native drag source node
mounted and suppress same-scope rail rerenders during a drag; navigation cancels
the preview. Verify both orientations and a real held-mouse drag, including that
the released order equals the last preview.
