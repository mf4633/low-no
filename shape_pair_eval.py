"""Hypothesis 8 -- the GAP between the two shape variables, which is the only
thing H4a and H7 actually disagree about.

WRITTEN 2026-09-02, BEFORE ANY H8 OUTCOME WAS COMPUTED. H4a and H7 are both
untouched: `shape_eval.py` and `shape_temp_eval.py` are not imported for their
models, not edited, and not re-tuned. This is a third harness with its own
verdict, exactly as H7 was to H4a.

WHY A "HYBRID" OF H4a AND H7 IS ONLY ONE THING. H7 is already H4a with a single
variable swapped: H4a buckets the rate of `run_max`, H7 buckets the rate of
`temp_now`, everything else identical. Averaging two buckets of the same
tendency would not be a hybrid, it would be one signal plus a noisier copy of
itself -- H7's own premise is that H4a's variable is the degraded one. The only
information that exists in the PAIR and in neither member is their DIFFERENCE:

    off_peak_gap = run_max - temp_now

H4a cannot see it (run_max alone). H7 cannot see it (temp_now alone). It is
exactly what the two variables disagree about, and it has a physical meaning.

MECHANISM, AND THE DIRECTION IS PRE-DECLARED. A large gap means the day already
set its high and has fallen back from it. Such a day must first recover the gap
before it can set a new high at all, so for a cap ABOVE the running max the
climb still to come is shorter than the tendency alone suggests. H7's finding
sharpens this: among peak-window intervals with delta(run_max) = 0 -- 47% of
them -- re-bucketing on temp_now splits 79% stalled / 3% mid / 18% CLIMBING.
Those 18% are days climbing BELOW their own maximum. "Climbing" and "climbing
with 4F to recover first" are the same bucket to H7 and the same bucket to H4a.

    PREDICTION: within a given temp_now rate bucket, a FLAGGED (off-peak)
    sample has LESS remaining climb (settle - run_max) than an unflagged one.

A difference in the other direction falsifies the mechanism rather than
supporting a variant of it.

THE THRESHOLD IS INSTRUMENT-DERIVED, NOT FITTED. 1.8F is one whole-degree-C
step, and the 5-minute observations are quantized to whole C. Below that a
"gap" cannot be distinguished from a rounding artifact. It is not chosen to
balance the split and it is not to be moved: if it needs changing, the change
is recorded in CANDIDATE.md with a reason, like every other correction here.

TWO LEGS, AND ONLY ONE OF THEM CAN BE ANSWERED IN TIME. This mirrors H4a's own
history, where the information claim was established on pooled samples first
and the held-out Brier validation came after.

  H8a -- INFORMATION. Pooled inside the peak window, stratified by temp_now
         bucket so this cannot be a Simpson artifact: does the flag move
         remaining climb? Bar: >= MIN_PER_GROUP samples in each of the four
         groups (flagged/unflagged x stalled/climbing). ANSWERABLE.

  H8b -- VALIDATION. The flag as a fourth cell dimension, held-out Brier
         against BOTH H4a's and H7's conditioning. Bar: MIN_SCORED held-out
         decisions on cells at E.MIN_N_RATE. **On the arithmetic below this
         CANNOT be reached before the 2026-12-31 programme stop**, and that is
         stated here rather than discovered in November: the joint cell splits
         H7's cells again, the flagged branch carries ~18% of peak-window rows,
         and H7's own cells are not expected to be scorable until late
         September. H8b is registered so that it is defined in advance if the
         programme is ever extended by something that PASSED -- not because it
         is expected to report.

BASELINES ARE BOTH, PRE-DECLARED. H8b must beat H4a's conditioning AND H7's
conditioning. Naming both now removes the later temptation to compare against
whichever one happens to look worse.

WHAT A PASS ON H8a IS AND IS NOT. It is an information claim, the same status
H4a's 1.48F held before its held-out test -- and H3 is the standing reminder
that a real signal can be entirely priced. H8 has NO pilot and cannot promote
anything. A trading claim on this gap would be a separate registration with its
own 60 units.

DISCLOSURE -- everything computed from the data before these rules were fixed:
  * peak-window rows carrying BOTH run_max and temp_now: 1018
  * distribution of run_max - temp_now: p10 0.00, p50 0.36, p90 3.60, max 18.00
  * share above candidate cuts: 49% (>0.5F), 45% (>1.0F), 18% (>1.8F),
    16% (>3.0F). 1.8 was taken from the quantization step, not from this list.
  * joint-cell depth on the train half: 82 cells, deepest 2, none at 12
Not one of those touches `settle`. No remaining-climb figure, no group mean and
no Brier value was computed before this file existed.
"""
import datetime as dt
import glob
import json
import math
import os
import statistics
import zoneinfo
from collections import defaultdict

