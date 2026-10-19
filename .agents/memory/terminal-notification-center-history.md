# Notification center retains the latest alert per terminal

The user requested a **Notifications** button next to **Lid Awake** on October
19, 2026. History shows each running terminal's latest red/green notification,
including reviewed and superseded alerts, in creation-time descending order,
20 at a time with **Load more**. Opening a card activates its exact terminal
and closes history. Outside click, close and Escape return to only current
input requests and unreviewed finishes, without reviewing them.

Retain the latest alert in session-local `@lab_notification`, read in the same
batched listing, so closed browsers do not lose alerts. The existing browser
report store provides a fallback for observed older-CLI reports, including when
the next report is working. Deduplicate shared terminal views by exact socket/session
incarnation. History clicks must use live navigation validation and the displayed
report ID: a past finish cannot review a newer report or change working/red
status. Red still persists after click until answered or updated. This extends
terminal-header-action-messages.md; ordinary active-card behavior is unchanged.
Expose history and opening/closing through Lab UI commands as well as controls.
