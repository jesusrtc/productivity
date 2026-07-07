# Workspace projects use the Makefile dev-server standard

Every current and future workspace project that runs a local dev server opts
into dashboard management with a root `Makefile`: `server-start` (foreground,
launched inside a tmux session), optional `server-stop` (best-effort stray
cleanup), `SERVER_PORT`, and optionally `SERVER_HEALTH_URL` (defaults to
`GET http://127.0.0.1:<SERVER_PORT>/`). Prefer a real `/healthz` route when
the server is ours to edit — cheap, early in the request handler, no disk
access. Full contract: `docs/SERVERS.md`. The dashboard discovers any project
with this Makefile automatically and shows start/stop controls + live health.

Port assignments so far:

- `8001` — resume (`local` workspace)
- `8002` — programming (`local` workspace)
- `8003` — type-and-recall (`local` workspace)
- `8005` — jaquemate (`productivity`/ssd workspace)
- `8006` — remotion (`productivity`/ssd workspace)

`remotion-manim` deliberately has **no** server — Remotion Studio was removed
2026-06-10 (render-only workflow; see `remotion-render-only-no-studio.md`),
and its Makefile ran `npx remotion studio`. Don't re-add a server-start target
there unless the user explicitly asks for Studio back.

Gotcha found while wiring this up: Vite's default `localhost` bind can
resolve to IPv6-only (`::1`) on macOS, which fails the dashboard's default
IPv4 health check (`127.0.0.1`) even though the server is up. If a project's
`server-start` runs Vite, set `server.host: "127.0.0.1"` in `vite.config.ts`
so the default health check works without a custom `SERVER_HEALTH_URL`.