from lowno import empirical as E
from lowno.config import CITIES

OFF_PEAK_GAP = 1.8      # one whole-degree-C step; below this is quantization
MIN_PER_GROUP = 150     # H8a, per group; ~0.2 sd detectable at conventional power
MIN_SCORED = 50         # H8b, same bar as H4a and H7


def _rows():
    """(day, city) -> sorted [(hour_float, hour, run_max, temp_now)].

    Deliberately its own reader rather than an import: H4a and H7 must keep
    working exactly as registered even if this file is later changed.
    """
    out = defaultdict(list)
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, city = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or city not in CITIES:
                continue
            rm, tn = d.get("run_max"), d.get("temp_now")
            if rm is None or tn is None:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"])
                      .replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[city]["tz"])))
            except Exception:
                continue
            out[(day, city)].append((lt.hour + lt.minute / 60.0, lt.hour, rm, tn))
    for k in out:
        out[k].sort(key=lambda x: x[0])
    return out


def _settles():
    return {tuple(k.split("|")): v
            for k, v in json.load(open("docs/settlements.json")).items()}


def samples(days_keep=None):
    """Peak-window paired cycles carrying the flag and the outcome.

    Same pairing rules as H4a and H7 -- 13-16 local, consecutive cycles
    0.5-2.5h apart, settled days only -- so a difference here cannot come from
    a different population.
    """
    settles, rows = _settles(), _rows()
    out = []
    for (day, city), v in rows.items():
        if days_keep is not None and day not in days_keep:
            continue
        s = settles.get((day, city))
        if s is None:
            continue
        for i in range(1, len(v)):
            hf, h, rm, tn = v[i]
            if not (E.PEAK_WINDOW[0] <= h <= E.PEAK_WINDOW[1]):
                continue
            dh = hf - v[i - 1][0]
            if not (0.5 <= dh <= 2.5):
                continue
            bucket = E.rate_bucket((tn - v[i - 1][3]) / dh)
            if bucket is None:
                continue
            out.append(dict(day=day, city=city, hour=h, bucket=bucket,
                            run_max=rm, temp_now=tn,
                            off_peak=bool((rm - tn) > OFF_PEAK_GAP),
                            remaining=s - rm, settle=s))
    return out


def _diff_ci(a, b, z=1.96):
    """mean(a) - mean(b) with a normal 95% interval (Welch standard error).

    Normal rather than t because the registered bar is 150 per group; at that
    size the difference is immaterial and the constant is fixed in advance.
    """
    if len(a) < 2 or len(b) < 2:
        return (None, None, None)
    d = statistics.mean(a) - statistics.mean(b)
    se = math.sqrt(statistics.variance(a) / len(a) + statistics.variance(b) / len(b))
    if se == 0:
        return (round(d, 3), None, None)
    return (round(d, 3), round(d - z * se, 3), round(d + z * se, 3))


def _groups(rows):
    g = defaultdict(list)
    for r in rows:
        if r["bucket"] == "mid":
            continue          # the deliberately undefined middle, as in H4a
        g[(r["bucket"], r["off_peak"])].append(r["remaining"])
    return g


