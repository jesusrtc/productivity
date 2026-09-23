# Provider idle events must not invent or erase activity

Checked against saved Claude and Copilot transcripts on 2026-09-22:
Claude records local commands such as /usage and their caveats as user messages.
Ignore local-command/command-name wrappers, isMeta entries, and compaction
summaries when detecting new work. A custom slash command that runs an agent
still emits assistant activity. User interruption markers stop working state.

Copilot appends session.shutdown after a completed response. Preserve an already
verified completion through shutdown so a polling interval cannot miss it.
Shutdown without a verified completion must never create a green dot. Keep
requiring a non-tool text response followed by its matching assistant.turn_end.
