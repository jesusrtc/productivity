# productivity

A tiny git-over-HTTP push service. You commit locally, run `g push`, and
the server materializes a working copy under its `repos/` folder.

## Layout (on the remote)

```
productivity/
├── cli/g           the client CLI (also lives on your laptop)
├── server/         HTTP server (listens on 127.0.0.1:4000)
├── Makefile        start/stop targets
└── repos/          pushed repos land here as subfolders
    └── <name>/     a real (non-bare) git working tree
```

## How it works

1. `g push` is run from inside any local git working tree.
2. It derives the repo name from `git rev-parse --show-toplevel` (or
   `--name X`), asks the server for its current head, and builds a git
   bundle of *only the new commits* on the current branch.
3. The server fast-forwards the branch under `$REPO_ROOT/<name>` and
   `git reset --hard`s the working tree.

Identification: the server looks at `$REPO_ROOT/<name>`. If there's no
`.git` there, it `git init`s the folder — that's how a "new repo" is
created on first push. Subsequent pushes update the same folder.

`$REPO_ROOT` defaults to `$(pwd)/repos` (so `~/productivity/repos/` when
the server is started from the cloned tooling folder).

---

## Setup on the remote (one-time)

```bash
git clone git@github.com:jesusrtc/productivity.git ~/productivity
cd ~/productivity
make startbg                     # server on 127.0.0.1:4000, log -> server.log
make status                      # confirm it's up
```

That's it. Pushed repos will materialize under
`~/productivity/repos/<name>/`. The server has no per-repo config — name
in the URL is enough.

## Setup on your laptop (one-time)

Put the CLI somewhere on your machine and alias it. For example, in
`~/.zprofile`:

```bash
alias g='python3 ~/path/to/productivity/cli/g'
```

(Or copy `cli/g` into a folder on your `PATH` and `chmod +x`.)

Then in another terminal forward port 4000 over SSH so the local
`localhost:4000` reaches the remote's server:

```bash
ssh -L 4000:127.0.0.1:4000 remote-host
```

Set `REPO_SERVER` if your server isn't at the default
`http://127.0.0.1:4000`.

## Daily flow

From inside any local git working tree:

```bash
g push                           # push current branch to <basename> on the server
g push --name foo                # override the repo name
g push --branch dev              # override the branch
g list                           # list repos the server has
```

On the remote, the working tree at `~/productivity/repos/<name>/` always
mirrors the latest pushed commit. You can `cd` in and `git log` / `git
diff` to inspect, but **don't edit it** — every push does `git reset --hard`.

### Auto-fan-out to GitHub (or any remote)

After a successful apply, the server runs `git push origin <branch>` if
the repo has an `origin` remote configured. So one `g push` from your
laptop propagates to GitHub automatically.

To enable it for a repo, on the **remote** machine, after the first
`g push` has materialized the folder:

```bash
cd ~/productivity/repos/<name>
git remote add origin git@github.com:you/<name>.git
git push -u origin <branch>     # first time, sets tracking
```

After that, every `g push` from your laptop fans out to GitHub. The CLI
prints `g: origin ok -> <url>` (or `FAILED` with stderr) so you see what
happened.

Notes:
- The remote machine needs SSH access to push to GitHub (deploy key, or
  an SSH agent forwarded over your tunnel).
- If GitHub has commits the server doesn't, the auto-push will fail
  with non-fast-forward — that's reported but doesn't fail the apply.

## Make targets

| target          | what                                    |
|-----------------|-----------------------------------------|
| `make start`    | run server in foreground                |
| `make startbg`  | run server detached, pid in `server.pid`|
| `make stop`     | stop the server                         |
| `make status`   | what's listening on `:4000`             |
| `make logs`     | `tail -f` `server.log`                  |

## API

Open `http://127.0.0.1:4000/` in a browser for an HTML index, or
`curl localhost:4000/` for JSON.

| method | path                  | purpose                    |
|--------|-----------------------|----------------------------|
| GET    | `/`                   | endpoint index             |
| GET    | `/health`             | liveness probe             |
| GET    | `/repos`              | list known repos           |
| GET    | `/repos/<name>/head`  | current sha of `<branch>`  |
| POST   | `/repos/<name>/push`  | apply a git bundle         |

`head` and `push` accept `?branch=…`. `push` also accepts `?base=<sha>`
(the sha the client thinks the server is at — used to detect divergence)
and the body must be the git bundle bytes.

## Limits (v1)

- Push only — no `pull`/`fetch`/`clone`/multi-branch sync.
- Fast-forward only.
- No auth — bind to `127.0.0.1` and reach it via SSH tunnel.
- Server's working tree is wiped on each push (`reset --hard`).
