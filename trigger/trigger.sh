#!/bin/sh
# Runs on a Fly scheduled Machine, hourly. Fires GitHub workflows that GitHub's
# own scheduler keeps failing to deliver (5/11 fires 2026-08-26, 0/14 on
# 2026-08-27, 0/3 scorecard slots on 2026-08-28).
#
# Independent of the in-repo chain on purpose: the chain cannot restart itself
# if it ever breaks outside the cron window. This can, from outside.
#
# Extra dispatches are harmless -- the scan's concurrency group serialises and
# keeps at most one run pending, and score_run skips days already settled.
R=mf4633/low-no
H=$(date -u +%H)

if [ -z "$DISPATCH_PAT" ]; then
  echo "DISPATCH_PAT unset - cannot dispatch"
  exit 1
fi

FAIL=0

dispatch() {
  echo "dispatching $1 at ${H}Z"
  # Check the HTTP STATUS, do not trust curl's exit code: `curl -sS` exits 0
  # on a 403 because it received a valid response. Observed 2026-08-28 -- a
  # token missing Actions:write 403'd every hourly fire while the Machine
  # reported "exited normally with code: 0". A trigger that cannot dispatch
  # must look broken, not healthy (CLAUDE.md #9).
  code=$(curl -sS -o /tmp/resp -w "%{http_code}" -X POST \
    -H "Authorization: Bearer $DISPATCH_PAT" \
    -H "Accept: application/vnd.github+json" \
    "https://api.github.com/repos/$R/actions/workflows/$1/dispatches" \
    -d "{\"ref\":\"main\"}")
  if [ "$code" = "204" ]; then
    echo "  $1 dispatched (204)"
  else
    echo "  FAILED: $1 returned HTTP $code"
    cat /tmp/resp
    echo
    FAIL=1
  fi
}

# Case rather than arithmetic: busybox sh treats 08/09 as invalid octal in
# some contexts, and the hour is exactly where that would bite.
case "$H" in
  11|12|13|14|15|16|17|18|19|20|21|22|23) dispatch lowno.yml ;;
  *) echo "${H}Z outside the scan window" ;;
esac

# Grading is the step that turns collection into H4a samples, and all three of
# its cron slots were dropped on 2026-08-28. Two independent attempts.
case "$H" in
  03|05) dispatch lowno-score.yml ;;
esac

exit $FAIL
