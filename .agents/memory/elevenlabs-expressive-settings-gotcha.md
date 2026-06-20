---
name: elevenlabs-expressive-settings-gotcha
description: Forcing stability/style on ElevenLabs designed/cloned voices breaks pacing — verify timings before building video beats
metadata:
  node_type: memory
  type: project
  originSessionId: 08130d80-b355-4300-8a9c-483b3d03e665
---

In the remotion project, `gen_audio.py --stability 0.35 --style 0.55` works well
with the professional narrator voice BRIAN (XgQWNZcJ8SRkxXwwhPTo) but broke the
designed voice "Jesus - Medium Prompt" (R2rxyBI0SWhoPwq16ESH): words stretched
to ~2 s and multi-second pauses, which wrecked the whole kinetic-typography
video synced to those timings (2026-06-10).

**Why:** style exaggeration + low stability on voice-design/cloned voices is
unstable in eleven_multilingual_v2; professional voices tolerate it.

**How to apply:** with non-professional voices use the voice's default settings
(no flags). Always check pacing from the `.mp3.json` sidecar before building
beats: flag words with `end-start > 1s` and gaps `> 0.8s`; regenerate if several
appear. Good narrator voices in the account: BRIAN (es-LatAm, punchy), Juan
Carlos RyfjEHnKbtma4Srae2za (es-LatAm, deep/cosmic).
