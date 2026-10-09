# Resource pop-outs cycle through positions 2, 3 and 4

The user prefers the former second cascade window's height, width and position
as the first opening. Keep only the old five-position cascade's second, third
and fourth positions, repeating 2 → 3 → 4 → 2 → 3 → 4. Preserve each position's
complete geometry, including the progressively smaller width and height.
In the shared popup formula these are zero-based slots 1, 2 and 3.

This supersedes only the five-position layout in
resource-popouts-use-five-position-cycle.md. Keep direct new-window opening
on every click, with no confirmation, resource registry, reuse or macOS helper.
