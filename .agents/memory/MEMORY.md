# Memory index

- [Lab UI runs as installed Chrome PWA](lab-ui-runs-as-installed-chrome-pwa.md) — same-origin `window.open` is frameless (no URL bar); prefer cross-origin/direct URLs for pop-outs
- [Cover letters: no weaknesses](feedback-cover-letter-no-weaknesses.md) — in CV project, keep gaps in fit.md only; close on strengths, never name missing skills
- [Console communication: be plain](console-communication-be-plain.md) — plain, short, jargon-free console messages; user dislikes dense technical recaps
- [Terminal latency invariants](terminal-latency-invariants.md) — term.py endpoints stay sync `def`; UI libs vendored (no CDN); WebGL on active terminal only
- [Index route stays async for latency](index-route-async-for-latency.md) — cached `/` must avoid the sync worker pool so tmux polling cannot delay page loads
- [Lab proxy injects base href](lab-proxy-injects-base-href.md) — static sites viewed via `/api/proxy/...` need `<base target="_self">` in every page or subdirectory links/assets break
- [Remotion: render-only, no Studio](remotion-render-only-no-studio.md) — user removed Remotion Studio (2026-06-10); videos are reviewed by rendering mp4/stills to `out/`, don't reintroduce the Studio or proxy hacks
- [ElevenLabs expressive settings gotcha](elevenlabs-expressive-settings-gotcha.md) — don't force stability/style on designed/cloned voices; check sidecar pacing (words >1s, gaps >0.8s) before building beats
- [Claude memory uses repo path](claude-memory-auto-directory.md) — prefer `autoMemoryDirectory` in ignored `.claude/settings.local.json`; keep `~/.claude/projects/.../memory` symlink only as fallback
- [Lab framework CLI layout](lab-framework-core-cli-layout.md) — keep the installable `lab` CLI as its own package under `core/cli/`; reserve framework `apps/` for workspace/client apps, not core internals
- [Core tests: unset LAB_WORKSPACE](core-tests-unset-lab-workspace.md) — a shell-exported `LAB_WORKSPACE` overrides test fixtures' `LAB_ROOT`; run `env -u LAB_WORKSPACE .venv/bin/python -m pytest`; the watcher debounce test flakes under load
- [Workspace projects use the Makefile dev-server standard](project-servers-make-standard.md) — `make server-start`/`server-stop` + `SERVER_PORT` (+ `/healthz` where ours); port map so far; `remotion-manim` has no server on purpose; Vite needs `server.host: "127.0.0.1"` or the default IPv4 health check fails
- [Terminal wheel scrolling routes to the app](lab-terminal-wheel-scroll-routing.md) — WheelUpPane must pass through when `mouse_any_flag` (claude scrolls its own transcript); copy-mode `-e` line-scroll otherwise; never arrow keys, never unconditional copy-mode
- [Terminal WS half-open after tmux attach dies](terminal-ws-half-open-after-tmux-attach-dies.md) — server doesn't close the WS on PTY EOF; frontend's 8s poll + auto-restore covers it (detection lag ≤8s)
- [Sidebar file rows have five render sites](sidebar-file-rows-have-five-render-sites.md) — icons/decorations must be applied at all five (project sidebar, meta rows, shared tree, self view, repo-tab tree); git-status containment = workspace ∪ registered repos ∪ framework root
- [Headless UI check misses launch-agent server](check-ui-launch-agent-process-detection.md) — `scripts/check-ui.sh`'s relative Python `pgrep` pattern does not match the Homebrew-Python launch-agent command; it may try to start a duplicate server
