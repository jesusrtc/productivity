# Client server port comes from .env

The persistent Lab server port for a framework checkout is `LAB_PORT` in its
root `.env`. Keep `.env.example` tracked as the client-editable template and
keep `.env` ignored so each installation can choose its own port. If `.env`
does not define a valid port, fall back to active workspace `lab.toml`
`[server].port`, then `3333`.

`make start PORT=NNNN` and `lab start --port NNNN` remain one-run overrides.
Do not treat ambient `LAB_PORT` as a Make input: Lab terminal processes inherit
the currently running server's `LAB_PORT`, and using it would silently defeat a
new persistent setting. Make reads the file through `scripts/lab-url.sh`, then
exports its resolved port as `LAB_PORT` to the server. The live port remains at
`.lab/state/server.port` and is resolved with `scripts/lab-url.sh`.
