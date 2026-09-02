"""Is every field each live hypothesis needs actually being logged?

A hypothesis that cannot be scored because a field was never written is the
cheapest possible failure and the easiest to miss -- H4b's telemetry only
started on 2026-08-27, and nobody would have noticed for weeks if it had not.
This checks presence per day, per field, against what each registered test
actually reads.

Run it after any change to what the scan writes.
"""
import glob
import json
import os
from collections import defaultdict

# field -> (who needs it, where it lives)
NEEDS = [
    ("run_max",          "H4a, H5, gate", "detail"),
    ("guide",            "gate, bias",    "detail"),
    ("pop",              "gate",          "detail"),
    ("curve_dev",        "H4b",           "detail"),
    ("temp_now",         "H7",            "detail"),
    ("curve_pred_now",   "H4b context",   "detail"),
    ("run_max_nowcast",  "H7 (NYC/DEN)",  "detail"),
    ("nowcast_detail",   "H7 (NYC/DEN)",  "detail"),
    ("airmass",          "telemetry",     "detail"),
    ("sky",              "telemetry",     "detail"),
    ("depth",            "floor96_depth", "rung"),
    ("na",               "every band",    "rung"),
    ("nb",               "two-sided",     "rung"),
    ("ya",               "YES bands",     "rung"),
    ("yb",               "spread",        "rung"),
    ("cap",              "every band",    "rung"),
    ("oi",               "telemetry",     "rung"),
    ("vol",              "forced.py",     "rung"),
]
HOURLY = {"NYC", "DEN"}

# One whole degree C is 1.8F. A run_max derived from a C-quantized observation
# sits above the whole-F value CLI reports, and the bound is the FULL step, not
# the half-step: measured deficits reach -1.20F (AUS 2026-08-12, run_max 102.20
# = 39.0C exactly, CLI 101), which a round-to-nearest cannot produce. Both
# outliers WOULD fit if CLI took the whole-F value at or below the true max,
# but H9 tested that convention against the model the same day and it is NOT
# SUPPORTED (see CANDIDATE.md); the two rows are unexplained. The bound stays
# at the full step because it is the MEASURED deficit that sets it, whatever
# the mechanism. Do not "tighten" this back to 0.9.
C_STEP_F = 1.8
MAX_C_INFLATION_F = 1.8


def _on_c_grid(f):
    c = (f - 32) / C_STEP_F
    return abs(c - round(c)) < 1e-6


def climb_integrity():
    """settle - run_max must be >= 0. Report every sample where it is not.

    Found 2026-09-02: 21% of peak-window shape samples asserted a NEGATIVE
    remaining climb, which is arithmetically impossible -- settle is the day's
    maximum and run_max is a running max of observations. Cause is a unit
    conversion, not a fault in the data collection: the 5-minute obs are
    quantized to whole degrees C and converted (31C -> 87.8F) while CLI settles
    in whole degrees F and reports 87. Our run_max therefore runs up to 0.9F
    hot, and the visible deficits cap at exactly -0.80.

    This matters because `settle - run_max` is the OUTCOME VARIABLE for H4a,
    H7 and H8, and the sample it feeds is the empirical P(exceed) distribution.
    An impossible value in training data is not noise, it is a wrong label.

    The row filter deliberately matches what the shape harnesses read -- any
    non-world row carrying run_max for a known city -- and NOT `verdict ==
    "LADDER"`. Requiring that label is what blinded the settlement quarantine
    to 2026-08-06..08-09, and a check that reads a different slice than its
    consumers is not protecting them.
    """
    try:
        from lowno.config import CITIES
        settles = {tuple(k.split("|")): v
                   for k, v in json.load(open("docs/settlements.json")).items()}
    except Exception as e:
        return None, f"unavailable ({str(e)[:60]})"

    per_day, worst, grid, total, bad_keys = defaultdict(int), {}, 0, 0, set()
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
            rm = d.get("run_max")
            if rm is None:
                continue
            s = settles.get((day, city))
            if s is None:
                continue
            total += 1
            if _on_c_grid(rm):
                grid += 1
            if s - rm < 0:
                per_day[day] += 1
                bad_keys.add((day, city))
                if s - rm < worst.get(day, (0,))[0]:
                    worst[day] = (s - rm, city)
                elif day not in worst:
                    worst[day] = (s - rm, city)
    return dict(per_day=dict(per_day), worst=worst, grid=grid, total=total,
                bad=sum(per_day.values()), city_days=len(bad_keys)), None


