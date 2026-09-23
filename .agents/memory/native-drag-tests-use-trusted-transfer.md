# Verify drag copy mode with a trusted dragstart

In the Chrome regression fixture, a constructed DataTransfer accepted the file
payload but kept effectAllowed at `none`. That is insufficient to test native
drag copy mode. Send native mouse press/move events, inspect the trusted
dragstart after the production handler has populated its DataTransfer, then
cancel that owned test drag to avoid an unintended drop.

Synthetic DragEvents remain useful for checking exact payloads on many rows.
After native drag/context steps, move the pointer away before independent
hover-sensitive pixel comparisons. Preserve their existing tolerances.
