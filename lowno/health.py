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

# Share of live stations that must produce a pairable peak-window observation.
# A healthy day is 100%; 2026-08-30 was 30% and passed the old zero-only test.
# Set well below 1.0 so one flaky station does not cry wolf.
MIN_PEAK_STATION_FRAC = 0.6


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


def _peak_stations(day):
    """(stations with a usable peak pair, stations observed) for `day`.

    A COUNT of samples is the wrong alarm on its own: it moves with the station
    roster, which went 10 -> 21 -> 23 during August, so no fixed number means
    the same thing across the month. The share of live stations that produced
    at least one pairable peak-window observation is comparable across the
    whole record.

    Why this exists: 2026-08-30 logged 15 scan cycles -- the HIGHEST count of
    the month -- and produced 7 usable pairs against a normal 78-84, with 16 of
    23 stations contributing nothing. The old zero-only test passed it in
    silence and no issue was ever opened.
    """
    try:
        import shape_eval
        with_pair = len({c["city"] for c in shape_eval.cycles({day})})
    except Exception as e:
        print("health: could not count peak stations -", str(e)[:120])
        return None, None
    observed = set()
    path = f"logs/{day}.jsonl"
    if not os.path.exists(path):
        return with_pair, 0
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if isinstance(d, dict) and not d.get("world") and d.get("run_max") is not None:
                if r.get("city"):
                    observed.add(r["city"])
    return with_pair, len(observed)


HOURLY_CITIES = {"NYC", "DEN"}
# Provisional. The nowcast legitimately refuses right after a host print (the
# aligned window is too short to carry a tendency) and whenever quorum fails, so
# some refusal is normal and the healthy band is not yet known -- the telemetry
# only started 2026-09-01. Set low enough that only a real outage trips it, and
# the observed rate is printed every run so the band can be pinned down later.
MIN_NOWCAST_AVAIL = 0.40


def _nowcast_availability(day):
    """(rows carrying run_max_nowcast, NYC/DEN rows) for `day`."""
    path = f"logs/{day}.jsonl"
    if not os.path.exists(path):
        return 0, 0
    have = tot = 0
    with open(path) as fh:
        for line in fh:
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict) or d.get("world"):
                continue
            if r.get("city") not in HOURLY_CITIES:
                continue
            tot += 1
            if d.get("run_max_nowcast") is not None:
                have += 1
    return have, tot


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
    elif settled > 0:
        # PARTIAL collapse: the day collected, graded, and still starved H4a.
        with_pair, observed = _peak_stations(day)
        if with_pair is not None and observed:
            frac = with_pair / observed
            if frac < MIN_PEAK_STATION_FRAC:
                problems.append(
                    f"PARTIAL PEAK COVERAGE: only {with_pair} of {observed} "
                    f"stations ({frac:.0%}) produced a pairable peak-window "
                    f"observation on {day}, against ~100% on a healthy day "
                    f"({samples} rate samples). Cycle COUNT can look normal "
                    f"while this is broken -- 2026-08-30 logged the month's "
                    f"highest count and scored 30%.")

    # The interpolator at KNYC/KDEN has failed silently twice on the day it was
    # written -- once because the freshness cut rejected every neighbour during
    # normal API lag, once because one laggy station capped the alignment window
    # to 2 minutes and refused the whole station. Both were found only because a
    # human asked for a live reading. This is that question, asked nightly.
    have, tot = _nowcast_availability(day)
    if tot:
        frac = have / tot
        print(f"health: nowcast availability {day} = {have}/{tot} ({frac:.0%})")
        if frac < MIN_NOWCAST_AVAIL:
            problems.append(
                f"NOWCAST DARK: run_max_nowcast present on only {have} of {tot} "
                f"KNYC/KDEN rows for {day} ({frac:.0%}, floor {MIN_NOWCAST_AVAIL:.0%}). "
                f"The interpolator is refusing far more than it should -- check "
                f"the `dropped` and refusal reasons in nowcast_detail. It has "
                f"failed silently before on a threshold that looked reasonable.")

    # Cycles that scanned but never pushed leave NO trace in the committed
    # logs, so the count has to be handed in from the scan step's environment.
    # This is the 2026-08-30 failure: six cycles collected across the whole
    # eastern peak window, six pushes rejected, and the only surviving evidence
    # was a red run nobody was watching.
    try:
        unpushed = int(os.environ.get("SCAN_PUSH_FAILURES", "0") or 0)
    except ValueError:
        unpushed = 0
    if unpushed:
        problems.append(
            f"UNPUSHED CYCLES: {unpushed} cycle(s) in this run scanned "
            f"successfully but could not be committed. That data is gone and "
            f"does not appear in any log. Check for a conflict outside the "
            f"regenerable set in .github/push_retry.sh.")

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
