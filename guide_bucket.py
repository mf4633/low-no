"""Is the market's concentration on the guide's bucket calibrated?

Denver today prices 56c on 85-86 with a guide of 86. That is only "spot on" if
the day really does land in the guide's own bucket about 56% of the time.
Countable, with no model: for every settled city-day, find which rung of the
ACTUAL logged ladder the guide fell in, and check whether the settlement landed
in that same rung.

Uses real ladder boundaries rather than assumed 2F bins, because the rungs are
what is traded.
"""
import glob
import json
import os
from collections import defaultdict


def bucket_of(value, rungs):
    """Which rung a temperature falls in. Bottom rung is '<= cap', top is
    '> floor-1', ranges are inclusive on both ends."""
    for g in rungs:
        fl, cap = g.get("fl"), g.get("cap")
        if fl is None and cap is not None and value <= cap:
            return f"<={cap}"
        if fl is not None and cap is not None and fl <= value <= cap:
            return f"{fl}-{cap}"
    for g in rungs:
        if g.get("cap") is None and g.get("fl") is not None and value >= g["fl"]:
            return f">={g['fl']}"
    return None


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    seen = {}
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, c = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or not c:
                continue
            g, rungs = d.get("guide"), d.get("rungs")
            if g is None or not rungs:
                continue
            seen.setdefault((day, c), (g, rungs))     # first ladder of the day

    hit = defaultdict(int)
    tot = defaultdict(int)
    off = defaultdict(int)
    for (day, c), (g, rungs) in seen.items():
        s = settles.get((day, c))
        if s is None:
            continue
        gb, sb = bucket_of(g, rungs), bucket_of(s, rungs)
        if gb is None or sb is None:
            continue
        tot["ALL"] += 1
        tot[c] += 1
        if gb == sb:
            hit["ALL"] += 1
            hit[c] += 1
        off["ALL"] += abs(s - g)
        off[c] += abs(s - g)

    n = tot["ALL"]
    print(f"settled city-days with a ladder and a guide: {n}")
    print(f"settlement landed in the GUIDE'S OWN bucket: {hit['ALL']} "
          f"= {100*hit['ALL']/n:.0f}%")
    print(f"mean |settle - guide|: {off['ALL']/n:.2f}F")
    print()
    print(f"{'city':6}{'n':>5}{'in guide bucket':>18}{'mean |err|':>12}")
    for c in sorted(tot):
        if c == "ALL" or tot[c] < 8:
            continue
        print(f"{c:6}{tot[c]:>5}{100*hit[c]/tot[c]:>17.0f}%{off[c]/tot[c]:>12.2f}")
    print()
    print("Compare against what the market charges for the guide's bucket.")
    print("Denver today: 56c on 85-86 with a guide of 86.")


if __name__ == "__main__":
    main()
