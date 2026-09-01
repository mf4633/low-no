"""Does 'the nearest morning analogue' predict the daily max better than the guide?

I offered Michael a piece of counter-evidence against the DEN 85-86 NO call: the
one day that started at today's 66F (Aug 25) settled at 85, inside the bucket.
That is analogue reasoning, and before it gets appended to the call record it
has to earn the status of evidence. Otherwise it is a story about one day.

The test: for every settled city-day, take the morning temperature, find the
NEAREST analogue among that city's other days by morning temperature, and
predict the max from the analogue. Score against the guide, which is the
incumbent. Leave-one-day-out by construction, since a day never matches itself.

If the analogue cannot beat the guide, then "the closest morning analogue
settled at 85" is not a reason to doubt anything, and nothing gets appended.
"""
import datetime as dt
import glob
import json
import os
import statistics
import zoneinfo
from collections import defaultdict

from lowno.config import CITIES

MORNING_H = (8, 10)      # first observation in this local-hour window


def main():
    settles = {tuple(k.split("|")): v
               for k, v in json.load(open("docs/settlements.json")).items()}
    morn, guide = {}, {}
    for path in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(path)[:-6]
        for line in open(path):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, c = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or c not in CITIES:
                continue
            t = d.get("temp_now")
            if t is None:
                t = d.get("run_max")          # fallback for pre-08-27 days
            if t is None:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[c]["tz"])))
            except Exception:
                continue
            if MORNING_H[0] <= lt.hour <= MORNING_H[1]:
                morn.setdefault((day, c), t)
            if d.get("guide") is not None:
                guide.setdefault((day, c), d["guide"])

    per_city = defaultdict(list)
    for (day, c), t in morn.items():
        s = settles.get((day, c))
        if s is not None:
            per_city[c].append((day, t, s))

    ana_err, guide_err, n_used = [], [], 0
    per_city_rows = []
    for c, rows in per_city.items():
        if len(rows) < 4:
            continue
        for day, t, s in rows:
            others = [(abs(t - t2), s2) for d2, t2, s2 in rows if d2 != day]
            if not others:
                continue
            others.sort()
            pred = others[0][1]                     # nearest analogue's settle
            g = guide.get((day, c))
            if g is None:
                continue
            ana_err.append(abs(pred - s))
            guide_err.append(abs(g - s))
            n_used += 1
        if len(rows) >= 5:
            sub_a = [abs(sorted([(abs(t-t2), s2) for d2, t2, s2 in rows if d2 != day])[0][1] - s)
                     for day, t, s in rows]
            sub_g = [abs(guide[(day, c)] - s) for day, t, s in rows if (day, c) in guide]
            if sub_g:
                per_city_rows.append((c, len(rows), statistics.fmean(sub_a),
                                      statistics.fmean(sub_g)))

    if not ana_err:
        print("no usable city-days")
        return
    print(f"city-days scored: {n_used}  (cities with >= 4 settled days)")
    print(f"  nearest-morning-analogue MAE : {statistics.fmean(ana_err):.2f}F")
    print(f"  guide MAE                    : {statistics.fmean(guide_err):.2f}F")
    diff = [a - g for a, g in zip(ana_err, guide_err)]
    m = statistics.fmean(diff)
    se = statistics.stdev(diff) / (len(diff) ** 0.5)
    print(f"  analogue minus guide         : {m:+.2f}F  [{m-1.96*se:+.2f}, {m+1.96*se:+.2f}]")
    print("  (positive means the analogue is WORSE than the guide)")
    print(f"\n{'city':6}{'n':>4}{'analogue MAE':>15}{'guide MAE':>12}{'analogue better?':>19}")
    for c, n, a, g in sorted(per_city_rows, key=lambda r: r[2] - r[3]):
        print(f"{c:6}{n:>4}{a:>15.2f}{g:>12.2f}{('YES' if a < g else 'no'):>19}")


if __name__ == "__main__":
    main()
