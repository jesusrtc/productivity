# Terminal bar settings and context actions

The terminal header keeps session identity, copy-attach, and one settings cog.
The modal owns vertical/horizontal layout, icons/text appearance, recent-tab
window/color, and a Danger zone with confirmed Kill all. The New button follows
the last tab, including when the rail is empty. Its picker lives outside the
scrolling rail so it cannot be clipped.

Secondary-click tabs to rename, add dividers, create/join/leave named groups,
or close a tab/group. Groups have colors and collapse/expand. Close actions must
capture vault/workspace and exact session names before awaiting requests;
closing a background tab must not detach the active terminal. Destructive UI
checks use sample tabs and intercept mutations rather than killing real work.