def main():
    days = sorted(os.path.basename(p)[:-6] for p in glob.glob("logs/2*.jsonl"))
    days = days[-8:]
    have = defaultdict(lambda: defaultdict(int))
    rows = defaultdict(int)
    hrows = defaultdict(int)
    lrows = defaultdict(int)
    for day in days:
        for line in open(f"logs/{day}.jsonl"):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d = r.get("detail")
            if not isinstance(d, dict) or d.get("world"):
                continue
            city = r.get("city")
            rows[day] += 1
            if city in HOURLY:
                hrows[day] += 1
            # Rung fields can only appear on LADDER rows. Scoring them against
            # every row makes a complete ladder look like 50% coverage.
            if r.get("verdict") == "LADDER":
                lrows[day] += 1
            for f, _, where in NEEDS:
                if where == "detail":
                    if d.get(f) is not None:
                        have[f][day] += 1
                else:
                    for g in (d.get("rungs") or []):
                        if g.get(f) is not None:
                            have[f][day] += 1
                            break

    print(f"rows per day: " + "  ".join(f"{d[5:]}={rows[d]}" for d in days))
    print(f"NYC/DEN rows: " + "  ".join(f"{d[5:]}={hrows[d]}" for d in days))
    print()
    hdr = "".join(f"{d[5:]:>7}" for d in days)
    print(f"{'field':18}{'needed by':16}{hdr}")
    for f, who, where in NEEDS:
        cells = ""
        for d in days:
            denom = (hrows[d] if "NYC/DEN" in who
                     else lrows[d] if where == "rung" else rows[d])
            if not denom:
                cells += f"{'-':>7}"
                continue
            pct = 100 * have[f][d] / denom
            cells += f"{pct:>6.0f}%"
        print(f"{f:18}{who:16}{cells}")
    print()
    print("Percentages are of rows that COULD carry the field: rung fields against")
    print("LADDER rows, NYC/DEN fields against NYC/DEN rows, the rest against all.")
    print("A field at 0% on recent days that is needed by a live hypothesis is a")
    print("blocker, not a gap -- that test simply cannot be scored.")

    res, err = climb_integrity()
    print()
    print("CLIMB INTEGRITY -- settle - run_max must be >= 0")
    if err:
        print(f"  {err}")
        return
    pct = 100 * res["bad"] / res["total"] if res["total"] else 0
    gpct = 100 * res["grid"] / res["total"] if res["total"] else 0
    print(f"  impossible samples: {res['bad']} of {res['total']} ({pct:.0f}%), "
          f"across {res['city_days']} city-days")
    print(f"  run_max on the whole-degree-C grid: {gpct:.0f}% "
          f"(inflated up to {MAX_C_INFLATION_F}F vs a whole-F CLI settlement)")
    if res["per_day"]:
        recent = sorted(res["per_day"])[-8:]
        print("  recent days: " + "  ".join(
            f"{d[5:]}={res['per_day'][d]}" for d in recent))
        w = min(res["worst"].values())
        print(f"  worst deficit: {w[0]:+.2f}F ({w[1]})")
    print("  KNOWN AND DEFERRED (2026-09-02): the repair waits until H4a has")
    print("  reported, so the registered test runs on the data it was")
    print("  registered against. See CANDIDATE.md. A rising count here, or a")
    print(f"  deficit beyond -{MAX_C_INFLATION_F}F, is something NEW -- one C step")
    print("  cannot produce it -- and should be investigated immediately.")
    print("  OPEN RISK, shadow.py quarantine: it drops a settlement when")
    print("  `v < round(obs) - 1`, i.e. a 1.0F tolerance, on the stated premise")
    print("  that our observed max is a valid lower bound. It is NOT -- a")
    print(f"  C-grid run_max sits up to {MAX_C_INFLATION_F}F high -- so a CORRECT")
    print("  settlement can be quarantined, and outside the 7-day CLI window")
    print("  that loss is permanent. The tolerance wants 2F, not 1F.")


if __name__ == "__main__":
    main()
