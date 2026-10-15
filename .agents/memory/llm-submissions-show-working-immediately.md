# LLM submissions show working immediately

On October 15, 2026 the user added an explicit-input exception to agent-only
terminal status: submitting a message to an LLM-controlled terminal must turn
its dot yellow immediately. When answering red, show `Working - responded
{response}` until the agent reports its actual WIP text. Other messages use
`Working - submitted {message}`. No inference from output or silence, and no
second badge/dot. Clicking yellow/red does not clear them; only green clears.

Lab launches mark the session LLM-controlled; manually started agents use
`lab terminal llm`, and normal process discovery recognizes supported local
providers. `lab terminal llm --off` returns to shell behavior. Markers are
session-local and exact-pane/socket scoped. Temporary submitted-input feedback
is browser-local, shared across windows and replaced by a newer agent report.
Pasted multiline drafts must not submit early, and ordinary shells stay unaffected.
