"""Build the GitHub issue body for a scan cycle that collected but could not push.

Kept out of lowno.yml deliberately: the body needs real JSON escaping, and a
heredoc nested inside a workflow's `run:` block is exactly the kind of quoting
that breaks silently months later (see CLAUDE.md #9 and the CRLF note in
.gitattributes).

Reads CYCLE and TITLE from the environment, writes the issue payload to stdout.
"""
import json
import os

cycle = os.environ.get("CYCLE", "?")
title = os.environ.get("TITLE", "scan pushes failing")
run = os.environ.get("GITHUB_RUN_ID", "?")
repo = os.environ.get("GITHUB_REPOSITORY", "mf4633/low-no")

body = (
    f"Cycle **{cycle}** of run "
    f"[{run}](https://github.com/{repo}/actions/runs/{run}) scanned "
    "successfully but could NOT be committed after 5 attempts.\n\n"
    "**Why this is its own alarm.** An uncommitted cycle leaves no timestamp "
    "anywhere, so the committed record cannot distinguish it from a cycle that "
    "never ran. That ambiguity is what made 2026-08-30 look like a scheduling "
    "problem: six cycles had in fact collected correctly, on time, straight "
    "through the eastern peak window, and were thrown away at the push. The "
    "run did not go red until five hours after the first rejection.\n\n"
    "**What to check.** Look for `conflict outside the regenerable set` in the "
    "run log -- that means the conflict was in a file "
    "`.github/push_retry.sh` deliberately refuses to auto-resolve, and it needs "
    "a human.\n\n"
    "**Recovering the data.** The loop keeps scanning, and a later cycle's "
    "successful push carries the earlier cycles' data with it, so this is "
    "usually self-healing. If the run ends with commits still unpushed they are "
    "preserved as a git bundle in the run's **unpushed-commits** artifact:\n\n"
    "```\n"
    "gh run download <run-id> -n unpushed-commits\n"
    "git fetch unpushed.bundle refs/heads/main:refs/remotes/rescue/main\n"
    "git log --oneline main..rescue/main\n"
    "```\n\n"
    "Reported by the scan loop over the REST API rather than via git, because "
    "git is what is broken when this fires."
)

print(json.dumps({"title": title, "labels": ["health"], "body": body}))
