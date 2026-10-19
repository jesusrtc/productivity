# Tab drag previews slide neighbouring tabs

The user requested Chrome-like displacement while holding a dragged tab, for
both workspace tabs and terminal tabs. Neighbours should smoothly make room at
the prospective insertion position before release, including vertical terminals.
Use visual-only previews: no ordering writes during hover, exact final preview
on drop, and original order on cancellation or leaving. Preserve terminal task
blocks, fixed Home/Assistant tabs, session identities and running work.

Rapid direction changes should animate from current visible positions rather
than jumping. Drop thresholds use unanimated layout geometry to avoid oscillation.
Keep the native source mounted; reduced motion keeps the gap without sliding.
The shared tab-drag-preview helper owns only its own Web Animations, leaving
terminal status effects untouched. Verify trusted held drags, reversal, cancel,
release/reload, both terminal orientations and reduced motion in Chrome.
