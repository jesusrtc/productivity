# Codex launches use explicit sandbox and approval options

Codex CLI 0.155.1 rejects `--full-auto` in interactive mode. This made the
Garmin Codex/Pixel/Mickey tabs exit immediately while Lab repeatedly restored
them. Keep the shared Codex autopilot flags as `--sandbox workspace-write
--ask-for-approval on-request`, preserving the previous sandbox and approval
behavior for workspace and document terminals. The backend imports these
settings, so restart Lab after changing them. Check the actual installed CLI
as well as docs when diagnosing option compatibility.
