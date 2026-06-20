---
name: asta-development
description: >-
  End-to-end workflow for developing a new ASTA (anti-abuse short-term
  action) rule in linkedin-multiproduct/abuse-short-term-action — from
  scaffolding through rdev testing through PR-comment iteration. Pairs
  with one-pager-asta (which writes the design doc) and
  code-asta-monitoring (which monitors the rule once it's running).
  Trigger when the user says "build a new ASTA", "ship the ASTA",
  "revamp ASTA <name>", "create the short-term-action rule for X",
  "let's wire up <rule>", or similar.
---

# asta-development

Three phases: build, rdev test, iterate. The rdev hacks (comment out
every other subjob + set `lixKey = None`) are isolated via `git stash`
so they never end up in a prod commit. A fourth phase (Phase 4) retires
the predecessor in a separate PR after ramp.

Reference: `content/wikis/linkedin/asta-development.md`.

## Phase 0 — ask first (single message, then wait)

Before writing any code, get the user to commit to these in one short
message:

1. **Schedule cadence** — bihourly or daily? Most ASTAs are bihourly
   (`runFrequency = AutomatedCleanupSubjob.BIHOURLY`). Daily is rarer
   and usually means a heavier window. Confirm.
2. **Rule name** — Scala class, cleanup-subjob registration, TRex
   namespace, model name. One stem, four surface formats that all
   need to agree.
3. **Source tables** — list every table the SQL touches. Warn loudly
   when the list contains:
   - `tracking.csaudit` — multi-TB, costly scans.
   - `tracking.userrequestevent` — also huge.
4. **Action + label** — `TAZER_LOGIN_RESTRICT` + `FAKE` is the common
   default; ATO rules use different labels.
5. **Predecessor rule (revamp)?** — if yes, plan the eventual
   retirement as a follow-up PR. Do **not** delete the old rule in
   the same PR.

## Phase 1 — build

Cut a worktree, write code + tests, wire the registry, push.

```bash
# One worktree per PR.
cd /Users/jcortes/src/productivity/repositories/abuse-short-term-action
git fetch origin master
git worktree add \
  /Users/jcortes/src/productivity/projects/<proj>/worktrees/asta-<slug> \
  -b jcortes/<slug> origin/master
```

### Cleanup-subjob constructor

```scala
val cleanupSubjob = new AutomatedCleanupSubjob[SecurityAccountActionMessage](
  "ASTAYourRuleCleanupSubjob",              // registration name
  query, dataReader, SecurityAccountActionAdapter,
  5000,                                     // batch size
  "YYYY-MM-DD-00",                          // onboarding date
  "YYYY-MM-DD-00",                          // expiry — must be < 8 months past onboarding
  "<go/design-doc URL>",
  "jcortes",
  Some("asta.your_rule"),                   // lixKey — keep Some(...) for prod
  runFrequency = AutomatedCleanupSubjob.BIHOURLY
)
```

The 8-month expiry cap is enforced by the framework. Default to a
6-month window; extend with a follow-up PR if needed.

### Wire the new subjob into the registry

Insert `YourRule.cleanupSubjob,` alphabetically into `automatedCleanupSubjobs` in `incident-response-short-term-action/.../cleanupsubjobs/AutomatedCleanupSubjobs.scala`.

### Build + push + open the PR

```bash
./gradlew --stop                                      # clear stale daemons
mint build > /tmp/mint.log 2>&1                       # never pipe through tail — it eats the exit code
git push -u origin jcortes/<slug>
```

Then use the `linkedin-dev-workflow:submit` skill to open the PR with
the repo template (`## Testing Done`, not Claude Code's default
`## Test plan`).

## Phase 2 — rdev test

Goal: make the Airflow rdev run **only** this new ASTA so its output
is observable without noise from the rest of the registry.

Two surgical changes, kept un-committed and stash-safe:

1. In `AutomatedCleanupSubjobs.scala`, comment out every entry except
   `YourRule.cleanupSubjob,`. Keep the alphabetical layout so the
   diff reads cleanly when re-applied.
2. In `YourRule.scala`, change `Some("asta.your_rule")` → `None` so
   the rule runs at 100 % in the rdev.

Build + release, then hand off:

```bash
mint build && mint release
```

**The user runs the picli commands themselves.** `picli test create`
and `picli test login` trigger Okta SSO / MFA flows that need a real
TTY (interactive iTerm). Automating via tmux
(`linkedin-cli-tools:interactive-cli`) works in a pinch but routinely
times out the lab server's 60 s authn-cli subprocess if MFA isn't
answered immediately. Surface the instructions and let the user
drive — do not script the auth flow.

Print these verbatim for the user and stop:

```bash
# Create a new rdev on master, e.g. abuse-short-term-action/jcortes
picli test create --name jcortes --branch master

# SSH and launch the webserver — keep this terminal open
picli test login abuse-short-term-action/jcortes --method ssh

# In a second local terminal (the worktree, with rdev hacks applied):
mint build && mint release
picli test upload abuse-short-term-action/jcortes
```

Wait for the user to confirm the rdev is up and the upload landed.
Once they're in the Airflow UI at the rdev's direct URL (the login
command prints it), they trigger the DAG and report back. Reference:
`projects/<proj>/docs/testing-in-airflow.md` if it exists.

## Phase 3 — iterate on PR comments

Reviewers post comments. Don't trash the rdev hacks — stash them.

```bash
# Save the rdev hacks so the working tree goes back to clean prod state.
git stash push -m "rdev-hacks" -- \
  incident-response-short-term-action/src/main/scala/com/linkedin/abuse/shorttermaction/cleanupsubjobs/AutomatedCleanupSubjobs.scala \
  incident-response-short-term-action/src/main/scala/com/linkedin/abuse/shorttermaction/cleanupsubjobs/YourRule.scala

# Address review comments on a clean tree.
$EDITOR <files>
mint build > /tmp/mint.log 2>&1                # green before commit
git add <changed-files>
git commit -m "Address PR comments: ..."
git push

# Update the PR description if behavior / scope changed.
gh pr edit <pr-number> --body "$(cat <<'EOF'
... refreshed body ...
EOF
)"

# Re-apply the rdev hacks for another round of Airflow testing.
git stash pop                                  # or `git stash apply` to keep the entry
mint build && mint release
picli test upload abuse-short-term-action/jcortes
```

Always re-stash before the next commit. The `git stash pop` / `apply`
pattern is the safety rail that keeps `lixKey = None` and the
commented-out registry out of every prod commit.

### If the stash is lost

Canonical rdev-hack content:

- `AutomatedCleanupSubjobs.scala` — every entry `// `-commented except
  `YourRule.cleanupSubjob,`. Keep a file-header comment
  `// LOCAL RDEV ISOLATION — DO NOT COMMIT` so a casual `git diff`
  reader can't miss it.
- `YourRule.scala` — `Some("asta.your_rule")` → `None`, with a
  `// LOCAL RDEV ISOLATION — DO NOT COMMIT` line on top.

## Phase 4 — retirement (revamp follow-up)

After the new ASTA ramps to 100 % and runs cleanly for at least one
week, retire the predecessor as a **separate PR**:

- Delete `OldRule.scala` and `TestOldRule.scala`.
- Remove the predecessor's entry from `AutomatedCleanupSubjobs.scala`.
- Open a TRex change to ramp `asta.old_rule` to 0 %.
- Close the related Jira / one-pager artifact.

## Gotchas

- **Forgetting the registry entry.** New file lands, rule never
  fires, restriction tables empty for weeks. Always confirm
  `AutomatedCleanupSubjobs.scala` is in the PR diff.
- **`mint build | tail` eats the exit code.** The harness sees
  exit 0 from the pipeline even when the build failed. Run
  `mint build > /tmp/mint.log 2>&1` instead of
  `mint build 2>&1 | tail -120`.
- **Test-scala OOM on default 4 G heap.** Set
  `GRADLE_OPTS=-Xmx8g -XX:MaxMetaspaceSize=1g` before `mint`. Stop
  the daemon first with `./gradlew --stop` if it's been alive a
  while.
- **Lab-server `/api/nb/exec` timeout.** Default 210 s bootstrap +
  3600 s body cap was too tight before the 2026-05-21 fix; if you
  see `darwin timed out after 210s`, check
  `core/src/core/routes/nb_exec.py` has the bumped values
  (bootstrap 900 s, no upper bound on body).
- **picli prompts need a TTY.** Piping `yes |` into `picli` triggers
  `Inappropriate ioctl for device`. Use a real iTerm, or
  `linkedin-cli-tools:interactive-cli` (tmux) when automating.
- **8-month expiry cap.** Framework rejects `expirationData` more
  than 8 months past `onboardingDate` with a confusing
  `IllegalArgumentException: requirement failed: ...`. Keep the
  window at 6 months and renew via a follow-up extension PR.

## Related skills

- `one-pager-asta` — write the design doc before code (Phase 0 input).
- `code-asta-monitoring` — verify the rule is firing after Phase 2 /
  Phase 4 ramp via the inline notebook dashboard.
- `linkedin-dev-workflow:submit` — open the PR with the right repo
  template (don't use Claude Code's default `## Test plan`).
- `linkedin-cli-tools:interactive-cli` — when you need to automate
  picli or any other TTY-bound CLI.
