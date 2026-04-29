# productivity

A tiny git-over-HTTP push service. You commit locally, run `g push`, and
the server materializes a working copy at a configured path on the remote.

## Layout

```
productivity/
├── cli/g           the client CLI ("g push")
├── server/         HTTP server (listens on 127.0.0.1:4000)
├── Makefile        start/stop/install targets
└── repos/          pushed repos land here as subfolders
    └── <name>/     a real (non-bare) git working tree
```

## How it works

1. `g push` is run from inside any local git working tree.
2. It looks up the repo name in `REPOS` (top of `cli/g`) to find
   `remote_path` — the absolute path on the remote where the working
   tree should live.
3. It asks the server for its current head, builds a git bundle of
   *only the new commits*, and POSTs it.
4. The server fast-forwards the branch and `git reset --hard`s the
   working tree, so the on-disk folder always reflects the latest push.

Identification: the server keys repos by **name in the URL** plus the
**path** the client provides. First push for a path with no `.git`
auto-`git init`s it.

---

## Setup on the remote (one-time)

```bash
git clone git@github.com:jesusrtc/productivity.git ~/productivity
cd ~/productivity
make startbg                       # server on 127.0.0.1:4000, log -> server.log
make status                        # confirm it's up
```

Pushed repos will materialize under `~/productivity/repos/<name>/`.

## Setup on your laptop (one-time)

```bash
git clone git@github.com:jesusrtc/productivity.git ~/productivity
cd ~/productivity
make install                       # symlinks ~/.local/bin/g -> cli/g
```

Make sure `~/.local/bin` is on your PATH. Edit `cli/g` and add an entry
to `REPOS` for each project you want to push, e.g.:

```python
REPOS = {
    "productivity": {"remote_path": "~/productivity/repos/productivity"},
    "myproject":    {"remote_path": "~/productivity/repos/myproject"},
}
```

## Daily flow

In one terminal, forward port 4000 over SSH:

```bash
ssh -L 4000:127.0.0.1:4000 remote-host
```

In another terminal, from inside any local git working tree:

```bash
g list                             # show configured repos
g push                             # push current branch from $PWD
```

`g push` defaults the repo name to the basename of `git rev-parse
--show-toplevel` and the branch to the current branch. Override with
`--name`, `--branch`, or `--path` (per-push override of `remote_path`).

## Make targets

| target            | what                                         |
|-------------------|----------------------------------------------|
| `make start`      | run server in foreground (Ctrl-C to stop)    |
| `make startbg`    | run server detached, pid in `server.pid`     |
| `make stop`       | stop the server                              |
| `make status`     | what's listening on `:4000`                  |
| `make logs`       | `tail -f` `server.log`                       |
| `make install`    | symlink `g` into `~/.local/bin`              |
| `make uninstall`  | remove that symlink                          |

## API

Open `http://127.0.0.1:4000/` in a browser for an HTML index, or
`curl localhost:4000/` for JSON.

| method | path                       | purpose                        |
|--------|----------------------------|--------------------------------|
| GET    | `/`                        | endpoint index                 |
| GET    | `/health`                  | liveness probe                 |
| GET    | `/repos`                   | list known repos               |
| GET    | `/repos/<name>/head`       | current sha of `<branch>`      |
| POST   | `/repos/<name>/push`       | apply a git bundle             |

Both `head` and `push` accept `?branch=…` and `?path=…` (absolute, `~`
expanded). Push body is the git bundle bytes.

## Limits (v1)

- Push only — no `pull`/`fetch`/`clone`/multi-branch sync.
- Fast-forward only.
- No auth — only run with `HOST=127.0.0.1` and reach it via SSH tunnel.
- Server's working tree is wiped to match each push (`reset --hard`);
  don't edit files there by hand.
