# Command-click opens Assistant documents in the modal

The user wants Command-click to open documents in the modal, consistent with
file and notebook previews. Apply this to Assistant entries, linked/recent
document shortcuts, and the rendered inline document body.

Document-entry Command-click cancels the pending ordinary inline click. Inline
body Command-click uses the same expansion as the Expand button, moving the
existing view and keeping its tabs and drafts. Capture the left click before
rendered links or controls act; preserve ordinary clicks and editable inputs.
Clicks inside an existing modal do not expand again.
