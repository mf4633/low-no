#!/usr/bin/env bash
# Commit-and-push that can SURVIVE a content conflict on a regenerable artifact.
#
# WHY THIS EXISTS -- 2026-08-30, the most expensive collection failure so far.
# The 16:16Z scan run started at 16:33 and scanned six cycles straight through
# the eastern peak window (16:33, 17:36, 18:38, 19:40, 20:42, 21:44). All six
# collected correctly. All six FAILED TO PUSH, and the whole day's peak-window
# coverage was thrown away -- 7 usable rate samples against a normal 84.
#
# The mechanism: the run checked out one commit behind the previous run's final
# push, so its own commit had to rebase, and conflicted on the whole-file
# snapshot artifacts (docs/active.json, docs/edge.json, docs/traps.json,
# logs/_kalshi_probe.json, logs/_ob_probe.json). The old loop's recovery was
# `git rebase --abort` then retry -- which restores the IDENTICAL state, so five
# retries produced five identical failures, and every later cycle in that run
# inherited the same doomed base. A run in that state burns its full 5.5 hours
# producing nothing and only fails at the very end.
#
# .gitattributes said a docs/*.json race is "repaired by the next cycle". That
# is false: it wedges the entire RUN, not one cycle.
#
# The fix is to resolve rather than abort. Every file in REGENERABLE is a
# deterministic regeneration from logs/ -- a fresh scan's version is strictly
# newer and always correct, so newest-wins is not a judgement call. Anything
# conflicting OUTSIDE that set is a real conflict and still aborts, because
# silently picking a side of a log or a source file is how observations vanish.
#
# NB: during a rebase the sides are inverted from intuition. --ours is upstream
# (already on main); --theirs is the commit being replayed (our fresh output).
#
# This file is SOURCED, so it deliberately sets no shell options -- `set -u` or
# `set -e` here would silently change the behaviour of the caller's loop.

# Whole-file snapshots regenerated from scratch every cycle. Deliberately does
# NOT include logs/*.jsonl -- those are append-only telemetry and carry
# merge=union in .gitattributes, which resolves them without ever reaching here.
REGENERABLE_RE='^(docs/[^/]*\.json|logs/_[^/]*\.json)$'

_in_rebase() {
  [ -d "$(git rev-parse --git-path rebase-merge)" ] ||
  [ -d "$(git rev-parse --git-path rebase-apply)" ]
}

# Resolve the current conflict set in favour of the replayed commit.
# Returns 1 if anything outside REGENERABLE is conflicted.
_resolve_regenerable() {
  local unmerged bad f
  unmerged=$(git diff --name-only --diff-filter=U)
  [ -z "$unmerged" ] && return 0
  bad=$(printf '%s\n' "$unmerged" | grep -Ev "$REGENERABLE_RE" || true)
  if [ -n "$bad" ]; then
    echo "conflict outside the regenerable set -- not auto-resolving:"
    printf '%s\n' "$bad" | sed 's/^/    /'
    return 1
  fi
  printf '%s\n' "$unmerged" | while IFS= read -r f; do
    [ -z "$f" ] && continue
    # --theirs = the commit being replayed = this cycle's fresh output.
    # If it was deleted on that side, --theirs fails and dropping it is right.
    git checkout --theirs -- "$f" 2>/dev/null || git rm -q -f -- "$f" 2>/dev/null || true
  done
  git add -A
  echo "    resolved $(printf '%s\n' "$unmerged" | wc -l) regenerable file(s), newest wins"
  return 0
}

# Drive a conflicted rebase to completion. A rebase can stop on EACH replayed
# commit, so this loops rather than continuing once.
_finish_rebase() {
  local guard=0
  while _in_rebase; do
    guard=$((guard + 1))
    if [ "$guard" -gt 20 ]; then
      echo "    rebase still unfinished after 20 steps, giving up"
      return 1
    fi
    _resolve_regenerable || return 1
    if ! GIT_EDITOR=true git rebase --continue; then
      # --continue can also exit non-zero simply because the step became empty.
      if _in_rebase; then continue; fi
      return 1
    fi
  done
  return 0
}

# push_retry "<commit message>"
# Returns 0 if there was nothing to commit or the push landed; 1 otherwise.
push_retry() {
  local msg="${1:?push_retry needs a commit message}" attempt
  git add -A
  if git diff --cached --quiet; then
    echo "nothing to commit"
    return 0
  fi
  git commit -q -m "$msg"

  for attempt in 1 2 3 4 5; do
    if git pull --rebase --autostash && git push; then
      if [ "$attempt" -gt 1 ]; then echo "pushed on attempt $attempt"; fi
      return 0
    fi
    if _in_rebase; then
      if _finish_rebase && git push; then
        echo "resolved a conflict on regenerable artifacts and pushed"
        return 0
      fi
      if git rebase --abort 2>/dev/null; then echo "    aborted an unresolvable rebase"; fi
    fi
    echo "push attempt $attempt lost a race, retrying"
    sleep $((attempt * 7))
  done

  echo "::error::could not push after 5 attempts -- this cycle's data is NOT committed"
  return 1
}
