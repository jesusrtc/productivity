# Bell switch stays open while checking notifications

The user clarified on October 19, 2026 that the notification control must show
only a bell and toggle switch, with no visible text. Its accessible label is
Show all notifications. Turning it on shows the existing latest-alert history.
Clicking any notification must keep the list and switch on, including after
green review and navigation rerenders, so the user can check several terminals.
Clicks elsewhere in Lab return to current alerts; explicit switch-off, close
and Escape are retained. New terminal events update individual active markers
without closing the list.

Keep the normal red/green cards and lifecycle. A white vertical line marks
currently active alerts; it clears on answer, replacement or green review while
the historical card remains. Put the native owning workspace and Objective
before the terminal, vault and state. Read owner names once per workspace in
the existing attention batch, never from the currently selected workspace or
by fetching full Objective documents for every card. Explicit child ownership
wins over inheritance; borrowed terminals retain the original owner's label.
This supersedes the close-on-card-click and text button instructions in
terminal-notification-center-history.md. Keep exact incarnation validation,
report-ID-safe acknowledgement, paging and the deferred renderer path.
