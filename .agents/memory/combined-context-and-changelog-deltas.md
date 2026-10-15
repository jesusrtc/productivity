# Combined context and per-terminal changelog differences

The user wants one Lab context document in META combining the complete agent
guide and canonical user guide. Remove the separate user-guide META row; retain
the full changelog reader. `lab context llm` prints that same combined context
with owning paths, plus only the changelog diff from its own tmux session's last
acknowledged version. It always prints full instructions on startup/recovery.

Store framework changelog snapshots by numeric context version in
$LAB_HOME/state/agent-context. After successful stdout flush and snapshot write,
advance @lab_context_version. Preserve this baseline across agent launches;
do not reset it or trust an inherited environment variable for acknowledgement.
Unchanged updates stay silent. With no earlier snapshot, explicitly establish a
baseline instead of inventing a diff or replaying the full historical log.
This supersedes full-changelog output and launch-reset versions in
one-command-llm-context-bootstrap.md. Keep USER-GUIDE.md and CHANGELOG.md as the
canonical packaged sources, and render the combined document from them.
