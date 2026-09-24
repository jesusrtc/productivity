# Sidebar Pin controls keep their own name

Ordinary workspace file rows carry a path for opening, dragging and context
menus, but `togglePin` historically receives the file's `name`. These can differ.
The single-element Pin button therefore stores an escaped `data-pin-name` and
the shared sidebar click handler reads that value, rather than reusing
`data-filepath`.

Keep the button's block display when hovered: removing its former flex wrapper
otherwise changes its text baseline. Native Chrome comparisons cover both
themes, widths, zoom levels, pin states, Git badges and hover states. Pin clicks
and Enter must avoid file navigation; the existing row double-click behavior
remains unchanged. Worktree views still omit these controls.

The 5,000-file Git fixture removed 5,004 elements and improved measured switch
median, but the matched first-open time did not improve. Do not call the earlier
cold-open latency miss fixed based on that comparison.
