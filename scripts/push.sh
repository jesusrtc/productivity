#!/usr/bin/env bash
# Push helper for the productivity monorepo and the content sub-repo.
#
# Usage:
#   scripts/push.sh productivity   # thin `git push`; fails if working tree dirty
#   scripts/push.sh content        # `git add -A`, build commit, push
#   scripts/push.sh both           # productivity then content
#
# Both repos push to `origin main`. Worktrees under content/projects/*/worktrees
# are already gitignored, so `git add -A` in content won't include them.
#
# Output: human-readable status lines on stdout, errors on stderr. Exit 0 on
# success, non-zero on any failure. The FastAPI endpoints reuse this script.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTENT="$ROOT/content"

push_productivity() {
    if ! git -C "$ROOT" diff --quiet || ! git -C "$ROOT" diff --cached --quiet; then
        echo "productivity: working tree is dirty. Commit changes before pushing." >&2
        return 1
    fi
    local out
    out=$(git -C "$ROOT" push origin main 2>&1) || {
        echo "productivity: push failed" >&2
        echo "$out" >&2
        return 1
    }
    if echo "$out" | grep -q "Everything up-to-date"; then
        echo "productivity: up to date"
    else
        local sha
        sha=$(git -C "$ROOT" rev-parse --short HEAD)
        echo "productivity: pushed (HEAD $sha)"
    fi
}

# Group `git status --porcelain` output of the content repo into a commit
# body. Compatible with bash 3.2 (no associative arrays) — uses
# newline-separated lists and dedupes via grep.
build_content_commit_message() {
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M')
    local porcelain
    porcelain=$(git -C "$CONTENT" status --porcelain)

    local modified="" added="" deleted="" other=""

    while IFS= read -r line; do
        [ -z "$line" ] && continue
        local code="${line:0:2}"
        local path="${line:3}"
        # Handle rename/copy: "R  old -> new" — take the new path.
        if echo "$path" | grep -q " -> "; then
            path="${path##* -> }"
        fi
        # Group by top-level project under projects/. For other paths, group
        # by the first path segment (e.g. wikis, meetings).
        local key
        if [ "${path#projects/}" != "$path" ]; then
            key=$(echo "$path" | cut -d/ -f2)
        else
            key=$(echo "$path" | cut -d/ -f1)
        fi
        case "$code" in
            "A "|"AM"|"??")
                if ! echo "$added" | grep -qx "$key"; then
                    added="${added}${key}"$'\n'
                fi
                ;;
            "D "|" D")
                if ! echo "$deleted" | grep -qx "$key"; then
                    deleted="${deleted}${key}"$'\n'
                fi
                ;;
            "M "|" M"|"MM")
                if ! echo "$modified" | grep -qx "$key"; then
                    modified="${modified}${key}"$'\n'
                fi
                ;;
            *)
                if ! echo "$other" | grep -qx "$key"; then
                    other="${other}${key}"$'\n'
                fi
                ;;
        esac
    done <<< "$porcelain"

    join_list() {
        # Newline-list -> "a, b, c"
        echo "$1" | sed '/^$/d' | paste -sd, - | sed 's/,/, /g'
    }

    local body=""
    [ -n "$modified" ] && body="${body}Modified: $(join_list "$modified")"$'\n'
    [ -n "$added" ]    && body="${body}Added: $(join_list "$added")"$'\n'
    [ -n "$deleted" ]  && body="${body}Deleted: $(join_list "$deleted")"$'\n'
    [ -n "$other" ]    && body="${body}Other: $(join_list "$other")"$'\n'

    printf 'Sync content %s\n' "$timestamp"
    if [ -n "$body" ]; then
        printf '\n%s' "$body"
    fi
}

push_content() {
    git -C "$CONTENT" add -A
    if git -C "$CONTENT" diff --cached --quiet; then
        # Nothing to commit — push in case prior commits weren't pushed.
        local out
        out=$(git -C "$CONTENT" push origin main 2>&1) || {
            echo "content: push failed" >&2
            echo "$out" >&2
            return 1
        }
        if echo "$out" | grep -q "Everything up-to-date"; then
            echo "content: nothing to commit, up to date"
        else
            local sha
            sha=$(git -C "$CONTENT" rev-parse --short HEAD)
            echo "content: nothing to commit, pushed prior commits (HEAD $sha)"
        fi
        return 0
    fi

    local msg
    msg=$(build_content_commit_message)
    git -C "$CONTENT" commit -m "$msg" >/dev/null
    local sha
    sha=$(git -C "$CONTENT" rev-parse --short HEAD)
    local out
    out=$(git -C "$CONTENT" push origin main 2>&1) || {
        echo "content: commit $sha created but push failed" >&2
        echo "$out" >&2
        return 1
    }
    echo "content: committed $sha and pushed"
}

case "${1:-}" in
    productivity) push_productivity ;;
    content) push_content ;;
    both) push_productivity && push_content ;;
    *) echo "usage: $0 {productivity|content|both}" >&2; exit 2 ;;
esac
