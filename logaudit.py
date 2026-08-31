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


if __name__ == "__main__":
    main()
