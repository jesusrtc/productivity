# Terminal asset links preserve origin

The user separates a terminal’s birth context (workspace, Objective or task)
from its optional asset link. Origin keeps the cwd, primary ownership and
visibility policy. Linking or unlinking an asset must not restart, reassign or
rename the terminal.

Provide Link to asset… / Unlink asset in terminal menus and Link to active
terminal in asset menus; preserve drag and drop onto tabs and sidebar assets.
Clicking an asset activates its terminal and clicking the terminal opens the
exact asset/subtab/sublink. Tabs and active headers adopt the shared asset icon
before task/default icons, including notebook and GitHub graphics. This works
for fixed mains and automation primaries too. Console drops remain unsent paste.

The terminal-asset Objective action stores an independent nested asset target
under the stable session ID. The terminal action continues to manage ownership
and preserves this asset binding. New plain-file links outside Objectives set
linked_file.activate=true; legacy links retain their Sync linked preference
until relinked. This extends the older separate-links-from-sync rule without
changing old preferences globally.
