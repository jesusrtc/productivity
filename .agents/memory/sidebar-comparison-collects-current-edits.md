# Local-main comparisons collect their own current edits

A recent Uncommitted snapshot must not restrict a new local-main comparison.
Even a snapshot under five seconds old can miss edits made after collection.
Compare `refs/heads/main` directly with the working tree each time the local-main
snapshot refreshes. This includes staged additions and unstaged edits and omits
branch edits reverted locally to main. Keep the existing minute-long cache and
bounded background Git workers; freshness of one filter does not establish
freshness of another filter's candidate set.
