# Compact sidebar preserves section spacing

The October 13, 2026 screenshots clarify that stable folded/unfolded geometry
applies to the entire first column, including Home, Vault and normal workspace
sidebars, not only Objective Tasks. Hidden file trees and Recently updated
lists must leave their full blank vertical space. META and its document icons
stay at exactly the same height, with unchanged scroll position. Keep one Files
and one Recently updated shortcut over their section headings; do not show each
file. Keep META readable and hide other labels, filters and the Links toolbar
without collapsing their space. This supersedes collapsed section/divider heights
in compact-sidebar-groups-files-and-recent.md and
compact-sidebar-icons-and-dividers.md.

Keep inner content and container queries at the expanded width while clipping
the outer rail. Sidebar width must resolve relative to the viewport (vw), not a
percentage of the narrow outer sidebar. Verify real section/icon coordinates,
large hidden file lists, META, saved proportional widths and scrolled states.
