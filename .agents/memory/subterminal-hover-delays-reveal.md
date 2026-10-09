# Subterminal hover delays reveal

The user wants a one-second hold before hovering a terminal reveals its children,
so passing across tabs does not expand and then collapse the hierarchy. Cancel
the pending reveal when the pointer leaves. Preserve elapsed hover time across
changed polling; a repaint must not reveal early or restart the full delay.

Keyboard disclosure remains immediate. Preserve own-WIP children and the active
child's direct siblings and ancestor path, along with nested parent ownership,
merged tabs, session identity and live processes.
