# Workspace links remember sites that need a browser

Public Slack, GitHub, Teams, Bitbucket, Linear, Notion, and Figma prohibit ordinary
framing, so scope link chips open their actual domains in the browser directly.
Figma's official embed URLs are exceptions. Match domains with a dot boundary,
never icon/service inference: self-hosted clients can permit embedding even when
they use these service icons. Do not proxy or bypass framing restrictions.

Cross-origin iframe failures cannot be reliably detected using load/error
events. Keep **Open in browser** and **Always open in browser** visible in the
middle panel. The latter remembers an exact HTTP(S) origin in localStorage
`lab.scope-links.browser-origins.v1` (bounded to 100 entries), restores the prior
content, and changes the chip's destination hint. The expanded link editor can
reset remembered choices with **Use middle panel again**; this preference does
not dirty or write checkout metadata. Known framing blockers have no reset.

This refines the embed defaults in `workspace-external-links-open-in-center.md`.
Real browser regressions cover known blockers, Figma embeds, lookalikes,
self-hosted icons, persistence, reset, and existing editor/terminal state.
