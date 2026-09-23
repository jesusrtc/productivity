# Document tab titles need more room

The collapsible document tabs drawer should open generously: 420px by default
in both inline and modal views, with long titles wrapping instead of truncating.
Since it overlays content, allow resizing up to 720px, bounded by the document
area while leaving 64px of content exposed for hover dismissal. Upgrade legacy
narrow widths once; preserve wider saved widths and any subsequent user resize.