def verdict():
    """Machine-readable gate for H8a, the answerable leg.

    PASSES only when the flagged group shows LESS remaining climb than the
    unflagged group with a 95% interval excluding zero, in BOTH the stalled and
    the climbing bucket. Requiring both is deliberate: one bucket alone is a
    subgroup finding, and the mechanism claims the gap matters wherever a day
    is below its own maximum.
    """
    try:
        rows = samples()
        g = _groups(rows)
    except Exception as e:
        return dict(id="H8", ready=False, passed=False, error=str(e)[:120])

    counts = {f"{b}_{'off' if f else 'on'}": len(v) for (b, f), v in g.items()}
    for b in ("stalled", "climbing"):
        for f in (True, False):
            counts.setdefault(f"{b}_{'off' if f else 'on'}", len(g.get((b, f), [])))
    if any(len(g.get((b, f), [])) < MIN_PER_GROUP
           for b in ("stalled", "climbing") for f in (True, False)):
        return dict(id="H8", ready=False, passed=False, counts=counts,
                    need_per_group=MIN_PER_GROUP,
                    reason="data bar not met (four groups, %d each)" % MIN_PER_GROUP)

    legs, ok = {}, True
    for b in ("stalled", "climbing"):
        d, lo, hi = _diff_ci(g[(b, True)], g[(b, False)])
        legs[b] = dict(diff=d, ci=[lo, hi], n_off=len(g[(b, True)]),
                       n_on=len(g[(b, False)]))
        if hi is None or hi >= 0:
            ok = False          # must be NEGATIVE: less remaining climb
    return dict(id="H8", ready=True, passed=bool(ok), counts=counts, legs=legs)


def validation():
    """H8b -- the joint cell, held-out against BOTH H4a's and H7's conditioning.

    Reported, never promoted. Refuses until MIN_SCORED decisions exist on cells
    that have earned E.MIN_N_RATE, which on the arithmetic in the module
    docstring will not happen before the programme stop.
    """
    days = sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    train = {d for d in days if int(d[-1]) % 2 == 0}
    test = {d for d in days if int(d[-1]) % 2 == 1}
    cells = defaultdict(list)
    for r in samples(train):
        cells[(r["city"], r["hour"], r["bucket"], r["off_peak"])].append(r["remaining"])
    deep = {k: v for k, v in cells.items() if len(v) >= E.MIN_N_RATE}
    n = 0
    for r in samples(test):
        if (r["city"], r["hour"], r["bucket"], r["off_peak"]) in deep:
            n += 1
    return dict(id="H8b", ready=bool(n >= MIN_SCORED), passed=False,
                scored=n, need=MIN_SCORED, cells=len(cells), cells_deep=len(deep),
                reason=("not enough held-out decisions on earned joint cells"
                        if n < MIN_SCORED else "scorable"))


def main():
    v = verdict()
    print("H8a -- does the run_max/temp_now gap carry information?")
    print(f"  groups (bar {MIN_PER_GROUP} each): {v.get('counts')}")
    if not v.get("ready"):
        print("  DATA BAR NOT MET -- refusing to report a result. "
              "This is the registered behaviour, not a failure.")
    else:
        print(f"\n  {'bucket':>10} {'n off':>7} {'n on':>7} {'diff F':>9} {'95% CI':>20}")
        for b, leg in v["legs"].items():
            print(f"  {b:>10} {leg['n_off']:>7} {leg['n_on']:>7} "
                  f"{leg['diff']:>9.2f} {str(leg['ci']):>20}")
        print("\n  verdict on the registered claim:")
        if v["passed"]:
            print("  A day below its own maximum has LESS climb left than its")
            print("  tendency implies, in both buckets. INFORMATION only -- H3")
            print("  is the reminder that a real signal can be fully priced.")
        else:
            print("  Not distinguishable from zero in both buckets. The gap")
            print("  adds nothing that the tendency did not already carry.")

    b = validation()
    print(f"\nH8b -- joint cell vs H4a and H7 (validation leg)")
    print(f"  {b['scored']}/{b['need']} held-out decisions; "
          f"{b['cells_deep']}/{b['cells']} cells at n>={E.MIN_N_RATE}")
    print("  Registered but not expected to report before the 2026-12-31 stop; "
          "see the module docstring.")


if __name__ == "__main__":
    main()
