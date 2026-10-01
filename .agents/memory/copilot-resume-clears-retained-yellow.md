# Copilot resume clears retained yellow

Verified with installed Copilot CLI 1.0.83 on 2026-10-01 using an offline local
provider, isolated CLI state, and owned disposable processes. A tool turn end
keeps yellow; a final text response plus matching turn end creates green, which
survives shutdown. Resuming after an abrupt stop emits `session.resume` and waits
for a new request. Mapping that event to unknown leaves browser-retained yellow
stuck. Emit an explicit interrupted state unless a final completion was already
verified; preserve its unread green. This also applies if the old start left the
bounded transcript tail. Native sanitized fixtures live under core/tests/fixtures.
