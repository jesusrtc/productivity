# Meta keeps workspace instructions visible

Lab agent context must be visible in Assistant as well as Home and workspaces.
Assistant agents already use `lab agents run` and receive the packaged guide.

Meta keeps instruction-file shortcuts anchored to the owning workspace or
Assistant root. When Files shows another folder/worktree, show that location's
instructions in a separate labeled group, preserving each file's root for
opening, highlighting, and file actions. Discover only the three instruction
paths, including Copilot's hidden file, without a recursive repository scan.

These are current files on disk, not a record of what a provider loaded at
startup. New terminals start in the selected folder/worktree; changing the
sidebar or linking an existing terminal does not change its startup context.
