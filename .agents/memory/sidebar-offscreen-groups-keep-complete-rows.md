# Offscreen sidebar groups retain the complete tree

Recently updated uses `content-visibility: auto` on folder children and on plain
100-row groups in flat folders above 200 files. Every file remains in the DOM:
native find-in-page, drag/context attributes, and click actions must keep working.
Initial intrinsic heights use visible row counts times the existing 22px metric;
update this assumption if row geometry changes. Browser checks compare scroll
extents/hit targets at 220/340px widths and 100/125% zoom in flat and nested trees.
Keep the existing template cache limits; do not enlarge them for a fixture.

Open live groups are now progressively prepared in idle callbacks and promoted
to visible content. Width changes invalidate that preparation and restore auto
skipping before re-preparing; see sidebar-idle-layout-prepares-live-groups.md.
