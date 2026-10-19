# Notification center searches at the bottom

On October 19, 2026 the user requested notification cards and the center at
the bottom of the screen, plus a search field at the top of the center. Anchor
the overlay at the bottom right without reserving console space; this supersedes
the top-right placement in terminal-header-action-messages.md.

Match all entered keywords across the full latest-alert history before paging,
including owning workspace/Objective, terminal, vault, status, creation time and
message. Ignore case and diacritics. Keep the search input mounted during typing,
composition, polling and card review so its value and caret survive. Keep its
search/header toolbar visible while results scroll, with counts, clear and
no-match feedback. Closing clears the query and restores all active alerts;
review/navigation must still use the exact session incarnation and report ID.
