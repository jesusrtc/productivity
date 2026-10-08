# Subterminals without their own WIP task use parent hover

The October 8 clarification in [Active subterminal family stays visible](active-subterminal-family-stays-visible.md)
supersedes the selected-child and selected-automation folding behavior below.

The user clarified on October 7, 2026 that a subterminal appears on parent hover
unless it has its own In progress task association. Inherited WIP context is not
an association. Automation children always use parent hover, even when selected
or associated with WIP. Keep each own-WIP child visible without revealing its
hover-only siblings. Selecting a hover-only child keeps its console active, but
leaving the parent hides its row. Keyboard disclosure remains available. This
supersedes inherited-WIP and selected-child retention in the earlier terminal
visibility memories; keep the always-visible WIP Tasks sidebar behavior.

Preserve nested hierarchy, session identity, parent recovery controls and live
processes. Deeply nested own-WIP terminals stay visible while hover-only ancestor
rows remain folded. Restore hovered branches after changed polling and retain rows on
unchanged polling. Native Chrome checks cover both orientations, mixed WIP and
automation siblings, nested inherited children, active children and keyboard
disclosure.
