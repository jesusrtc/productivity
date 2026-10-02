# Reviewed terminal cleanup belongs inside Resources

The user's October 2026 request supersedes the earlier global Cleanup button:
Resources owns cleanup in its existing table layout. Show cleanup candidates
opens on All workspaces, with tabs for scoped review (including empty scopes),
exact session names, owning workspace/vault and last activity/access. Individual
Kill and counted bulk Kill controls submit only the displayed reviewed candidate
fingerprints. Keep confirmations, backend inactivity rechecks, exclusions and
saved conversations; do not stop user terminals during tests. Failed reviews
disable stale kills. Show all processes restores monitoring and file-scan controls.
