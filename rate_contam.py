"""Does hourly publication corrupt H4a's rate buckets at KNYC and KDEN?

H4a classifies a day by rate = delta(run_max) / delta(hours) between consecutive
scans, into stalled / mid / climbing. run_max only moves when the station
publishes. At the 21 five-minute stations that is continuous. At KNYC and KDEN
it happens once an hour, and our scan cadence is ~55 minutes -- so two
consecutive scans will regularly fall between the same pair of prints, giving
delta(run_max) = 0 and labelling the day STALLED when it may be climbing hard.

If so, the shape cells at those two stations are polluted by publication timing
rather than weather, and both H4a and H5 (which reuses the cells) inherit it.

Compares the rate-bucket mix at the two hourly stations against the 21 others,
restricted to the 13-16 local peak window where H4a operates.
"""
import datetime as dt
import glob
import json
import os
import zoneinfo
from collections import Counter, defaultdict

from lowno import empirical as E
from lowno.config import CITIES

HOURLY = {"NYC", "DEN"}
GAP_LO, GAP_HI = 0.5, 2.5


def main():
    paths = defaultdict(list)
    for p in sorted(glob.glob("logs/2*.jsonl")):
        day = os.path.basename(p)[:-6]
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d, c = r.get("detail"), r.get("city")
            if not isinstance(d, dict) or d.get("world") or c not in CITIES:
                continue
            rm = d.get("run_max")
            if rm is None:
                continue
            try:
                lt = (dt.datetime.fromisoformat(r["at"]).replace(tzinfo=dt.timezone.utc)
                      .astimezone(zoneinfo.ZoneInfo(CITIES[c]["tz"])))
            except Exception:
                continue
            paths[(day, c)].append((lt.hour + lt.minute / 60.0, lt.hour, rm))

    buckets = defaultdict(Counter)
    zero_delta = Counter()
    total = Counter()
    for (day, c), v in paths.items():
        v.sort(key=lambda x: x[0])
        grp = "hourly" if c in HOURLY else "5-min"
        for i in range(1, len(v)):
            hf, h, rm = v[i]
            dh = hf - v[i - 1][0]
            if not (GAP_LO <= dh <= GAP_HI) or not (13 <= h <= 16):
                continue
            delta = rm - v[i - 1][2]
            b = E.rate_bucket(delta / dh)
            if b is None:
                continue
            buckets[grp][b] += 1
            total[grp] += 1
            if abs(delta) < 1e-9:
                zero_delta[grp] += 1
            buckets[c][b] += 1
            total[c] += 1
            if abs(delta) < 1e-9:
                zero_delta[c] += 1

    print("Peak-window (13-16 local) rate classifications, by station group")
    print(f"{'group':10}{'n':>7}{'stalled':>10}{'mid':>9}{'climbing':>11}"
          f"{'exactly 0 delta':>18}")
    for grp in ("hourly", "5-min"):
        n = total[grp]
        if not n:
            continue
        b = buckets[grp]
        print(f"{grp:10}{n:>7}{100*b['stalled']/n:>9.0f}%{100*b['mid']/n:>8.0f}%"
              f"{100*b['climbing']/n:>10.0f}%{100*zero_delta[grp]/n:>17.0f}%")

    print(f"\n{'city':6}{'n':>6}{'stalled':>10}{'exactly 0 delta':>18}  cadence")
    for c in sorted(total):
        if c in ("hourly", "5-min") or total[c] < 15:
            continue
        n = total[c]
        print(f"{c:6}{n:>6}{100*buckets[c]['stalled']/n:>9.0f}%"
              f"{100*zero_delta[c]/n:>17.0f}%  "
              f"{'HOURLY' if c in HOURLY else '5-min'}")
    print()
    print("A 'stalled' label means H4a expects ~+1.05F of remaining climb instead")
    print("of ~+2.53F. If the hourly stations are over-labelled stalled purely")
    print("because no new print landed, their cells are measuring the publication")
    print("schedule and not the weather -- and H5 reuses those cells.")


if __name__ == "__main__":
    main()
