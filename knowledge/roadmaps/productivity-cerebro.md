---
title: "Roadmap: Productivity Cerebro"
date: 2026-04-03
type: roadmap
scope: personal
projects: [cerebro]
tags: [roadmap, cerebro, sessions, tracked-projects, claude-code, hooks]
---

# Roadmap: Productivity Cerebro

## 1. Claude Code workflows in cerebro with symlinks to ~/.claude

Move all Claude Code workflow files (tracker.sh, tracked-projects, statusline, hooks) into cerebro. `make install` creates symlinks into `~/.claude/`. Single source of truth in the repo, `~/.claude` is just symlinks.

- Check latest commits in `~/.claude` for tracker.sh and tracked-projects fixes
- Define what lives where (cerebro vs apps)
- Install command that wires everything up

## 2. Claude Code rules in cerebro, symlinked to ~/.claude/rules/

Rules like `pre-commit-workflow.md`, `captain.md`, `tracked-projects.md` should live in cerebro and be symlinked to `~/.claude/rules/`. Single source of truth, versioned in git. Part of the `make install` step from item 1.

## 3. Session/objective tracking (needs brainstorming)

Replace or evolve tracked-projects into a more flexible "session" concept:

**Problems with current approach:**
- Tied to git branch per repo — doesn't cover non-branch work (RFCs, one-pagers, research)
- No multi-repo support — one project may span multiple repos
- No way to have multiple concurrent sessions in the same folder

**Ideas to explore:**
- Abstract "session" concept decoupled from git branches
- A session has: objectives, status, notes, related repos/branches/PRs
- Sessions live in cerebro (not `.claude/tracked-projects/`)
- gdiff or mdview renders session status in the web UI
- Folder-level sessions: a folder can have multiple active sessions
- Multi-repo sessions: one session can track changes across N repos

**Open questions:**
- What triggers session creation? Manual? Auto on branch creation?
- How to associate a session with repos/folders without being rigid?
- Where does session state live? YAML in cerebro? A dedicated folder?
- How to display in web UI? Sidebar in gdiff? Separate dashboard?

## 4. Render session status in web UI

Instead of terminal-only display (gdiff.sh `render_tracking`), show session objectives, status, and progress in mdview or gdiff web UI. Plan/checklist items rendered as interactive checkboxes.

## 5. Enforce cerebro logging via Claude Code hooks

All todos, completed tasks, and session progress must be documented in cerebro. Potential approach:

- **Claude Code hook** (post-tool or custom event) that calls a `cerebro-cli` to read current session state and update cerebro with what was done
- Example flow: after `mint build` succeeds → `cerebro-cli read` (get current session context) → `cerebro-cli update` (log what was accomplished)
- Could be a hook in `settings.json` or a wrapper script
- The hook ensures nothing falls through the cracks — cerebro is always up to date

**Open questions:**
- What's the right hook point? Post-commit? Post-build? Post-session?
- Does cerebro-cli need to be a real CLI or just a shell script?
- How granular? Log every task? Or just session summaries?
- How to avoid noise — only log meaningful progress, not every small action

## 6. Cerebro auto-save mode

Periodic automatic git add + commit + push for cerebro so content is never lost:

- `git add -A && git commit -m "snapshot" && git push` every ~6 hours
- Installable via `cd cerebro && make install` (sets up cron/launchd)
- Could be a launchd plist, cron job, or part of `make start`
- Only runs if there are changes (no empty commits)
- Commit message could include timestamp or summary of changed files

---

## Priority Order

1. Claude Code workflows → cerebro + symlinks (includes item 2)
2. Session concept brainstorming + design
3. Web UI for session/objective tracking
4. Cerebro logging enforcement via hooks (depends on 2)
5. Cerebro auto-save
