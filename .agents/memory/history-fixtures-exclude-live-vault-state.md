# Git history fixtures exclude live vault state

Git history fixtures need their own repository beneath the test vault.
Committing the vault itself includes live .lab logs/index files, so a staged-only
rename test can spuriously observe unrelated unstaged writes. Keep the special
rename/source-path assertion and isolate the repository instead of broadening its
expected working-tree states.
