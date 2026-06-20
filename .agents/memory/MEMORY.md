# Memory index

- [Lab UI runs as installed Chrome PWA](lab-ui-runs-as-installed-chrome-pwa.md) — same-origin `window.open` is frameless (no URL bar); prefer cross-origin/direct URLs for pop-outs
- [Cover letters: no weaknesses](feedback-cover-letter-no-weaknesses.md) — in CV project, keep gaps in fit.md only; close on strengths, never name missing skills
- [Console communication: be plain](console-communication-be-plain.md) — plain, short, jargon-free console messages; user dislikes dense technical recaps
- [Terminal latency invariants](terminal-latency-invariants.md) — term.py endpoints stay sync `def`; UI libs vendored (no CDN); WebGL on active terminal only
- [Index route stays async for latency](index-route-async-for-latency.md) — cached `/` must avoid the sync worker pool so tmux polling cannot delay page loads
- [Lab proxy injects base href](lab-proxy-injects-base-href.md) — static sites viewed via `/api/proxy/...` need `<base target="_self">` in every page or subdirectory links/assets break
- [Remotion: render-only, no Studio](remotion-render-only-no-studio.md) — user removed Remotion Studio (2026-06-10); videos are reviewed by rendering mp4/stills to `out/`, don't reintroduce the Studio or proxy hacks
- [ElevenLabs expressive settings gotcha](elevenlabs-expressive-settings-gotcha.md) — don't force stability/style on designed/cloned voices; check sidecar pacing (words >1s, gaps >0.8s) before building beats
