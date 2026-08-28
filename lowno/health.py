"""Open a GitHub Issue when the MEASUREMENT PIPELINE is broken.

notify.py alerts on trading flags. Nothing alerted on the pipeline itself --
which is how 2026-08-26 and 2026-08-27 each produced ZERO H4a rate samples
while every dashboard looked normal, and how 2026-08-28 lost five cycles to a
wedged rebase. Both were found by a human asking "how is low-no looking?".

This checks yesterday, because yesterday is the last day that can be fully
judged: the current day is unsettled by design (see the same-day settle guard),
so a live zero is expected rather than alarming.

Deliberately NOT a pass/fail on any hypothesis. It reports whether DATA WAS
COLLECTED AND GRADED, never whether a result looks good -- a health check that
leaks an outcome invites the peeking the registrations exist to prevent.

Reuses notify._api, so it no-ops silently without GITHUB_TOKEN (local runs).
"""
import datetime as dt
import glob
import json
import os
import zoneinfo

from . import notify

# A healthy day is ~11 cycles. Alert well below that rather than at the first
# missing fire, so ordinary scheduler flakiness does not cry wolf.
MIN_CYCLES = 5


def _yesterday_et():
    now = dt.datetime.now(zoneinfo.ZoneInfo("America/New_York"))
    return (now.date() - dt.timedelta(days=1)).isoformat()


def _cycles_logged(day):
    """Distinct scan cycles logged for `day`, counted by minute-stamp."""
    path = f"logs/{day}.jsonl"
    if not os.path.exists(path):
        return 0
    stamps = set()
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            at = r.get("at")
            if at:
                stamps.add(at[11:16])
    # Cycles span a few minutes; collapse to the hour to approximate runs.
    return len({s[:2] for s in stamps})


def _settled(day):
    try:
        s = json.load(open("docs/settlements.json"))
    except Exception:
        return 0
    return len([k for k in s if k.startswith(day) and s[k] is not None])


def _rate_samples(day):
    """Peak-window rate samples, via the H4a harness itself.

    Imported read-only and never modified -- shape_eval.py was written before
    its data existed and must not be edited to obtain a result.
    """
    try:
        import shape_eval
        return len(shape_eval.cycles({day}))
    except Exception as e:
        print("health: could not count rate samples -", str(e)[:120])
        return None


def check(day=None):
    """Return a list of problem strings for `day` (default: yesterday ET)."""
    day = day or _yesterday_et()
    problems = []

    cycles = _cycles_logged(day)
    if cycles < MIN_CYCLES:
        problems.append(
            f"COVERAGE: only {cycles} scan hour(s) logged for {day} "
            f"(healthy is ~11). Collection stopped or never started.")

    settled = _settled(day)
    if settled == 0:
        problems.append(
            f"UNGRADED: no settlements for {day}. Grading is what turns "
            f"collection into H4a samples, and CLI is fetchable for only 7 "
            f"days -- after that the day can never be graded.")

    samples = _rate_samples(day)
    if samples == 0 and settled > 0:
        problems.append(
            f"ZERO SAMPLES: {day} settled but produced 0 peak-window rate "
            f"samples. Observations were probably spaced outside the 0.5-2.5h "
            f"pairing band, so the day looks collected but counts for nothing.")

    return day, problems


def report(day=None):
    day, problems = check(day)
    if not problems:
        print(f"health: {day} OK")
        return 0

    for p in problems:
        print(f"health: {p}")

    title = f"pipeline unhealthy: {day}"
    got = notify._api("/issues?state=open&labels=health&per_page=100")
    if got and any(title == (i.get("title") or "") for i in got):
        print("health: issue already open for", day)
        return len(problems)

    body = (
        f"Automated pipeline health check for **{day}** (ET).\n\n"
        + "\n".join(f"- {p}" for p in problems)
        + "\n\nThis reports COLLECTION AND GRADING only -- never whether any "
          "hypothesis looks good.\n\n"
          "Likely causes, in the order they have actually happened:\n"
          "1. GitHub dropped every scheduled fire (5/11 on 2026-08-26, "
          "0/14 on 2026-08-27).\n"
          "2. A wedged rebase left the runner on a detached HEAD, so cycles "
          "committed but could never push (2026-08-28, five cycles lost).\n"
          "3. DISPATCH_PAT expired or was revoked, so neither the chain nor "
          "the Fly trigger can start a run.\n")
    out = notify._api("/issues", "POST",
                      {"title": title, "body": body, "labels": ["health"]})
    if out:
        print(f"health: opened issue #{out.get('number')} for {day}")
    return len(problems)


if __name__ == "__main__":
    # Exits 0 even when yesterday was unhealthy. The GitHub Issue IS the alert,
    # and the run doing the checking usually collected fine -- failing it would
    # say "this run broke" when the truth is "yesterday did", which is exactly
    # the kind of misleading signal that cost two days here.
    #
    # This is not `|| true` masking (CLAUDE.md #9): every problem is printed to
    # the log AND raised as an Issue, and an unexpected crash still propagates
    # and fails the step.
    report()
