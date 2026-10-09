# Resource pop-outs use a five-position cycle

The user chose simple direct pop-outs after trying resource window management.
Every resource click must immediately create a new window, including another
click on the same URL. Do not add confirmation dialogs, URL/window registries,
reuse, focus restoration, automatic rearrangement or macOS scripts/helpers.
Leave existing resource windows under their own browser/window controls.

Keep the accepted placement: almost Lab's full width, below its workspace tabs,
with each new window 36px lower and a small horizontal offset so previous title
bars remain exposed. Cycle through exactly five positions; the sixth returns to
the first, the eleventh to the first again. Apply placement only when opening.
Browser feature height is content height, so reserve space for the popup frame
to avoid Chrome clamping an oversized window upward over Lab's tab strip.

Open the direct URL synchronously during the user's click on their own device
with noopener,noreferrer. Preserve Lab's drafts, navigation and terminals.
The explicit demo pop-out trial uses the same opening behavior. General explicit
browser-tab actions retain their separate existing behavior.

This supersedes resource-windows-cascade-and-reuse.md and the centering/attachment
discussion in resource-links-default-to-popouts.md.
